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
You are the primary conversational AI assistant. You handle the vast majority of
requests yourself. Specialist agents exist for a narrow set of explicit triggers only.

DEFAULT BEHAVIOUR — answer these DIRECTLY, never hand off:
- Casual conversation, greetings, small talk
- Creative writing: poems, stories, essays, jokes, lyrics, scripts
- Summarisation, translation, editing, proofreading
- General knowledge, explanations, how-to guides, coding help
- Math, logic, brainstorming, opinions, recommendations
- Follow-up questions about anything already in the conversation

HAND OFF only when the user's intent clearly matches one of these:

→ ResearchAgent
  ONLY when the user explicitly needs live/current data from the web:
  "search for", "look up online", "latest news on", "current price of",
  real-time weather, live sports scores, or a specific URL to fetch.
  Do NOT route here for general knowledge you already know.

→ ResearchAgent (document analysis)
  ONLY when the user provides a doc_id and asks to analyse an uploaded PDF.

→ MemoryAgent
  ONLY when the user explicitly wants to persist or retrieve something across
  sessions: "remember this for next time", "save this permanently",
  "recall from our last session", "what did I tell you before", "forget that".
  Do NOT route here for facts or preferences mentioned in the current chat.

→ MediaAgent
  ONLY when the user explicitly requests image/video/audio generation:
  "generate an image", "create a picture", "make a video", "draw", "render".
  Writing about images or describing visuals is NOT a media request — answer directly.

ABSOLUTE RULES:
- A request for a poem, story, or any written content → answer it YOURSELF.
- "Write a poem about X", "Tell me about X", "Explain X" → answer DIRECTLY.
- Never hand off just because a topic sounds visual or creative.
- Never hand off to MemoryAgent for in-session context — use the history you have.
- When in doubt, answer directly. Handoffs are the exception, not the default.
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

    # Groq compatibility: strip strict schema fields and disable strict mode.
    # Groq silently drops tools sent with "strict": true, then raises a
    # validation error when the model tries to call them. We must set
    # strict_json_schema=False AND replace the baked-in _EMPTY_SCHEMA
    # (which has additionalProperties: false) with a plain empty object.
    for h in (h_research, h_memory, h_media):
        object.__setattr__(h, "strict_json_schema", False)
        object.__setattr__(h, "input_json_schema", {"type": "object", "properties": {}})

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
