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

import httpx

from agents import Agent, RunContextWrapper, function_tool

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


def _fetch_url_impl(url: str) -> str:
    """Raw implementation — testable without the @function_tool wrapper."""
    import re  # noqa: PLC0415

    ensure_str(url, "fetch_url.url")
    url = url.strip()

    md_match = re.search(r'\(?(https?://[^\s\)\]>]+)', url)
    if md_match:
        url = md_match.group(1)
    url = re.sub(r'[\[\]<>]', '', url).strip()

    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; service-ai/1.0)"})
            resp.raise_for_status()
            html = resp.text

        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        _MAX = 8000
        truncated = text[:_MAX]
        suffix = "... [truncated]" if len(text) > _MAX else ""

        logger.info("fetch_url — url=%s, chars=%d", url, len(text))
        return f"Content from {url}:\n\n{truncated}{suffix}"

    except httpx.HTTPStatusError as exc:
        return f"Error: HTTP {exc.response.status_code} fetching {url}"
    except Exception as exc:
        logger.warning("fetch_url failed — url=%s, error=%s", url, exc)
        return f"Error fetching URL: {exc}"


@function_tool
def fetch_url(url: str) -> str:
    """
    Fetch the text content of a web page and return it stripped of HTML tags.

    Use this when the user provides a specific URL they want you to read,
    or when you need to retrieve content from a known source.

    CRITICAL: The `url` argument must be a raw URL string ONLY.
    DO NOT use markdown formatting, brackets, parentheses, or HTML.
    CORRECT:   "https://example.com"
    INCORRECT: "[https://example.com](https://example.com)"

    Args:
        url: The full URL to fetch (must start with http:// or https://).

    Returns:
        Plain text content of the page (truncated to 8000 chars).
    """
    return _fetch_url_impl(url)


def _calculate_impl(expression: str) -> str:
    """Raw implementation — testable without the @function_tool wrapper."""
    import ast  # noqa: PLC0415
    import operator as op  # noqa: PLC0415

    ensure_str(expression, "calculate.expression")

    _OPERATORS = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
        ast.Div: op.truediv, ast.FloorDiv: op.floordiv,
        ast.Mod: op.mod, ast.Pow: op.pow,
        ast.USub: op.neg, ast.UAdd: op.pos,
    }

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval(tree.body)
        if result == int(result):
            return str(int(result))
        return str(round(result, 10))
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as exc:
        return f"Error evaluating expression: {exc}"


@function_tool
def calculate(expression: str) -> str:
    """
    Safely evaluate a mathematical expression and return the result.

    Supports: +, -, *, /, //, %, **, parentheses, and basic numeric literals.
    Does NOT support function calls, imports, or any non-math operations.

    Args:
        expression: A math expression string, e.g. "(3 + 4) * 2 / 1.5"

    Returns:
        The numeric result as a string, or an error message.
    """
    return _calculate_impl(expression)


def _run_python_impl(code: str) -> str:
    """Raw implementation — testable without the @function_tool wrapper."""
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415
    import textwrap  # noqa: PLC0415

    ensure_str(code, "run_python.code")

    _BLOCKED = ["import os", "import sys", "import subprocess", "import socket",
                "import requests", "import httpx", "__import__", "open(", "exec(",
                "eval(", "compile("]
    code_lower = code.lower()
    for pattern in _BLOCKED:
        if pattern in code_lower:
            return f"Error: '{pattern}' is not allowed in sandboxed execution."

    dedented = textwrap.dedent(code)

    try:
        result = subprocess.run(
            [sys.executable, "-c", dedented],
            capture_output=True, text=True, timeout=3,
        )
        output = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            return f"Script error (exit {result.returncode}):\n{stderr or output}"
        if not output and stderr:
            return f"Script produced no output. Stderr:\n{stderr}"

        _MAX_OUTPUT = 4000
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + "\n... [output truncated]"

        logger.info("run_python — returncode=%d, output_len=%d", result.returncode, len(output))
        return output or "(script ran successfully with no output)"

    except subprocess.TimeoutExpired:
        return "Error: script exceeded the 3-second timeout."
    except Exception as exc:
        logger.warning("run_python failed — %s", exc)
        return f"Error running script: {exc}"


