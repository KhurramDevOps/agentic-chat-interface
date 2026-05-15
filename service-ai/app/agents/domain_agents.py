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
def tavily_search(query: str) -> str:
    """
    Search the web for current, accurate information using Tavily Search.

    Args:
        query: The search query string.

    Returns:
        A plain-text summary of the top search results with sources.
    """
    ensure_str(query, "tavily_search.query")
    logger.info("tavily_search called — query=%r", query)

    settings = get_settings()

    if not settings.tavily_api_key:
        logger.warning("TAVILY_API_KEY not set — returning mock search result.")
        return (
            f"[Mock search results for: '{query}']\n"
            "Note: Set TAVILY_API_KEY in .env to enable real web search."
        )

    try:
        from tavily import TavilyClient  # type: ignore[import-untyped]
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(query=query, max_results=5)

        results = response.get("results", [])
        if not results:
            return f"No results found for query: '{query}'"

        lines = [f"Search results for: '{query}'\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            url = r.get("url", "")
            content = r.get("content", "")[:300]
            lines.append(f"{i}. {title}\n   {url}\n   {content}\n")

        return "\n".join(lines)
    except Exception as exc:
        logger.warning("tavily_search failed — %s", exc)
        return f"Search encountered an error: {exc}"


# ── Document analysis tool (Phase 6) ─────────────────────────────────────────

@function_tool
def analyze_document(doc_id: str, query: str) -> str:
    """
    Retrieve an uploaded document from the in-memory store and return its
    content as context for answering a query.

    Args:
        doc_id: UUID returned by the /files/upload endpoint.
        query:  The user's question or analysis request about the document.

    Returns:
        Formatted string with document context and the query for the LLM to answer.
    """
    from app.services.file_service import get_document_store  # noqa: PLC0415

    ensure_str(doc_id, "analyze_document.doc_id")
    ensure_str(query, "analyze_document.query")

    store = get_document_store()
    text = store.get_document(doc_id)

    if text is None:
        return (
            f"Error: No document found with doc_id='{doc_id}'. "
            "Please upload a PDF first using the /api/v1/files/upload endpoint "
            "and use the returned doc_id."
        )

    # Truncate to protect the LiteLLM context window
    _MAX_CHARS = 15_000
    truncated = text[:_MAX_CHARS]
    was_truncated = len(text) > _MAX_CHARS

    suffix = "... [truncated]" if was_truncated else ""
    logger.info(
        "analyze_document — doc_id=%s, chars=%d, truncated=%s",
        doc_id, len(text), was_truncated,
    )

    return (
        f"Document context:\n{truncated}{suffix}\n\n"
        f"Please analyze this context to answer: {query}"
    )


# ── MemoryAgent tools ─────────────────────────────────────────────────────────

def _add_memory_impl(context_id: str, content: str) -> str:
    """Raw implementation — testable without the @function_tool wrapper."""
    ensure_str(context_id, "add_memory.context_id")
    ensure_str(content, "add_memory.content")

    if not content.strip():
        return "Error: content cannot be empty."

    settings = get_settings()

    try:
        if settings.mem0_use_local:
            logger.info(
                "add_memory (local) — context_id=%r, content_len=%d",
                context_id,
                len(content),
            )
            return f"Memory stored (local mode) for context '{context_id}': {content[:80]}..."
        else:
            from mem0 import MemoryClient  # type: ignore[import-untyped]
            client = MemoryClient(api_key=settings.mem0_api_key)
            result = client.add(
                messages=[{"role": "user", "content": content}],
                user_id=context_id,
            )
            # mem0 v2 returns {"event_id": ..., "status": "PENDING"}
            # mem0 v1 returns a list of dicts with "id"
            if isinstance(result, dict):
                memory_id = result.get("event_id", result.get("id", "stored"))
            elif isinstance(result, list) and result:
                memory_id = result[0].get("id", "stored") if isinstance(result[0], dict) else "stored"
            else:
                memory_id = "stored"
            logger.info("add_memory (cloud) — memory_id=%s, context_id=%s", memory_id, context_id)
            return f"Memory stored with id '{memory_id}' for context '{context_id}'."
    except Exception as exc:
        logger.warning("add_memory failed — %s", exc)
        return f"Memory storage encountered an error: {exc}"


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
    return _add_memory_impl(context_id=context_id, content=content)


def _search_memory_impl(context_id: str, query: str) -> str:
    """Raw implementation — testable without the @function_tool wrapper."""
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
            # mem0 v2: user_id must be passed via filters, not as top-level param
            raw = client.search(query=query, filters={"user_id": context_id})

            # mem0 v2+ returns {"results": [...], "relations": [...]}
            # older versions return a plain list
            if isinstance(raw, dict):
                results = raw.get("results", [])
            elif isinstance(raw, list):
                results = raw
            else:
                results = []

            logger.info(
                "search_memory (cloud) — context_id=%r, query=%r, found=%d",
                context_id, query, len(results),
            )

            if not results:
                return f"No memories found for context '{context_id}'."

            lines = []
            for i, item in enumerate(results[:5], 1):
                if isinstance(item, dict):
                    memory_text = item.get("memory", item.get("text", "(no content)"))
                else:
                    memory_text = str(item)
                lines.append(f"{i}. {memory_text}")

            return "\n".join(lines)
    except Exception as exc:
        logger.warning("search_memory failed — context_id=%r, error=%s", context_id, exc, exc_info=True)
        return f"Memory retrieval encountered an error: {exc}"


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
    return _search_memory_impl(context_id=context_id, query=query)


# ── Agent definitions ─────────────────────────────────────────────────────────

def build_research_agent(model: str, mcp_servers: list | None = None) -> Agent:
    """
    Construct and return the ResearchAgent.

    Args:
        model:       Model name for this agent.
        mcp_servers: List of MCPServerStdio instances injected at runtime
                     from MCPManager. Falls back to built-in mock tools
                     when no MCP servers are configured.
    """
    # Use MCP servers when available; fall back to mock tools for dev/test
    if mcp_servers:
        return Agent(
            name="ResearchAgent",
            handoff_description=(
                "Specialist for web search, current events, factual lookups, "
                "deep research, and analyzing uploaded PDF documents."
            ),
            instructions=(
                "You are a research specialist with access to Tavily's search and "
                "extraction tools. Use tavily_search to find accurate, up-to-date "
                "information and tavily_extract to pull detailed content from specific URLs. "
                "Use analyze_document when the user provides a doc_id to analyze an uploaded PDF. "
                "Always cite your sources and present findings clearly. "
                "When research is complete, provide a comprehensive summary."
            ),
            mcp_servers=mcp_servers,
            tools=[analyze_document],
            model=model,
        )
    else:
        # Fallback: built-in Python tools (no MCP configured)
        return Agent(
            name="ResearchAgent",
            handoff_description=(
                "Specialist for web search, current events, factual lookups, "
                "deep research, and analyzing uploaded PDF documents."
            ),
            instructions=(
                "You are a research specialist. Use tavily_search to find accurate, "
                "up-to-date information from the web. "
                "Use analyze_document when the user provides a doc_id to analyze an uploaded PDF. "
                "Always cite your sources and present findings clearly. "
                "When research is complete, provide a comprehensive summary."
            ),
            tools=[tavily_search, analyze_document],
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
            "You are a memory specialist. The user's session_id is always provided "
            "at the start of their message in the format [session_id: <id>]. "
            "You MUST extract this session_id and use it as the context_id in ALL tool calls.\n\n"
            "Rules you MUST follow:\n"
            "1. When storing information: call add_memory with the session_id as context_id "
            "and the information as content.\n"
            "2. When the user asks about past projects, preferences, or 'what you know about me': "
            "you MUST call search_memory FIRST before providing any response. "
            "Never answer from memory without calling the tool.\n"
            "3. Always confirm what was stored or retrieved.\n"
            "4. Never store sensitive credentials or PII.\n"
            "5. If search_memory returns no results, tell the user honestly that "
            "no memories were found for their session."
        ),
        tools=[add_memory, search_memory],
        model=model,
    )


