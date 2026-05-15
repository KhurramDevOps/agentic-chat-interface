"""
app/agents/swarm.py
────────────────────
Swarm orchestrator — builds the agent graph and exposes run_swarm().

The SDK's Runner handles MCP tool calls natively when MCPServerStdio
instances are passed to Agent(mcp_servers=...). No custom tool-call loop
is needed here.

Constitution compliance:
  - No MongoDB imports or connections.
  - All RunResult field access uses type_guards.
"""

from __future__ import annotations

from agents import Agent, Runner, RunResult, set_default_openai_client

from app.agents.triage_agent import build_triage_agent
from app.core.llm_proxy import get_openai_client
from app.core.logging import get_logger
from app.core.type_guards import ensure_str
from app.schemas.chat import AgentMetadata, AgentResponse, ChatRequest

logger = get_logger(__name__)

# Module-level reference to the built swarm — set once by initialise_swarm()
_triage_agent: Agent | None = None


async def initialise_swarm() -> Agent:
    """
    Build the full agent swarm, wire the SDK client, and inject MCP servers.
    Called once from the FastAPI lifespan startup handler.
    Idempotent — returns the cached agent on subsequent calls.
    """
    global _triage_agent
    if _triage_agent is not None:
        return _triage_agent

    # Wire the Gemini OpenAI-compatible client
    client = get_openai_client()
    set_default_openai_client(client)
    logger.info("Swarm client wired to Gemini OpenAI-compatible endpoint.")

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

    # Build the input as a list of OpenAI-style message dicts.
    # Prepend a system message with the session_id so memory tools
    # always have access to it without polluting the user message.
    system_msg = {
        "role": "system",
        "content": f"session_id: {context_id}. Use this as context_id in all memory tool calls.",
    }

    history_msgs = [
        {"role": msg.role, "content": msg.content}
        for msg in request.messages
    ]

    input_messages = [system_msg] + history_msgs

    logger.info(
        "run_swarm — request_id=%s, input_len=%d, context_id=%s, history_turns=%d",
        request.request_id,
        len(user_input),
        context_id,
        len(request.messages),
    )

    result: RunResult = await Runner.run(
        starting_agent=triage,
        input=input_messages,
        max_turns=10,
    )

    final_output = result.final_output
    if not isinstance(final_output, str):
        final_output = str(final_output) if final_output is not None else ""

    last_agent: Agent = result.last_agent
    handoff_chain = _extract_handoff_chain(result)
    handoff_occurred = len(handoff_chain) > 1

    logger.info(
        "run_swarm complete — last_agent=%s, handoff=%s, turns=%d",
        last_agent.name,
        handoff_occurred,
        result._current_turn,
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
        model=request.model,
    )


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
