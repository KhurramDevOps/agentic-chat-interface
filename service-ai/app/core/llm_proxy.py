"""
app/core/llm_proxy.py
──────────────────────
Provider-aware OpenAI-compatible client factory.

Supports:
  - Gemini  : https://generativelanguage.googleapis.com/v1beta/openai/
  - Groq    : https://api.groq.com/openai/v1

Switch providers by setting LLM_PROVIDER=gemini|groq in .env.
The active model and API key are resolved automatically from Settings.

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
os.environ["OPENAI_TELEMETRY"] = "false"
set_tracing_disabled(True)
set_default_openai_api("chat_completions")

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    """
    Return a singleton AsyncOpenAI client for the active LLM provider.
    Provider is determined by LLM_PROVIDER in .env (gemini | groq).
    """
    settings = get_settings()

    logger.info(
        "Configuring AsyncOpenAI client → provider=%s, base_url=%s, model=%s",
        settings.llm_provider,
        settings.active_base_url,
        settings.active_model,
    )

    return AsyncOpenAI(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
    )