# ── MediaAgent tools (T030) ───────────────────────────────────────────────────

@function_tool
def generate_media(
    prompt: str,
    client_id: str = "",
    request_id: str = "",
    job_type: str = "image",
) -> str:
    """
    Dispatch a non-blocking image generation job via Pollinations.ai.

    Returns immediately with a task_id and the direct image URL.
    If a WebSocket client_id is provided, a background_update event will
    be pushed to that client when the job completes.

    Args:
        prompt:     Description of the image to generate.
        client_id:  WebSocket client_id to push the completion event to (optional).
        request_id: Originating chat request ID for correlation (optional).
        job_type:   "image" | "video" | "audio" (default: "image")

    Returns:
        Acknowledgment string with the task_id and direct image URL.
    """
    import urllib.parse  # noqa: PLC0415

    from app.schemas.streaming import JobType  # noqa: PLC0415
    from app.workers.media_worker import dispatch_media_job  # noqa: PLC0415

    ensure_str(prompt, "generate_media.prompt")

    # Validate job_type
    try:
        jt = JobType(job_type.lower())
    except ValueError:
        jt = JobType.IMAGE

    # Build the Pollinations URL immediately — no waiting needed
    encoded_prompt = urllib.parse.quote(prompt)
    image_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=1024&height=1024&nologo=true"
    )

    # Dispatch background job only if a WebSocket client is connected
    effective_client_id = client_id or "no-ws-client"
    effective_request_id = request_id or "no-request-id"

    task_id = dispatch_media_job(
        client_id=effective_client_id,
        request_id=effective_request_id,
        job_type=jt,
        input_payload={"prompt": prompt, "job_type": jt.value, "url": image_url},
    )

    logger.info(
        "generate_media dispatched — task_id=%s, client_id=%s, job_type=%s",
        task_id, effective_client_id, jt.value,
    )
    return (
        f"Your image is being generated! Here is the direct link:\n\n"
        f"{image_url}\n\n"
        f"Task ID: {task_id}. The image will render once Pollinations processes it "
        f"(usually within a few seconds). "
        f"{'A WebSocket notification will be sent when ready.' if client_id else ''}"
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
            "You are a media generation specialist using Pollinations.ai. "
            "When the user requests an image, call generate_media with their prompt. "
            "The tool returns a direct image URL immediately — share it with the user. "
            "You do NOT need client_id or request_id — just pass the prompt. "
            "Always confirm the image URL has been generated and share it directly in your response."
        ),
        tools=[generate_media],
        model=model,
    )