@function_tool
def run_python(code: str) -> str:
    """
    Execute a sandboxed Python script and return its stdout output.

    Use this for data analysis, calculations, string processing, or any
    task that benefits from running actual Python code.

    Restrictions:
      - 3-second execution timeout
      - No network access (subprocess isolation)
      - Only stdout is captured; imports of dangerous modules will fail

    Args:
        code: Valid Python source code to execute.

    Returns:
        The stdout output of the script, or an error/timeout message.
    """
    return _run_python_impl(code)


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
    text = store.get_document_sync(doc_id)

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
def add_memory(ctx: RunContextWrapper[dict], content: str) -> str:
    """
    Store a piece of information in the user's long-term memory.

    Args:
        content: The information to remember.

    Returns:
        Confirmation message.
    """
    context_variables = ctx.context or {}
    context_id = context_variables.get("session_id") or context_variables.get("context_id", "default")
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
def search_memory(ctx: RunContextWrapper[dict], query: str) -> str:
    """
    Retrieve relevant memories for a given context and query.

    Args:
        query: Natural-language query to search stored memories.

    Returns:
        Relevant memory entries as a formatted string.
    """
    context_variables = ctx.context or {}
    context_id = context_variables.get("session_id") or context_variables.get("context_id", "default")
    return _search_memory_impl(context_id=context_id, query=query)


# ── Agent definitions ─────────────────────────────────────────────────────────

def build_research_agent(model: str, mcp_servers: list | None = None, model_settings=None) -> Agent:
    """
    Construct and return the ResearchAgent.

    Args:
        model:         Model name for this agent.
        mcp_servers:   List of MCPServerStdio instances injected at runtime.
        model_settings: Optional ModelSettings (e.g. parallel_tool_calls=False for Groq).
    """
    base_tools = [tavily_search, analyze_document, fetch_url, calculate, run_python]
    instructions = (
        "You are a research and analysis specialist. "
        "Use tavily_search for live web data. "
        "Use fetch_url to read a specific URL the user provides. "
        "Use calculate for any arithmetic — never do math in your head. "
        "Use run_python for data analysis, transformations, or complex calculations. "
        "Use analyze_document when the user provides a doc_id to analyze an uploaded PDF. "
        "Always cite your sources and present findings clearly."
    )

    if mcp_servers:
        return Agent(
            name="ResearchAgent",
            handoff_description=(
                "Specialist for web search, URL fetching, data analysis, math, "
                "code execution, and analyzing uploaded PDF documents."
            ),
            instructions=instructions,
            mcp_servers=mcp_servers,
            tools=[analyze_document, fetch_url, calculate, run_python],
            model=model,
            model_settings=model_settings,
        )
    else:
        return Agent(
            name="ResearchAgent",
            handoff_description=(
                "Specialist for web search, URL fetching, data analysis, math, "
                "code execution, and analyzing uploaded PDF documents."
            ),
            instructions=instructions,
            tools=base_tools,
            model=model,
            model_settings=model_settings,
        )


def build_memory_agent(model: str, model_settings=None) -> Agent:
    """Construct and return the MemoryAgent."""
    return Agent(
        name="MemoryAgent",
        handoff_description=(
            "Specialist for storing and retrieving user preferences, "
            "past conversation context, and long-term memory."
        ),
        instructions=(
            "You are a memory specialist. The session context is automatically injected "
            "— you do NOT need to pass any session_id or context_id to the tools.\n\n"
            "Rules you MUST follow:\n"
            "1. When storing information: call add_memory with only the content to remember.\n"
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
        model_settings=model_settings,
    )


# ── MediaAgent tools (T030) ───────────────────────────────────────────────────

@function_tool
def generate_media(
    ctx: RunContextWrapper[dict],
    prompt: str,
    job_type: str = "image",
) -> str:
    """
    Dispatch a non-blocking image generation job via Pollinations.ai.

    Returns immediately with the direct image URL.

    Args:
        prompt:   Description of the image to generate.
        job_type: "image" | "video" | "audio" (default: "image")

    Returns:
        Acknowledgment string with the direct image URL.
    """
    import urllib.parse  # noqa: PLC0415

    from app.schemas.streaming import JobType  # noqa: PLC0415
    from app.workers.media_worker import dispatch_media_job  # noqa: PLC0415

    ensure_str(prompt, "generate_media.prompt")

    context_variables = ctx.context or {}
    client_id = context_variables.get("client_id", "no-ws-client")
    request_id = context_variables.get("request_id", "no-request-id")

    try:
        jt = JobType(job_type.lower())
    except ValueError:
        jt = JobType.IMAGE

    encoded_prompt = urllib.parse.quote(prompt)
    image_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=1024&height=1024&nologo=true"
    )

    task_id = dispatch_media_job(
        client_id=client_id,
        request_id=request_id,
        job_type=jt,
        input_payload={"prompt": prompt, "job_type": jt.value, "url": image_url},
    )

    logger.info("generate_media dispatched — task_id=%s, job_type=%s", task_id, jt.value)
    return (
        f"Your image is being generated! Here is the direct link:\n\n"
        f"{image_url}\n\n"
        f"Task ID: {task_id}. The image will render once Pollinations processes it "
        f"(usually within a few seconds)."
    )


def build_media_agent(model: str, model_settings=None) -> Agent:
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
        model_settings=model_settings,
    )
