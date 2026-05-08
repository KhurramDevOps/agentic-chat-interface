"""
app/agents/domain_agents.py  (T022 / T030)
───────────────────────────────────────────
ResearchAgent, MemoryAgent, and MediaAgent domain specialists.

ResearchAgent  — web search (mocked; real MCP tool in Phase 6+)
MemoryAgent    — mem0 read/write for local agentic context
MediaAgent     — dispatches non-blocking background media generation jobs

Constitution compliance:
  - No MongoDB imports or connections.
  - All dict/payload access goes through type_guards before key access.
  - MediaAgent MUST NOT block — generate_media dispatches and returns immediately.
"""

from __future__ import annotations

from agents import Agent, function_tool

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.type_guards import ensure_dict, ensure_str, safe_get

logger = get_logger(__name__)


# ── ResearchAgent tools ───────────────────────────────────────────────────────

@function_tool
def web_search(query: str) -> str:
    """
    Search the web for current information about a topic.

    Args:
        query: The search query string.

    Returns:
        A plain-text summary of the top search results.
    """
    ensure_str(query, "web_search.query")
    logger.info("web_search called — query=%r", query)

    # Phase 4: mocked response. Real MCP/Brave integration in Phase 5+.
    return (
        f"[Mock web search results for: '{query}']\n"
        "1. Wikipedia: General overview of the topic.\n"
        "2. News source: Recent developments as of today.\n"
        "3. Academic source: Peer-reviewed findings.\n"
        "Note: This is a mock response. Real search integration is in Phase 5."
    )


@function_tool
def deep_research(topic: str, max_sources: int = 3) -> str:
    """
    Perform deep research on a topic by scraping multiple sources.

    Args:
        topic:       The research topic.
        max_sources: Maximum number of sources to consult (default 3).

    Returns:
        A synthesised research summary.
    """
    ensure_str(topic, "deep_research.topic")
    logger.info("deep_research called — topic=%r, max_sources=%d", topic, max_sources)

    return (
        f"[Mock deep research on: '{topic}' — {max_sources} sources]\n"
        "Synthesis: This topic has been studied extensively. "
        "Key findings include multiple perspectives and ongoing debates. "
        "Note: This is a mock response. Real scraping integration is in Phase 5."
    )


# ── MemoryAgent tools ─────────────────────────────────────────────────────────

@function_tool
def add_memory(context_id: str, content: str) -> str:
    """
    Store a piece of information in the user's long-term memory.

    Args:
        context_id: The conversation or user context bucket identifier.
        content:    The information to remember.

    Returns:
        Confirmation message with the stored content summary.
    """
    ensure_str(context_id, "add_memory.context_id")
    ensure_str(content, "add_memory.content")

    if not content.strip():
        return "Error: content cannot be empty."

    settings = get_settings()

    try:
        if settings.mem0_use_local:
            # Local in-memory mode — no API key required
            logger.info(
                "add_memory (local) — context_id=%r, content_len=%d",
                context_id,
                len(content),
            )
            # In local mode we acknowledge without persisting to external store
            return f"Memory stored (local mode) for context '{context_id}': {content[:80]}..."
        else:
            from mem0 import MemoryClient  # type: ignore[import-untyped]
            client = MemoryClient(api_key=settings.mem0_api_key)
            result = client.add(
                messages=[{"role": "user", "content": content}],
                user_id=context_id,
            )
            ensure_dict(result, "mem0.add result")
            memory_id = safe_get(result, "id", default="unknown")
            logger.info("add_memory (cloud) — memory_id=%s", memory_id)
            return f"Memory stored with id '{memory_id}' for context '{context_id}'."
    except Exception as exc:
        logger.warning("add_memory failed — %s", exc)
        return f"Memory storage encountered an error: {exc}"


