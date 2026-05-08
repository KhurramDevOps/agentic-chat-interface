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

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


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
    logger.info("LiteLLM model: %s", settings.litellm_model)
    logger.info(
        "mem0 mode   : %s",
        "local (no API key)" if settings.mem0_use_local else "cloud",
    )

    if not settings.gemini_api_key:
        logger.warning(
            "GEMINI_API_KEY is not configured — chat routes will fail at runtime."
        )

    logger.info("service-ai startup complete.")

    yield  # ← application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("service-ai shutting down.")


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
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Exception handlers ───────────────────────────────────────────────
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── CORS (tightened in production via env) ───────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=not settings.is_production,
        log_level=settings.log_level.lower(),
    )
