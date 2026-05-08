"""
app/core/llm_proxy.py  (T021 — revised)
─────────────────────────────────────────
OpenAI client configured for Google's native OpenAI-compatible endpoint.

We bypass LiteLLM entirely and point the Agents SDK's AsyncOpenAI client
directly at Google's Gemini REST endpoint, which speaks the OpenAI Chat
Completions protocol natively.

Endpoint: https://generativelanguage.googleapis.com/v1beta/openai/
Auth:      GEMINI_API_KEY

Critical SDK configuration applied at module load:
  - OPENAI_TELEMETRY=false  : prevents env-var-level telemetry init
  - set_tracing_disabled()  : disables SDK-level trace POSTs to OpenAI
  - set_default_openai_api("chat_completions") : forces the SDK to use
    /v1/chat/completions instead of /v1/responses (which Gemini doesn't
    support and returns 404).

Constitution compliance:
  - No MongoDB imports or connections.
  - Client is constructed once and reused (singleton via lru_cache).
"""

from __future__ import annotations

import os
from functools import lru_cache

from agents import set_default_openai_api, set_tracing_disabled
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger

# ── SDK-level fixes applied once at import time ───────────────────────────────

# Prevent telemetry env-var check from firing before the SDK is fully loaded
os.environ["OPENAI_TELEMETRY"] = "false"

# Disable the SDK's built-in tracing client (stops 401 POSTs to OpenAI)
set_tracing_disabled(True)

# Force Chat Completions transport — Gemini does NOT support /v1/responses
set_default_openai_api("chat_completions")

logger = get_logger(__name__)

_GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    """
    Return a singleton AsyncOpenAI client pointed at Google's
    OpenAI-compatible Gemini endpoint.

    The Agents SDK calls set_default_openai_client() once at startup
    (done in build_swarm()) so every Agent instance shares this client.
    """
    settings = get_settings()

    logger.info(
        "Configuring AsyncOpenAI client → base_url=%s, model=%s",
        _GEMINI_OPENAI_BASE,
        settings.litellm_model,
    )

    return AsyncOpenAI(
        api_key=settings.gemini_api_key,
        base_url=_GEMINI_OPENAI_BASE,
    )
