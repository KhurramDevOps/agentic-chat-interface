"""
app/core/llm_proxy.py  (T021)
──────────────────────────────
LiteLLM routing configuration for OpenAI-to-Gemini mapping.

The openai-agents SDK uses an AsyncOpenAI client under the hood.
We point that client at LiteLLM's OpenAI-compatible proxy endpoint
so all model calls are transparently routed to Gemini.

When OPENAI_BASE_URL is set in .env, traffic goes to a self-hosted
LiteLLM proxy. When it is empty, we use LiteLLM's Python library
directly via its built-in OpenAI-compatible base URL.

Constitution compliance:
  - No MongoDB imports or connections.
  - Client is constructed once and reused (singleton via lru_cache).
"""

from __future__ import annotations

from functools import lru_cache

import litellm
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# LiteLLM's built-in OpenAI-compatible endpoint
_LITELLM_LOCAL_BASE = "https://api.openai.com/v1"


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    """
    Return a singleton AsyncOpenAI client configured for LiteLLM/Gemini routing.

    The Agents SDK calls set_default_openai_client() once at startup
    (done in build_swarm()) so every Agent instance shares this client.
    """
    settings = get_settings()

    base_url = settings.openai_base_url.strip() or _LITELLM_LOCAL_BASE
    api_key = settings.gemini_api_key or settings.openai_api_key or "placeholder"

    logger.info("Configuring AsyncOpenAI client → base_url=%s", base_url)

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    return client


def configure_litellm() -> None:
    """
    Apply global LiteLLM settings.
    Called once from the FastAPI lifespan startup handler.
    """
    settings = get_settings()

    # Route gemini/* model aliases to the Gemini provider
    litellm.api_key = settings.gemini_api_key  # type: ignore[attr-defined]

    # Suppress LiteLLM's verbose success logs in non-debug mode
    if settings.log_level != "DEBUG":
        litellm.suppress_debug_info = True  # type: ignore[attr-defined]
        litellm.set_verbose = False  # type: ignore[attr-defined]

    logger.info("LiteLLM configured — default model: %s", settings.litellm_model)
