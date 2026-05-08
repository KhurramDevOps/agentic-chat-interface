"""
app/api/deps.py  (T008)
───────────────────────
Shared FastAPI dependencies and standardised error envelope.

Provides:
  - APIError          — structured error response model
  - http_error()      — raise HTTPException with a consistent JSON body
  - Exception handlers registered on the app instance
  - get_settings_dep  — FastAPI dependency that injects Settings
  - get_request_id    — FastAPI dependency that extracts / generates request_id

All error responses follow the envelope:
    {
        "error": {
            "code":       "NOT_FOUND",
            "message":    "The requested resource was not found.",
            "request_id": "abc-123",
            "details":    {}          # optional
        }
    }
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Error envelope models ─────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None


class APIError(BaseModel):
    error: ErrorDetail


# ── Helper ────────────────────────────────────────────────────────────────────

def http_error(
    status_code: int,
    code: str,
    message: str,
    request_id: str = "-",
    details: dict[str, Any] | None = None,
) -> HTTPException:
    """
    Build an HTTPException whose detail is the standard APIError envelope.

    Usage:
        raise http_error(404, "NOT_FOUND", "Agent not found.", request_id)
    """
    body = APIError(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
            details=details,
        )
    )
    return HTTPException(status_code=status_code, detail=body.model_dump())


# ── Exception handlers (register these on the FastAPI app) ───────────────────

async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic request validation errors with the standard envelope."""
    request_id = _extract_request_id(request)
    logger.warning(
        "Request validation failed",
        extra={"request_id": request_id, "errors": exc.errors()},
    )
    body = APIError(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request payload failed validation.",
            request_id=request_id,
            details={"errors": exc.errors()},
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=body.model_dump(),
    )


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """
    Re-wrap HTTPExceptions that already carry an APIError detail dict,
    and wrap plain string details into the envelope for consistency.
    """
    request_id = _extract_request_id(request)

    # If the detail is already our envelope dict, pass it through
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        # Inject request_id if it was left as the default "-"
        if exc.detail["error"].get("request_id") == "-":
            exc.detail["error"]["request_id"] = request_id
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    # Plain string or other detail — wrap it
    body = APIError(
        error=ErrorDetail(
            code="HTTP_ERROR",
            message=str(exc.detail),
            request_id=request_id,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for unexpected server errors — never leak stack traces."""
    request_id = _extract_request_id(request)
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        extra={"request_id": request_id},
    )
    body = APIError(
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again later.",
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body.model_dump(),
    )


# ── FastAPI injectable dependencies ──────────────────────────────────────────

def get_settings_dep() -> Settings:
    """Inject the singleton Settings instance into route handlers."""
    return get_settings()


def get_request_id(request: Request) -> str:
    """
    Extract X-Request-ID from incoming headers, or generate a new UUID.
    Downstream handlers can inject this to correlate logs with requests.
    """
    return _extract_request_id(request)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_request_id(request: Request) -> str:
    """Read X-Request-ID header or fall back to a fresh UUID4."""
    return request.headers.get("x-request-id") or str(uuid.uuid4())
