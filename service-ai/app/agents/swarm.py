"""
app/agents/swarm.py
────────────────────
Swarm orchestrator — builds the agent graph and exposes run_swarm()
and stream_swarm() for non-streaming and streaming execution.

Constitution compliance:
  - No MongoDB imports or connections.
  - All RunResult field access uses type_guards.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from agents import Agent, Runner, RunResult, set_default_openai_client
from fastapi import HTTPException, status
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.agents.triage_agent import build_triage_agent
from app.core.llm_proxy import get_openai_client
from app.core.logging import get_logger
from app.core.type_guards import ensure_str
from app.schemas.chat import AgentMetadata, AgentResponse, ChatRequest

logger = get_logger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on rate-limit (429) or server errors (500/503)."""
    msg = str(exc).lower()
    return any(code in msg for code in ["429", "500", "503", "rate limit", "overloaded"])

# Module-level reference to the built swarm — set once by initialise_swarm()
_triage_agent: Agent | None = None


def sanitize_history_for_groq(messages: list[dict]) -> list[dict]:
    """
    Strip tool-call artifacts from message history before sending to Groq.

    Groq's Llama models reject messages with 'role: tool' or assistant messages
    that contain 'tool_calls' without corresponding text content. This sanitizer
    removes those entries so multi-turn sessions don't break.

    Rules:
      - Drop any message with role='tool'
      - For role='assistant' with 'tool_calls':
          - If it also has non-empty 'content' → keep but strip 'tool_calls'
          - If content is empty/None → drop entirely
      - Keep all 'user', 'system', and clean 'assistant' messages unchanged
    """
    sanitized = []
    for msg in messages:
        role = msg.get("role", "")

        if role == "tool":
            continue  # drop tool result messages

        if role == "assistant" and "tool_calls" in msg:
            content = msg.get("content") or ""
            if content.strip():
                # Keep the text but strip the tool_calls key
                clean = {k: v for k, v in msg.items() if k != "tool_calls"}
                sanitized.append(clean)
            # else: pure tool-call assistant turn — drop it
            continue

        sanitized.append(msg)

    return sanitized


async def initialise_swarm() -> Agent:
    """
    Build the full agent swarm, wire the SDK client, and inject MCP servers.
    Called once from the FastAPI lifespan startup handler.
    Idempotent — returns the cached agent on subsequent calls.
    """
    global _triage_agent
    if _triage_agent is not None:
        return _triage_agent

    # Wire the active OpenAI-compatible client
    client = get_openai_client()
    set_default_openai_client(client)
    logger.info("Swarm client wired to active OpenAI-compatible endpoint.")

    # Fetch MCP servers for the ResearchAgent
    from app.services.mcp_service import get_mcp_manager  # noqa: PLC0415
    mcp_manager = get_mcp_manager()
    research_mcp_servers = mcp_manager.servers_for_agent("ResearchAgent")

    if research_mcp_servers:
        logger.info(
            "Injecting %d MCP server(s) into ResearchAgent: %s",
            len(research_mcp_servers),
            [s.name for s in research_mcp_servers],
        )
    else:
        logger.info("No MCP servers configured — ResearchAgent using mock tools.")

    _triage_agent = build_triage_agent(mcp_servers=research_mcp_servers or None)
    logger.info("Swarm ready — entry point: %s", _triage_agent.name)
    return _triage_agent


def get_swarm() -> Agent:
    """
    Return the already-initialised triage agent.
    Raises RuntimeError if called before initialise_swarm().
    """
    if _triage_agent is None:
        raise RuntimeError(
            "Swarm has not been initialised. "
            "Ensure initialise_swarm() is awaited in the FastAPI lifespan."
        )
    return _triage_agent


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    reraise=True,
)
async def _run_with_retry(agent: Agent, input_messages: list, context_variables: dict | None = None) -> RunResult:
    """Execute Runner.run with exponential backoff on 429/500/503."""
    return await Runner.run(
        starting_agent=agent,
        input=input_messages,
        context=context_variables,
        max_turns=10,
    )


