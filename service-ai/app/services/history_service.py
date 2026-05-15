"""
app/services/history_service.py
────────────────────────────────
In-memory conversation history store.

Maintains short-term message history per session_id so the swarm has
full conversational context across multiple requests.

Design:
  - Keyed by session_id (memory_context_id or request_id fallback).
  - Each session stores a list of {role, content} dicts.
  - History is capped at MAX_HISTORY_MESSAGES to protect the context window.
  - System messages are always preserved at position 0 if present.

Constitution compliance:
  - No MongoDB imports or connections.
  - Pure in-process storage — intentional for Phase 7.
"""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)

# Keep the last N messages (user + assistant turns) per session.
# A turn = 1 user message + 1 assistant message = 2 entries.
# 20 messages = 10 full turns of context.
MAX_HISTORY_MESSAGES = 20


class HistoryStore:
    """
    In-memory conversation history registry.

    Usage:
        store = get_history_store()
        store.append(session_id, "user", "Hello")
        store.append(session_id, "assistant", "Hi there!")
        history = store.get(session_id)   # list of {role, content} dicts
    """

    def __init__(self) -> None:
        # session_id → list of {"role": str, "content": str}
        self._sessions: dict[str, list[dict[str, str]]] = {}

    def get(self, session_id: str) -> list[dict[str, str]]:
        """Return the full message history for a session (empty list if new)."""
        return list(self._sessions.get(session_id, []))

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append a message to the session history, then trim if over limit."""
        if session_id not in self._sessions:
            self._sessions[session_id] = []

        self._sessions[session_id].append({"role": role, "content": content})
        self._trim(session_id)

        logger.debug(
            "history.append — session=%s, role=%s, total=%d",
            session_id, role, len(self._sessions[session_id]),
        )

    def _trim(self, session_id: str) -> None:
        """
        Trim history to MAX_HISTORY_MESSAGES.

        Strategy: always keep a system message at index 0 if present,
        then keep the most recent messages up to the cap.
        """
        messages = self._sessions[session_id]
        if len(messages) <= MAX_HISTORY_MESSAGES:
            return

        # Separate system message from the rest
        if messages and messages[0]["role"] == "system":
            system_msg = [messages[0]]
            rest = messages[1:]
            trimmed = rest[-(MAX_HISTORY_MESSAGES - 1):]
            self._sessions[session_id] = system_msg + trimmed
        else:
            self._sessions[session_id] = messages[-MAX_HISTORY_MESSAGES:]

        logger.debug(
            "history.trim — session=%s, kept=%d",
            session_id, len(self._sessions[session_id]),
        )

    def clear(self, session_id: str) -> None:
        """Clear history for a session."""
        self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        return len(self._sessions)

    def message_count(self, session_id: str) -> int:
        return len(self._sessions.get(session_id, []))


# ── Singleton ─────────────────────────────────────────────────────────────────

_history_store: HistoryStore | None = None


def get_history_store() -> HistoryStore:
    """Return the process-wide HistoryStore singleton."""
    global _history_store
    if _history_store is None:
        _history_store = HistoryStore()
        logger.info("HistoryStore initialised.")
    return _history_store
