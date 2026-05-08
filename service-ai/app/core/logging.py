"""
app/core/logging.py  (T009)
───────────────────────────
Structured JSON-capable logging configuration for service-ai.

Provides:
  - configure_logging()  — called once at app startup via lifespan
  - get_logger()         — convenience wrapper for named loggers
  - RequestIdFilter      — injects request_id into every log record

Design notes:
  - In development, output is human-readable (coloured if colorlog is present).
  - In production, output is newline-delimited JSON for log aggregators.
  - The root logger is configured; all app loggers inherit from it.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings


# ── Request-ID context filter ─────────────────────────────────────────────────

class RequestIdFilter(logging.Filter):
    """
    Injects a `request_id` field into every LogRecord so that
    structured log lines can be correlated to a specific API request.

    Usage:
        logger = logging.getLogger(__name__)
        logger.addFilter(RequestIdFilter(request_id="abc-123"))
    """

    def __init__(self, request_id: str = "-") -> None:
        super().__init__()
        self.request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = self.request_id  # type: ignore[attr-defined]
        return True


# ── JSON formatter ────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """
    Emits each log record as a single-line JSON object.
    Fields: timestamp, level, logger, message, request_id, [exc_info].
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


# ── Human-readable formatter (dev) ───────────────────────────────────────────

_DEV_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] %(message)s"
)


class DevFormatter(logging.Formatter):
    """Plain-text formatter with request_id for local development."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = "-"  # type: ignore[attr-defined]
        return super().format(record)


# ── Public API ────────────────────────────────────────────────────────────────

def configure_logging(settings: "Settings") -> None:
    """
    Configure the root logger for the entire service.
    Call once from the FastAPI lifespan startup handler.

    Args:
        settings: Validated Settings instance from app.core.config.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    # Remove any handlers added by earlier basicConfig calls
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())  # default request_id = "-"

    if settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        formatter = DevFormatter(fmt=_DEV_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S")
        handler.setFormatter(formatter)

    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "litellm"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Thin wrapper kept for import convenience."""
    return logging.getLogger(name)
