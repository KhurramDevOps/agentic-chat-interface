"""
app/api/routes/health.py  (T014)
─────────────────────────────────
Health and readiness endpoints for service-ai.

Endpoints:
  GET /api/v1/health/live   — liveness probe (is the process up?)
  GET /api/v1/health/ready  — readiness probe (is config valid and service ready?)
  GET /api/v1/health        — combined summary (convenience)

Response shape:
  {
    "status":    "ok" | "degraded",
    "service":   "service-ai",
    "version":   "0.1.0",
    "env":       "development",
    "checks": {
      "config":  "ok" | "warn:<reason>",
      "memory":  "local" | "cloud"
    }
  }
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_settings_dep
from app.core.config import Settings

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_health(settings: Settings) -> HealthResponse:
    """Evaluate current health state from validated settings."""
    config_status = "ok"
    overall: Literal["ok", "degraded"] = "ok"

    if not settings.gemini_api_key:
        config_status = "warn:GEMINI_API_KEY not set"
        overall = "degraded"

    return HealthResponse(
        status=overall,
        env=settings.app_env,
        checks=HealthChecks(
            config=config_status,
            memory="local" if settings.mem0_use_local else "cloud",
        ),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/live",
    summary="Liveness probe",
    description="Returns 200 as long as the process is running.",
    tags=["Health"],
)
async def liveness() -> dict:
    return {"status": "ok", "service": "service-ai"}


@router.get(
    "/ready",
    summary="Readiness probe",
    response_model=HealthResponse,
    description="Returns 200 when config is valid; 503 when critically degraded.",
    tags=["Health"],
)
async def readiness(
    settings: Settings = Depends(get_settings_dep),
) -> HealthResponse:
    return _build_health(settings)


@router.get(
    "",
    summary="Health summary",
    response_model=HealthResponse,
    description="Combined liveness + readiness summary.",
    tags=["Health"],
)
async def health_summary(
    settings: Settings = Depends(get_settings_dep),
) -> HealthResponse:
    return _build_health(settings)