async def run_swarm(request: ChatRequest) -> AgentResponse:
    """
    Execute a ChatRequest through the TriageAgent swarm.

    Passes the full conversation history as a list of OpenAI-style message
    dicts so the SDK's Runner has native multi-turn context. The session_id
    is injected as a system message so memory tools can use it.

    Args:
        request: Validated ChatRequest — messages list contains full history
                 (loaded and merged by the chat route before calling here).

    Returns:
        AgentResponse with the final output and routing metadata.
    """
    triage = get_swarm()

    user_input = request.last_user_message
    ensure_str(user_input, "run_swarm.user_input")

    context_id = request.memory_context_id or request.request_id

    system_msg = {
        "role": "system",
        "content": f"session_id: {context_id}",
    }

    history_msgs = [
        {"role": msg.role, "content": msg.content}
        for msg in request.normalized_messages()
    ]

    input_messages = [system_msg] + history_msgs

    # Sanitize tool-call artifacts for Groq compatibility
    from app.core.config import get_settings as _cfg  # noqa: PLC0415
    if _cfg().llm_provider == "groq":
        input_messages = sanitize_history_for_groq(input_messages)

    logger.info(
        "run_swarm — request_id=%s, input_len=%d, context_id=%s, history_turns=%d",
        request.request_id,
        len(user_input),
        context_id,
        len(request.normalized_messages()),
    )

    # context_variables are injected into tool functions via context_variables: dict param
    # — hidden from the LLM schema, available to tools at runtime.
    context_variables = {
        "session_id": context_id,
        "client_id": request.request_id,  # WebSocket client_id == request_id in stream.py
        "request_id": request.request_id,
    }

    try:
        result: RunResult = await asyncio.wait_for(
            _run_with_retry(triage, input_messages, context_variables),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.error("run_swarm timed out — request_id=%s", request.request_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": {"code": "LLM_TIMEOUT",
                               "message": "The AI service did not respond in time. Please try again.",
                               "request_id": request.request_id}},
        )

    final_output = result.final_output
    if not isinstance(final_output, str):
        final_output = str(final_output) if final_output is not None else ""

    last_agent: Agent = result.last_agent
    handoff_chain = _extract_handoff_chain(result)
    handoff_occurred = len(handoff_chain) > 1

    # Extract token usage from all model responses in this run
    prompt_tokens = 0
    completion_tokens = 0
    for model_response in result.raw_responses:
        usage = getattr(model_response, "usage", None)
        if usage:
            prompt_tokens += getattr(usage, "input_tokens", 0)
            completion_tokens += getattr(usage, "output_tokens", 0)

    logger.info(
        "run_swarm complete — last_agent=%s, handoff=%s, turns=%d, tokens=%d",
        last_agent.name,
        handoff_occurred,
        result._current_turn,
        prompt_tokens + completion_tokens,
    )

    return AgentResponse(
        request_id=request.request_id,
        content=final_output,
        agent=AgentMetadata(
            agent_name=last_agent.name,
            handoff_occurred=handoff_occurred,
            handoff_chain=handoff_chain,
            turns_used=result._current_turn,
        ),
        model=request.model or _cfg().active_model,
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


async def stream_swarm(
    request: ChatRequest,
    result_container: dict | None = None,
) -> AsyncIterator[str]:
    """
    Execute a ChatRequest through the TriageAgent swarm in streaming mode.

    Yields text delta strings as they arrive from the LLM.
    Tool calls and handoffs are handled internally — only final text
    tokens are yielded to the caller.

    After the iterator is exhausted, the caller can read exact token usage
    from the caller-owned result_container.

    Usage:
        async for delta in stream_swarm(request):
            await websocket.send_text(delta)
        usage = get_stream_usage(result_container.get("result"))

    Args:
        request: Validated ChatRequest with full history merged in.

    Yields:
        str — incremental text chunks from the LLM.
    """
    from agents import RawResponsesStreamEvent, RunConfig, ModelSettings  # noqa: PLC0415

    triage = get_swarm()
    context_id = request.memory_context_id or request.request_id

    system_msg = {
        "role": "system",
        "content": f"session_id: {context_id}",
    }
    history_msgs = [{"role": msg.role, "content": msg.content} for msg in request.normalized_messages()]
    input_messages = [system_msg] + history_msgs

    logger.info(
        "stream_swarm — request_id=%s, context_id=%s, history_turns=%d",
        request.request_id, context_id, len(request.normalized_messages()),
    )

    context_variables = {
        "session_id": context_id,
        "client_id": request.request_id,
        "request_id": request.request_id,
    }

    from app.core.config import get_settings as _get_settings  # noqa: PLC0415
    _settings = _get_settings()
    run_config = None
    if _settings.llm_provider == "groq":
        input_messages = sanitize_history_for_groq(input_messages)
        run_config = RunConfig(model_settings=ModelSettings(parallel_tool_calls=False))

    result = Runner.run_streamed(
        starting_agent=triage,
        input=input_messages,
        context=context_variables,
        max_turns=10,
        run_config=run_config,
    )

    try:
        async with asyncio.timeout(30.0):
            async for event in result.stream_events():
                if not isinstance(event, RawResponsesStreamEvent):
                    continue

                data = event.data
                delta_content: str | None = None

                if hasattr(data, "choices") and data.choices:
                    delta = data.choices[0].delta
                    if delta and delta.content:
                        delta_content = delta.content
                elif hasattr(data, "type") and data.type == "response.output_text.delta":
                    delta_content = getattr(data, "delta", None)

                if delta_content:
                    yield delta_content
    except asyncio.TimeoutError:
        logger.error("stream_swarm timed out — request_id=%s", request.request_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": {"code": "LLM_TIMEOUT",
                               "message": "The AI service did not respond in time.",
                               "request_id": request.request_id}},
        )

    if result_container is not None:
        result_container["result"] = result
        result_container["usage"] = get_stream_usage(result)

    logger.info(
        "stream_swarm complete — request_id=%s, last_agent=%s",
        request.request_id,
        result.last_agent.name if result.last_agent else "unknown",
    )

def get_stream_usage(result) -> dict[str, int]:
    """
    Return exact token usage from one request-scoped streaming result.
    Returns zeros if no result is available.
    """
    if result is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    prompt_tokens = 0
    completion_tokens = 0
    for model_response in getattr(result, "raw_responses", []):
        usage = getattr(model_response, "usage", None)
        if usage:
            prompt_tokens += getattr(usage, "input_tokens", 0)
            completion_tokens += getattr(usage, "output_tokens", 0)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _extract_handoff_chain(result: RunResult) -> list[str]:
    """Walk RunResult items to reconstruct the agent handoff chain."""
    from agents import HandoffCallItem, HandoffOutputItem  # noqa: PLC0415

    chain: list[str] = ["TriageAgent"]
    for item in result.new_items:
        if isinstance(item, (HandoffCallItem, HandoffOutputItem)):
            agent_name = getattr(item, "agent", None)
            if agent_name and hasattr(agent_name, "name"):
                name = agent_name.name
            else:
                name = str(agent_name) if agent_name else "Unknown"
            if name not in chain:
                chain.append(name)
    return chain
