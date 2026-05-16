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

from agents import Agent, ModelSettings, handoff

from app.agents.domain_agents import build_media_agent, build_memory_agent, build_research_agent
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TRIAGE_INSTRUCTIONS = """
You are the Triage Agent — the primary entry point for all user interactions.

You have the full conversation history in your context. Use it to answer
follow-up questions directly without routing to any specialist.

Your responsibilities:
1. Handle casual conversation, greetings, simple questions, and follow-up
   questions about the current conversation DIRECTLY — do NOT hand off.
2. Route to specialists ONLY for the specific triggers listed below.

Routing rules:
- Research intent → ResearchAgent
  Triggers: "search for", "look up", "what is [external fact]", "latest news",
            weather, sports scores, current events, anything needing live web data.

- Document intent → ResearchAgent
  Triggers: "analyze this document", "read this PDF", any message with a doc_id.

- Long-term memory (EXPLICIT save/recall only) → MemoryAgent
  Triggers: ONLY when user says "remember this for next time", "save this permanently",
            "recall from our last session", "what did I tell you before", "forget that".
  DO NOT route here for: statements of fact, preferences shared in conversation,
  or questions answerable from the current chat history.

- Media intent → MediaAgent
  Triggers: "generate an image", "create a picture", "make a video", "draw", "render".

CRITICAL RULES:
- If the user says "My favorite X is Y" → respond directly, do NOT route to MemoryAgent.
- If the user asks "What is my favorite X?" and it was mentioned earlier in this
  conversation → answer directly from history, do NOT route to MemoryAgent.
- Only route to MemoryAgent when the user EXPLICITLY asks to save or retrieve
  something from a PREVIOUS session using words like "remember", "save", "recall".
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
    model = settings.active_model

    # Groq requires parallel_tool_calls=False — it doesn't support parallel calls
    # and generates malformed tool call syntax when it's enabled.
    model_settings = ModelSettings(parallel_tool_calls=False) if settings.llm_provider == "groq" else ModelSettings()

    research_agent = build_research_agent(model, mcp_servers=mcp_servers, model_settings=model_settings)
    memory_agent = build_memory_agent(model, model_settings=model_settings)
    media_agent = build_media_agent(model, model_settings=model_settings)

    h_research = handoff(
        research_agent,
        tool_description_override=(
            "Transfer to ResearchAgent for web searches, current events, "
            "factual lookups, and any question requiring up-to-date information."
        ),
    )
    h_memory = handoff(
        memory_agent,
        tool_description_override=(
            "Transfer to MemoryAgent to store or retrieve user preferences "
            "and long-term conversational context."
        ),
    )
    h_media = handoff(
        media_agent,
        tool_description_override=(
            "Transfer to MediaAgent for any image, video, or audio generation request. "
            "The job runs in the background — user can keep chatting."
        ),
    )

    # Disable strict JSON schema validation — required for Groq compatibility.
    # Groq rejects handoff tool schemas that have 'required' without 'properties'.
    for h in (h_research, h_memory, h_media):
        object.__setattr__(h, "strict_json_schema", False)

    triage = Agent(
        name="TriageAgent",
        instructions=_TRIAGE_INSTRUCTIONS,
        handoffs=[h_research, h_memory, h_media],
        model=model,
        model_settings=model_settings,
    )

    logger.info(
        "TriageAgent built — handoffs: %s",
        [h.agent_name for h in triage.handoffs],  # type: ignore[union-attr]
    )
    return triage
