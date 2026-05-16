"""
app/core/logging.py
────────────────────
Emoji-enhanced, visually scannable logging for service-ai.

Dev output example:
  2026-05-16T10:23:01 🟢 INFO     💬 app.api.routes.chat      Processing request...
  2026-05-16T10:23:02 🧠 INFO     🧠 app.agents.swarm         run_swarm complete
  2026-05-16T10:23:02 🔴 ERROR    💾 app.services.history     MongoDB timeout

Production output: newline-delimited JSON (unchanged).

Module → emoji mapping lets your eyes jump straight to the relevant subsystem.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings


# ── Module → emoji map ────────────────────────────────────────────────────────

_MODULE_EMOJI: dict[str, str] = {
    # Agents / swarm
    "app.agents":          "🧠",
    "app.agents.swarm":    "🧠",
    "app.agents.triage":   "🧠",
    "app.agents.domain":   "🧠",
    # API routes
    "app.api.routes.chat": "💬",
    "app.api.routes.sse":  "💬",
    "app.api.routes.stream": "💬",
    "app.api.routes.audio": "🎤",
    "app.api.routes.vision": "🎨",
    "app.api.routes.files": "📄",
    "app.api.routes.users": "👤",
    "app.api.routes.health": "🏥",
    "app.api":             "🌐",
    # Services
    "app.services.history": "💾",
    "app.services.user":    "👤",
    "app.services.file":    "📄",
    "app.services.mcp":     "🔌",
    "app.services.stream":  "📡",
    "app.services":         "⚙️ ",
    # Workers
    "app.workers.media":   "🎨",
    "app.workers":         "⚙️ ",
    # Core
    "app.core.config":     "⚙️ ",
    "app.core.llm":        "🤖",
    "app.core":            "⚙️ ",
    # App root
    "app.main":            "🚀",
}

_LEVEL_EMOJI: dict[str, str] = {
    "DEBUG":    "🔵",
    "INFO":     "🟢",
    "WARNING":  "🟡",
    "ERROR":    "🔴",
    "CRITICAL": "🔥",
}


def _module_emoji(name: str) -> str:
    """Return the best-matching emoji for a logger name."""
    # Walk from most-specific to least-specific prefix
    for prefix in sorted(_MODULE_EMOJI, key=len, reverse=True):
        if name.startswith(prefix):
            return _MODULE_EMOJI[prefix]
    return "📋"


# ── Request-ID context filter ─────────────────────────────────────────────────

class RequestIdFilter(logging.Filter):
    """Injects a `request_id` field into every LogRecord."""

    def __init__(self, request_id: str = "-") -> None:
        super().__init__()
        self.request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = self.request_id  # type: ignore[attr-defined]
        return True


# ── JSON formatter (production) ───────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Emits each log record as a single-line JSON object."""

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


# ── Emoji formatter (development) ─────────────────────────────────────────────

class EmojiFormatter(logging.Formatter):
    """
    Human-readable formatter with emoji level indicators and module icons.

    Output format:
      {timestamp} {level_emoji} {level:<8} {module_emoji} {logger:<35} {message}

    Example:
      2026-05-16T10:23:01 🟢 INFO     🧠 app.agents.swarm          Swarm ready
      2026-05-16T10:23:02 🔴 ERROR    💾 app.services.history_serv  MongoDB timeout
    """

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = "-"  # type: ignore[attr-defined]

        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%dT%H:%M:%S")
        level_emoji = _LEVEL_EMOJI.get(record.levelname, "⬜")
        mod_emoji = _module_emoji(record.name)
        level = record.levelname.ljust(8)

        # Truncate long logger names to keep columns aligned
        logger_name = record.name
        if len(logger_name) > 32:
            parts = logger_name.split(".")
            logger_name = ".".join(p[:1] for p in parts[:-1]) + "." + parts[-1]
        logger_name = logger_name.ljust(32)

        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return f"{ts} {level_emoji} {level} {mod_emoji} {logger_name} {msg}"


# ── Public API ────────────────────────────────────────────────────────────────

def configure_logging(settings: "Settings") -> None:
    """
    Configure the root logger for the entire service.
    Call once from the FastAPI lifespan startup handler.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())

    if settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(EmojiFormatter())

    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "litellm", "pymongo"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Thin wrapper kept for import convenience."""
    return logging.getLogger(name)