@function_tool
def search_memory(context_id: str, query: str) -> str:
    """
    Retrieve relevant memories for a given context and query.

    Args:
        context_id: The conversation or user context bucket identifier.
        query:      Natural-language query to search stored memories.

    Returns:
        Relevant memory entries as a formatted string.
    """
    ensure_str(context_id, "search_memory.context_id")
    ensure_str(query, "search_memory.query")

    settings = get_settings()

    try:
        if settings.mem0_use_local:
            logger.info(
                "search_memory (local) — context_id=%r, query=%r",
                context_id,
                query,
            )
            return (
                f"[Local memory search for context '{context_id}', query='{query}']\n"
                "No persistent memories found in local mode. "
                "Set MEM0_API_KEY to enable cloud memory."
            )
        else:
            from mem0 import MemoryClient  # type: ignore[import-untyped]
            client = MemoryClient(api_key=settings.mem0_api_key)
            results = client.search(query=query, user_id=context_id)

            if not isinstance(results, list) or not results:
                return f"No memories found for context '{context_id}'."

            lines = []
            for i, item in enumerate(results[:5], 1):
                ensure_dict(item, f"mem0.search result[{i}]")
                memory_text = safe_get(item, "memory", default="(no content)")
                lines.append(f"{i}. {memory_text}")

            return "\n".join(lines)
    except Exception as exc:
        logger.warning("search_memory failed — %s", exc)
        return f"Memory retrieval encountered an error: {exc}"


# ── Agent definitions ─────────────────────────────────────────────────────────

def build_research_agent(model: str) -> Agent:
    """Construct and return the ResearchAgent."""
    return Agent(
        name="ResearchAgent",
        handoff_description=(
            "Specialist for web search, current events, factual lookups, "
            "and deep research on any topic."
        ),
        instructions=(
            "You are a research specialist. Use your web_search and deep_research "
            "tools to find accurate, up-to-date information. "
            "Always cite your sources and present findings clearly. "
            "When research is complete, provide a comprehensive summary."
        ),
        tools=[web_search, deep_research],
        model=model,
    )


def build_memory_agent(model: str) -> Agent:
    """Construct and return the MemoryAgent."""
    return Agent(
        name="MemoryAgent",
        handoff_description=(
            "Specialist for storing and retrieving user preferences, "
            "past conversation context, and long-term memory."
        ),
        instructions=(
            "You are a memory specialist. Use add_memory to store important "
            "information the user wants remembered, and search_memory to recall "
            "relevant context. Always confirm what was stored or retrieved. "
            "Never store sensitive credentials or PII."
        ),
        tools=[add_memory, search_memory],
        model=model,
    )


# ── MediaAgent tools (T030) ───────────────────────────────────────────────────

@function_tool
def generate_media(
    client_id: str,
    request_id: str,
    prompt: str,
    job_type: str = "image",
) -> str:
    """
    Dispatch a non-blocking media generation job and return an acknowledgment.

    CRITICAL: This tool MUST NOT await the actual generation. It dispatches
    the job to the background worker and returns immediately so the user
    can continue chatting while the job runs.

    Args:
        client_id:  WebSocket client_id to push the completion event to.
        request_id: Originating chat request ID for correlation.
        prompt:     Description of the media to generate.
        job_type:   "image" | "video" | "audio" (default: "image")

    Returns:
        Acknowledgment string with the task_id.
    """
    from app.schemas.streaming import JobType  # noqa: PLC0415
    from app.workers.media_worker import dispatch_media_job  # noqa: PLC0415

    ensure_str(client_id, "generate_media.client_id")
    ensure_str(request_id, "generate_media.request_id")
    ensure_str(prompt, "generate_media.prompt")
    ensure_str(job_type, "generate_media.job_type")

    # Validate job_type
    try:
        jt = JobType(job_type.lower())
    except ValueError:
        jt = JobType.IMAGE

    task_id = dispatch_media_job(
        client_id=client_id,
        request_id=request_id,
        job_type=jt,
        input_payload={"prompt": prompt, "job_type": jt.value},
    )

    logger.info(
        "generate_media dispatched — task_id=%s, client_id=%s, job_type=%s",
        task_id, client_id, jt.value,
    )
    return (
        f"Media generation started! Task ID: {task_id}. "
        f"You'll receive the {jt.value} via WebSocket when it's ready. "
        "Feel free to keep chatting in the meantime."
    )


def build_media_agent(model: str) -> Agent:
    """Construct and return the MediaAgent."""
    return Agent(
        name="MediaAgent",
        handoff_description=(
            "Specialist for generating images, videos, and audio. "
            "Dispatches jobs asynchronously so the user can keep chatting."
        ),
        instructions=(
            "You are a media generation specialist. "
            "When the user requests an image, video, or audio, call generate_media "
            "with the user's client_id, request_id, their prompt, and the job_type. "
            "Always confirm the task has been dispatched and tell the user they will "
            "receive the result via WebSocket when generation completes. "
            "NEVER wait for the generation to finish before responding."
        ),
        tools=[generate_media],
        model=model,
    )
