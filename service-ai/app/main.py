"""
app/main.py
───────────
FastAPI application factory and lifespan manager for service-ai.

Responsibilities:
  - Create and configure the FastAPI app instance.
  - Run startup validation (settings, constitution checks).
  - Register all API routers.
  - Expose the ASGI app for `uv run uvicorn app.main:app`.

Constitution compliance:
  - No MongoDB imports or connections anywhere in this file.
  - All long-running work is deferred to background tasks (not here).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

# Load .env before any app module imports so all env vars are available
# at module-load time (critical for MCPManager, Settings, etc.)
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from groq import AsyncGroq
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

# ── Rate limiter (slowapi, in-memory, no Redis needed) ────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])


def _extract_stream_delta(chunk: Any) -> str:
    """Return streamed text from a LiteLLM/OpenAI-compatible chunk."""
    try:
        return chunk.choices[0].delta.content or ""
    except (AttributeError, IndexError, TypeError):
        pass

    try:
        return chunk["choices"][0]["delta"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _extract_message_content(response: Any) -> str:
    """Return text from a non-streaming LiteLLM/OpenAI-compatible response."""
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError):
        pass

    try:
        return response["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _heuristic_memory(user_message: str, current_memory: dict[str, Any]) -> dict[str, Any]:
    """Small deterministic fallback so obvious personal facts persist even if extraction fails."""
    text = user_message.strip()
    memory = {
        "name": current_memory.get("name", ""),
        "nickname": current_memory.get("nickname", ""),
        "occupation": current_memory.get("occupation", ""),
        "location": current_memory.get("location", ""),
        "facts": list(current_memory.get("facts") or []),
    }

    name_match = re.search(r"\b(?:my name is|i am|i'm)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})", text)
    if name_match:
        candidate = name_match.group(1).strip(" .,!?:;")
        if len(candidate.split()) <= 4:
            memory["name"] = candidate

    location_match = re.search(r"\b(?:i live in|i am from|i'm from|my location is)\s+([^.!?\n]+)", text, re.I)
    if location_match:
        memory["location"] = location_match.group(1).strip(" .,!?:;")

    fact_patterns = [
        r"\b(?:i work as|i am a|i'm a|my profession is)\s+([^.!?\n]+)",
        r"\b(?:i like|i prefer|my favorite|my favourite)\s+([^.!?\n]+)",
        r"\b(?:i use|my stack is|my tech stack is)\s+([^.!?\n]+)",
    ]
    facts = set(memory["facts"])
    for pattern in fact_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            fact = match.group(0).strip(" .,!?:;")
            if 4 <= len(fact) <= 160:
                facts.add(fact[0].upper() + fact[1:])
            if "work as" in match.group(0).lower() or "profession" in match.group(0).lower():
                memory["occupation"] = match.group(1).strip(" .,!?:;")

    memory["facts"] = list(facts)[:30]
    return memory


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _duckduckgo_search(query: str) -> list[dict[str, str]]:
    def run_search() -> list[dict[str, str]]:
        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        })
        url = f"https://api.duckduckgo.com/?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "NexusChat/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8", errors="ignore"))

        results: list[dict[str, str]] = []
        for topic in data.get("RelatedTopics", []):
            if "Topics" in topic:
                for nested in topic.get("Topics", []):
                    if nested.get("FirstURL") and nested.get("Text"):
                        results.append({
                            "title": nested.get("Text", "").split(" - ")[0][:80],
                            "url": nested.get("FirstURL", ""),
                            "snippet": nested.get("Text", "")[:240],
                            "domain": urllib.parse.urlparse(nested.get("FirstURL", "")).netloc,
                        })
            elif topic.get("FirstURL") and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "").split(" - ")[0][:80],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", "")[:240],
                    "domain": urllib.parse.urlparse(topic.get("FirstURL", "")).netloc,
                })

        if data.get("AbstractURL") and data.get("AbstractText"):
            results.insert(0, {
                "title": data.get("Heading") or "DuckDuckGo result",
                "url": data.get("AbstractURL"),
                "snippet": data.get("AbstractText")[:240],
                "domain": urllib.parse.urlparse(data.get("AbstractURL")).netloc,
            })
        if results:
            return results[:3]

        return [{
            "title": f"Search results for {query}",
            "url": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}",
            "snippet": "Open DuckDuckGo search results for this query.",
            "domain": "duckduckgo.com",
        }]

    try:
        return await asyncio.to_thread(run_search)
    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return []


async def _web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()

    if api_key and api_key != "your-tavily-api-key-here":
        def run_tavily() -> list[dict[str, str]]:
            from tavily import TavilyClient  # noqa: PLC0415

            client = TavilyClient(api_key=api_key)
            response = client.search(query=query, search_depth="advanced", max_results=max_results)
            results = response.get("results", []) if isinstance(response, dict) else []
            return [
                {
                    "title": str(item.get("title") or urllib.parse.urlparse(item.get("url", "")).netloc or "Search result")[:120],
                    "url": str(item.get("url") or ""),
                    "snippet": str(item.get("content") or item.get("snippet") or "")[:500],
                    "domain": urllib.parse.urlparse(str(item.get("url") or "")).netloc,
                }
                for item in results
                if item.get("url")
            ][:max_results]

        try:
            return await asyncio.to_thread(run_tavily)
        except Exception as exc:
            logger.warning("Tavily search failed, falling back to DuckDuckGo: %s", exc)

    return await _duckduckgo_search(query)


def _should_search(user_message: str) -> bool:
    text = user_message.lower().strip()
    if not text:
        return False

    casual_patterns = [
        r"^(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|lol|haha)\b",
        r"\b(i feel|i want|i like|i love|i hate|i'm bored|im bored|bubbly|rn)\b",
        r"\b(what is my name|who am i|do you remember|tell me about me)\b",
    ]
    if any(re.search(pattern, text) for pattern in casual_patterns) and len(text.split()) <= 12:
        return False

    current_markers = [
        "today", "latest", "current", "recent", "now", "this week", "this month",
        "news", "price", "prices", "stock", "weather", "release date", "version",
        "2025", "2026", "near me", "best", "top", "review", "compare", "vs",
        "buy", "product", "how to", "guide", "tutorial", "documentation", "docs",
        "source", "citation", "research", "search", "look up", "find",
    ]
    if any(marker in text for marker in current_markers):
        return True

    question_starts = ("where can i", "which", "when did", "when is", "who is the current", "what is the latest")
    return text.startswith(question_starts)


async def _analyse_images(images: list[dict[str, Any]], prompt: str, api_key: str) -> str:
    if not images:
        return ""

    content: list[dict[str, Any]] = []
    content.append({"type": "text", "text": prompt or "Please analyse and describe this image in detail."})
    for image in images[:3]:
        base64_data = image.get("base64")
        if not base64_data:
            continue
        mime_type = image.get("mimeType") or "image/jpeg"
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
        })

    if len(content) <= 1:
        return ""

    try:
        client = AsyncGroq(api_key=api_key)
        response = await client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": content}],
            max_tokens=900,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Inline image analysis failed: %s", exc)
        return ""


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.
    Startup: validate config, log service identity.
    Shutdown: clean up any held resources.
    """
    settings = get_settings()

    # ── Startup ──────────────────────────────────────────────────────────
    configure_logging(settings)

    logger.info("━━━ service-ai starting ━━━")
    logger.info("Environment : %s", settings.app_env)
    logger.info("Provider    : %s", settings.llm_provider)
    logger.info("Model       : %s", settings.active_model)
    logger.info(
        "mem0 mode   : %s",
        "local (no API key)" if settings.mem0_use_local else "cloud",
    )

    if settings.llm_provider == "groq" and not settings.groq_api_key:
        logger.error("GROQ_API_KEY is not configured — chat routes will fail at runtime.")
    if settings.llm_provider == "gemini" and not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY is not configured — Gemini routes will fail at runtime.")

    # ── Start MCP server subprocesses ────────────────────────────────────
    from app.services.mcp_service import get_mcp_manager  # noqa: PLC0415
    mcp_manager = get_mcp_manager()
    await mcp_manager.start()

    # ── Pre-build the agent swarm (injects MCP servers) ──────────────────
    from app.agents.swarm import initialise_swarm  # noqa: PLC0415
    await initialise_swarm()

    # ── Register main event loop for media worker thread scheduling ───────
    import asyncio  # noqa: PLC0415
    from app.workers.media_worker import set_main_event_loop  # noqa: PLC0415
    set_main_event_loop(asyncio.get_running_loop())

    logger.info("service-ai startup complete.")

    yield  # ← application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("service-ai shutting down.")
    await mcp_manager.shutdown()


