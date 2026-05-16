"""
app/api/routes/health.py  (T014)
─────────────────────────────────
Health and readiness endpoints for service-ai.

Endpoints:
  GET /api/v1/health/live     — liveness probe
  GET /api/v1/health/ready    — readiness probe
  GET /api/v1/health          — combined summary
  GET /api/v1/health/detailed — deep probe: MongoDB ping + LLM reachability
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_settings_dep
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class HealthChecks(BaseModel):
    config: str
    memory: Literal["local", "cloud"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str = "service-ai"
    version: str = "0.1.0"
    env: str
    checks: HealthChecks


class DetailedChecks(BaseModel):
    mongodb: str          # "ok" | "error:<msg>"
    llm_provider: str     # "ok" | "error:<msg>"
    mem0: str             # "local" | "cloud" | "error:<msg>"
    config: str


class DetailedHealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str = "service-ai"
    version: str = "0.1.0"
    env: str
    checks: DetailedChecks


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_health(settings: Settings) -> HealthResponse:
    config_status = "ok"
    overall: Literal["ok", "degraded"] = "ok"

    if settings.llm_provider == "gemini" and not settings.gemini_api_key:
        config_status = "warn:GEMINI_API_KEY not set"
        overall = "degraded"
    elif settings.llm_provider == "groq" and not settings.groq_api_key:
        config_status = "warn:GROQ_API_KEY not set"
        overall = "degraded"

    return HealthResponse(
        status=overall,
        env=settings.app_env,
        checks=HealthChecks(
            config=config_status,
            memory="local" if settings.mem0_use_local else "cloud",
        ),
    )


async def _check_mongodb() -> str:
    """Ping MongoDB and return 'ok' or 'error:<msg>'."""
    import os  # noqa: PLC0415
    from motor.motor_asyncio import AsyncIOMotorClient  # noqa: PLC0415
    try:
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
        await client.admin.command("ping")
        return "ok"
    except Exception as exc:
        return f"error:{exc}"


async def _check_llm(settings: Settings) -> str:
    """Make a minimal API call to verify the LLM provider is reachable."""
    import httpx  # noqa: PLC0415
    try:
        url = settings.active_base_url.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {settings.active_api_key}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code < 500:
            return "ok"
        return f"error:HTTP {resp.status_code}"
    except Exception as exc:
        return f"error:{exc}"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/live", summary="Liveness probe", tags=["Health"])
async def liveness() -> dict:
    return {"status": "ok", "service": "service-ai"}


@router.get(
    "/ready",
    summary="Readiness probe",
    response_model=HealthResponse,
    tags=["Health"],
)
async def readiness(settings: Settings = Depends(get_settings_dep)) -> HealthResponse:
    return _build_health(settings)


@router.get(
    "",
    summary="Health summary",
    response_model=HealthResponse,
    tags=["Health"],
)
async def health_summary(settings: Settings = Depends(get_settings_dep)) -> HealthResponse:
    return _build_health(settings)


@router.get(
    "/detailed",
    summary="Deep health probe — MongoDB + LLM reachability",
    response_model=DetailedHealthResponse,
    tags=["Health"],
)
async def health_detailed(settings: Settings = Depends(get_settings_dep)) -> DetailedHealthResponse:
    """
    Actively pings MongoDB and the LLM provider API.
    Slower than /health but gives real dependency status.
    """
    mongodb_status, llm_status = await _check_mongodb(), await _check_llm(settings)

    config_ok = "ok"
    if settings.llm_provider == "gemini" and not settings.gemini_api_key:
        config_ok = "warn:GEMINI_API_KEY not set"
    elif settings.llm_provider == "groq" and not settings.groq_api_key:
        config_ok = "warn:GROQ_API_KEY not set"

    overall: Literal["ok", "degraded"] = "ok"
    if any(s.startswith("error") for s in (mongodb_status, llm_status)):
        overall = "degraded"

    mem0_status = "local" if settings.mem0_use_local else "cloud"

    logger.info(
        "health/detailed — mongodb=%s, llm=%s, mem0=%s",
        mongodb_status, llm_status, mem0_status,
    )

    return DetailedHealthResponse(
        status=overall,
        env=settings.app_env,
        checks=DetailedChecks(
            mongodb=mongodb_status,
            llm_provider=llm_status,
            mem0=mem0_status,
            config=config_ok,
        ),
    )
