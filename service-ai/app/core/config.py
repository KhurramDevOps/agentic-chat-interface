"""
app/core/config.py
──────────────────
Centralised settings loader using Pydantic BaseSettings.

All configuration is sourced from environment variables (or a .env file).
Startup validation raises a clear error if required values are absent,
preventing the service from starting in a misconfigured state.

Constitution compliance:
  - No MongoDB connection strings are accepted here.
  - Any attempt to inject a MongoDB URI raises a ValueError at startup.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service-scoped settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Runtime ──────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ── LiteLLM / Gemini ─────────────────────────────────────────────────
    litellm_model: str = Field(
        default="gemini/gemini-1.5-pro",
        description="OpenAI-style model alias resolved by LiteLLM.",
    )
    gemini_api_key: str = Field(
        default="",
        description="Gemini provider API key.",
    )

    # ── mem0 ─────────────────────────────────────────────────────────────
    mem0_api_key: str = Field(
        default="",
        description="mem0 API key. Empty string uses local in-memory mode.",
    )

    # ── OpenAI Agents SDK ────────────────────────────────────────────────
    openai_api_key: str = Field(default="", description="OpenAI / proxy API key.")
    openai_base_url: str = Field(
        default="",
        description="Optional base URL override (e.g. LiteLLM self-hosted proxy).",
    )

    # ── Background task limits ───────────────────────────────────────────
    media_task_timeout_seconds: int = Field(default=300, ge=1)
    media_task_max_queue: int = Field(default=50, ge=1)

    # ── Constitution safeguard ───────────────────────────────────────────
    @model_validator(mode="before")
    @classmethod
    def reject_mongodb_config(cls, values: dict) -> dict:
        """
        T011 — Constitution boundary safeguard.
        Raise immediately if any MongoDB-related variable is present,
        preventing accidental direct DB access from service-ai.
        """
        forbidden = {"mongodb_uri", "mongo_uri", "mongodb_url", "mongo_url"}
        found = forbidden.intersection({k.lower() for k in values})
        if found:
            raise ValueError(
                f"Constitution violation: service-ai MUST NOT configure MongoDB. "
                f"Detected forbidden variable(s): {found}. "
                "MongoDB ownership belongs exclusively to gateway-node."
            )
        return values

    @field_validator("gemini_api_key", mode="after")
    @classmethod
    def warn_missing_gemini_key(cls, v: str) -> str:
        if not v:
            import warnings
            warnings.warn(
                "GEMINI_API_KEY is not set. LiteLLM routing to Gemini will fail "
                "at request time. Set the key in your .env file.",
                stacklevel=2,
            )
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def mem0_use_local(self) -> bool:
        """True when no mem0 API key is provided — falls back to local memory."""
        return not self.mem0_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.
    Cached after first call so .env is only parsed once per process.
    """
    return Settings()
