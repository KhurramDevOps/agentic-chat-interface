"""
app/agents/triage_agent.py  (T023)
────────────────────────────────────
TriageAgent — the swarm entry point.

Responsibilities:
  - Handle casual conversation directly.
  - Classify intent and hand off to the appropriate domain agent.
  - Preserve conversation context across handoffs.

Handoff targets:
  - ResearchAgent : research, web search, current events, factual questions
  - MemoryAgent   : remember/recall user preferences and past context

Constitution compliance:
  - No MongoDB imports or connections.
  - All payload access uses type_guards.
"""

from __future__ import annotations

from agents import Agent, handoff

from app.agents.domain_agents import build_media_agent, build_memory_agent, build_research_agent
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TRIAGE_INSTRUCTIONS = """
You are the Triage Agent — the primary entry point for all user interactions.

The user's session_id is always provided at the start of their message in the
format [session_id: <id>]. Pass this through to specialist agents unchanged.

Your responsibilities:
1. Handle casual conversation, greetings, and simple questions directly.
2. Detect user intent and route to the correct specialist agent when needed.

Routing rules (use handoffs — do NOT answer these yourself):
- Research intent  → transfer to ResearchAgent
  Triggers: questions about current events, news, facts, "search for", "look up",
            "what is", "who is", "when did", "how does", weather, sports scores,
            any topic requiring up-to-date information.
- Document intent  → transfer to ResearchAgent
  Triggers: "analyze this document", "read this PDF", "summarize this doc",
            "what does this document say", any message containing a doc_id,
            any request to analyze, read, or summarize a document or PDF.
- Memory intent    → transfer to MemoryAgent
  Triggers: "remember", "recall", "what did I say", "save this", "forget",
            "my preferences", "last time we talked", "what do you know about me",
            "what are my projects", any question about past context or preferences.
- Media intent     → transfer to MediaAgent
  Triggers: "generate an image", "create a picture", "make a video",
            "draw", "illustrate", "render", "produce audio", "generate media",
            any request to create visual or audio content.

When handing off:
- Pass the full user message (including the [session_id: ...] prefix) to the specialist.
- Do not attempt to answer research, document, memory, or media questions yourself.

For everything else (greetings, opinions, creative writing, coding help):
- Respond directly and helpfully.
""".strip()


def build_triage_agent(mcp_servers: list | None = None) -> Agent:
    """
    Construct the TriageAgent with handoffs to all domain agents.
    Called once at app startup via build_swarm().

    Args:
        mcp_servers: MCP server instances from MCPManager, injected into
                     the ResearchAgent for real web search capability.
    """
    settings = get_settings()
    model = settings.litellm_model

    research_agent = build_research_agent(model, mcp_servers=mcp_servers)
    memory_agent = build_memory_agent(model)
    media_agent = build_media_agent(model)

    triage = Agent(
        name="TriageAgent",
        instructions=_TRIAGE_INSTRUCTIONS,
        handoffs=[
            handoff(
                research_agent,
                tool_description_override=(
                    "Transfer to ResearchAgent for web searches, current events, "
                    "factual lookups, and any question requiring up-to-date information."
                ),
            ),
            handoff(
                memory_agent,
                tool_description_override=(
                    "Transfer to MemoryAgent to store or retrieve user preferences "
                    "and long-term conversational context."
                ),
            ),
            handoff(
                media_agent,
                tool_description_override=(
                    "Transfer to MediaAgent for any image, video, or audio generation request. "
                    "The job runs in the background — user can keep chatting."
                ),
            ),
        ],
        model=model,
    )

    logger.info(
        "TriageAgent built — handoffs: %s",
        [h.agent_name for h in triage.handoffs],  # type: ignore[union-attr]
    )
    return triage
