"""
app/agents/swarm.py
────────────────────
Swarm orchestrator — builds the agent graph and exposes run_swarm().

This module is the single public interface the API route (chat.py) calls.
It owns:
  - build_swarm()  : one-time construction + SDK client wiring
  - run_swarm()    : execute a ChatRequest through the TriageAgent

Constitution compliance:
  - No MongoDB imports or connections.
  - All RunResult field access uses type_guards.
"""

from __future__ import annotations

from functools import lru_cache

from agents import Agent, Runner, RunResult, set_default_openai_client

from app.agents.triage_agent import build_triage_agent
from app.core.llm_proxy import get_openai_client
from app.core.logging import get_logger
from app.core.type_guards import ensure_str
from app.schemas.chat import AgentMetadata, AgentResponse, ChatRequest

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def build_swarm() -> Agent:
    """
    Build the full agent swarm and wire the SDK's default OpenAI client.
    Cached — called once at startup, reused for every request.
    """
    client = get_openai_client()
    set_default_openai_client(client)
    logger.info("Swarm client wired to Gemini OpenAI-compatible endpoint.")

    triage = build_triage_agent()
    logger.info("Swarm ready — entry point: %s", triage.name)
    return triage


async def run_swarm(request: ChatRequest) -> AgentResponse:
    """
    Execute a ChatRequest through the TriageAgent swarm.

    Args:
        request: Validated ChatRequest from the API layer.

    Returns:
        AgentResponse with the final output and routing metadata.
    """
    triage = build_swarm()

    # Build the input string from the last user message
    user_input = request.last_user_message
    ensure_str(user_input, "run_swarm.user_input")

    logger.info(
        "run_swarm — request_id=%s, input_len=%d",
        request.request_id,
        len(user_input),
    )

    result: RunResult = await Runner.run(
        starting_agent=triage,
        input=user_input,
        max_turns=10,
    )

    # Extract final output safely
    final_output = result.final_output
    if not isinstance(final_output, str):
        final_output = str(final_output) if final_output is not None else ""

    # Build handoff chain from the run items
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
    """
    Walk the RunResult items to reconstruct the agent handoff chain.
    Returns a list of agent names in execution order.
    """
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