def create_app() -> FastAPI:
    """Construct and return the configured FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="service-ai",
        description=(
            "Agentic AI microservice — LiteLLM/Gemini routing, "
            "mem0 local memory, multi-agent swarm, async media jobs."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "service": "nexus-python"}

    # ── Exception handlers ───────────────────────────────────────────────
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # Attach limiter to app state (required by slowapi)
    app.state.limiter = limiter

    # ── CORS ─────────────────────────────────────────────────────────────
    origins = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5001").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/chat")
    async def chat(body: dict):
        message = body.get("message", "")
        history = body.get("history", [])
        image_inputs = body.get("imageInputs") if isinstance(body.get("imageInputs"), list) else []
        images = body.get("images") if isinstance(body.get("images"), list) else []
        for image in images:
            if not isinstance(image, dict) or not image.get("base64"):
                continue
            mime_type = image.get("mimeType") or "image/jpeg"
            image_inputs.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image['base64']}"},
            })
        web_search = bool(body.get("webSearch"))
        code_mode = bool(body.get("codeMode"))
        deep_think = bool(body.get("deepThink"))
        system_prompt = body.get("systemPrompt") or (
            "You are Nexus, an agentic AI assistant. You are helpful, "
            "precise, and capable of web search, analysis, and long-running tasks."
        )

        async def generate():
            if not message:
                yield _sse({"type": "error", "text": "Message is required"})
                yield _sse({"type": "done"})
                return

            settings = get_settings()
            api_key = settings.groq_api_key or os.getenv("GROQ_API_KEY", "").strip()
            model = settings.groq_model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

            if not api_key or api_key == "your-groq-api-key-here":
                yield _sse({"type": "error", "text": "GROQ_API_KEY is required for Nexus chat streaming"})
                yield _sse({"type": "done"})
                return

            should_search = bool(web_search and _should_search(str(message)))
            image_analysis = ""

            if deep_think:
                yield _sse({
                    "type": "step",
                    "id": "deep_breakdown",
                    "icon": "✦",
                    "text": "Breaking down the problem...",
                    "status": "thinking",
                })
                yield _sse({
                    "type": "step",
                    "id": "deep_approaches",
                    "icon": "💭",
                    "text": "Considering multiple approaches...",
                    "status": "thinking",
                })
                yield _sse({
                    "type": "step",
                    "id": "deep_evaluate",
                    "icon": "✓",
                    "text": "Evaluating best answer...",
                    "status": "thinking",
                })

            if image_inputs:
                yield _sse({
                    "type": "step",
                    "id": "image",
                    "icon": "📎",
                    "text": "Analysing your image...",
                    "status": "processing",
                })
                image_analysis = await _analyse_images(
                    images,
                    str(message) or "Please analyse and describe this image in detail.",
                    api_key,
                )

            sources: list[dict[str, str]] = []
            search_context = ""
            if should_search:
                yield _sse({
                    "type": "step",
                    "id": "search_decide",
                    "icon": "💭",
                    "text": "Analysing your question...",
                    "status": "thinking",
                })
                yield _sse({
                    "type": "step",
                    "id": "search_decision",
                    "icon": "💭",
                    "text": f'Decided to search the web for: "{str(message)[:80]}"',
                    "status": "thinking",
                })
                yield _sse({
                    "type": "step",
                    "id": "web_search",
                    "icon": "🔍",
                    "text": f'Searching: "{str(message)[:80]}"',
                    "status": "searching",
                })
                sources = await _web_search(str(message), max_results=5)
                if sources:
                    for index, source in enumerate(sources, start=1):
                        yield _sse({
                            "type": "step",
                            "id": f"read_{index}",
                            "icon": "🌐",
                            "text": f"Reading {source.get('domain') or source.get('url')}...",
                            "status": "reading",
                        })
                    search_context = "\n\nWeb search results:\n" + "\n".join(
                        f"- {source['title']} ({source['url']}): {source['snippet']}"
                        for source in sources
                    )
                    yield _sse({
                        "type": "step",
                        "id": "search_synthesis",
                        "icon": "💭",
                        "text": "Synthesising results...",
                        "status": "thinking",
                    })
                else:
                    yield _sse({
                        "type": "step",
                        "id": "web_search_empty",
                        "icon": "🔍",
                        "text": "Web search returned no usable results",
                        "status": "done",
                    })

            if should_search or deep_think or image_inputs:
                yield _sse({
                    "type": "step",
                    "id": "compose",
                    "icon": "📝",
                    "text": "Composing response",
                    "status": "done",
                })

            messages = [
                {
                    "role": "system",
                    "content": str(system_prompt) + search_context + (
                        f"\n\nImage analysis from the vision model:\n{image_analysis}"
                        if image_analysis else ""
                    ) + (
                        "\n\nWhen web search results are present, cite the source domains naturally."
                        if search_context else ""
                    ) + (
                        "\n\nUse extended reasoning privately before answering. Do not reveal chain-of-thought; summarize the conclusion clearly."
                        if deep_think else ""
                    ) + (
                        "\n\nThe user prefers code formatting when it helps." if code_mode else ""
                    ),
                }
            ]
            if isinstance(history, list):
                messages.extend(
                    {
                        "role": item.get("role"),
                        "content": item.get("content", ""),
                    }
                    for item in history
                    if isinstance(item, dict)
                    and item.get("role") in {"system", "user", "assistant"}
                    and item.get("content")
                )
            user_text = str(message) or "Please analyse and describe this image in detail."
            if image_analysis:
                user_text = f"{user_text}\n\nUse this image analysis in your answer:\n{image_analysis}"
            messages.append({"role": "user", "content": user_text})

            try:
                import litellm  # noqa: PLC0415

                stream = await litellm.acompletion(
                    model=f"groq/{model}",
                    messages=messages,
                    api_key=api_key,
                    max_tokens=2048,
                    stream=True,
                )

                async for chunk in stream:
                    text = _extract_stream_delta(chunk)
                    if text:
                        yield _sse({"type": "content", "text": text})
                        await asyncio.sleep(0)
            except Exception as exc:
                logger.exception("Groq stream failed")
                if image_inputs:
                    try:
                        messages[-1] = {
                            "role": "user",
                            "content": (
                                f"{message}\n\nThe user attached image(s), but the active model could not process "
                                "the image payload directly. Explain that limitation briefly and answer any text portion."
                            ),
                        }
                        stream = await litellm.acompletion(
                            model=f"groq/{model}",
                            messages=messages,
                            api_key=api_key,
                            max_tokens=2048,
                            stream=True,
                        )
                        async for chunk in stream:
                            text = _extract_stream_delta(chunk)
                            if text:
                                yield _sse({"type": "content", "text": text})
                                await asyncio.sleep(0)
                    except Exception as retry_exc:
                        logger.exception("Groq retry without images failed")
                        yield _sse({"type": "error", "text": str(retry_exc)})
                else:
                    yield _sse({"type": "error", "text": str(exc)})

            yield _sse({"type": "sources", "searchUsed": should_search, "sources": sources if should_search else []})
            if should_search or deep_think or image_inputs:
                yield _sse({
                    "type": "step",
                    "id": "done",
                    "icon": "✓",
                    "text": "Done",
                    "status": "done",
                })
            yield _sse({"type": "done"})

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/memory/extract")
    async def extract_memory(body: dict):
        user_message = str(body.get("userMessage", "") or "")
        assistant_reply = str(body.get("assistantReply", "") or "")
        current_memory = body.get("currentMemory") if isinstance(body.get("currentMemory"), dict) else {}

        settings = get_settings()
        api_key = settings.groq_api_key or os.getenv("GROQ_API_KEY", "").strip()
        model = settings.groq_model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        fallback = _heuristic_memory(user_message, current_memory)

        if not api_key or api_key == "your-groq-api-key-here":
            return JSONResponse({"memory": fallback, "source": "heuristic"})

        try:
            import litellm  # noqa: PLC0415

            response = await litellm.acompletion(
                model=f"groq/{model}",
                api_key=api_key,
                temperature=0,
                max_tokens=300,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract stable long-term user memory from the conversation. "
                            "Return only JSON with keys: name, nickname, occupation, location, facts. "
                            "Only include personal facts explicitly revealed by the user. "
                            "Preserve existing values when no update is needed."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "currentMemory": current_memory,
                                "userMessage": user_message,
                                "assistantReply": assistant_reply[:1000],
                            }
                        ),
                    },
                ],
            )
            raw = _extract_message_content(response).strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(raw)

            memory = {
                "name": parsed.get("name") or fallback.get("name", ""),
                "nickname": parsed.get("nickname") or fallback.get("nickname", ""),
                "occupation": parsed.get("occupation") or fallback.get("occupation", ""),
                "location": parsed.get("location") or fallback.get("location", ""),
                "facts": [
                    str(fact).strip()
                    for fact in (parsed.get("facts") if isinstance(parsed.get("facts"), list) else fallback.get("facts", []))
                    if str(fact).strip()
                ][:30],
            }

            heuristic_facts = fallback.get("facts", [])
            memory["facts"] = list(dict.fromkeys([*memory["facts"], *heuristic_facts]))[:30]
            return JSONResponse({"memory": memory, "source": "groq"})
        except Exception as exc:
            logger.warning("Memory extraction fell back to heuristics: %s", exc)
            return JSONResponse({"memory": fallback, "source": "heuristic"})

    # ── Routers ──────────────────────────────────────────────────────────
    # Imported here to avoid circular imports at module load time.
    from app.api.routes import router as api_router  # noqa: PLC0415

    app.include_router(api_router, prefix="/api/v1")

    return app


# ASGI entry point — used by:  uv run uvicorn app.main:app --reload
app = create_app()


def run() -> None:
    """Entry point for `uv run start` (defined in pyproject.toml scripts)."""
    import uvicorn

    settings = get_settings()
    port = int(os.getenv("PORT", settings.app_port))
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
