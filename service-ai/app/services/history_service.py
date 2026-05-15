"""
app/services/history_service.py
────────────────────────────────
MongoDB-backed conversation history store using motor (async).

Persists short-term message history per session_id in MongoDB so history
survives server restarts.

Collection: chotuu_db.conversations
Document shape:
  {
    "session_id": "user-khurram",
    "messages": [{"role": "user", "content": "..."}, ...]
  }

History is capped at MAX_HISTORY_MESSAGES (20) to protect the context window.
System messages at index 0 are always preserved during trim.
"""

from __future__ import annotations

import os

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_HISTORY_MESSAGES = 20

_DB_NAME = "chotuu_db"
_COLLECTION = "conversations"

# ── Motor client singleton ────────────────────────────────────────────────────

_client: AsyncIOMotorClient | None = None


def _get_collection():
    """Return the motor collection, creating the client on first call."""
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri)
        logger.info("HistoryStore: motor client connected → %s", uri.split("@")[-1])
    return _client[_DB_NAME][_COLLECTION]


# ── Public API ────────────────────────────────────────────────────────────────

async def get_history(session_id: str) -> list[dict]:
    """
    Return the message history for a session (empty list if not found).
    """
    col = _get_collection()
    doc = await col.find_one({"session_id": session_id}, {"_id": 0, "messages": 1})
    if doc:
        return doc.get("messages", [])
    return []


async def append_to_history(session_id: str, role: str, content: str) -> None:
    """
    Append a message to the session history and trim to MAX_HISTORY_MESSAGES.

    Uses $push + $slice to atomically append and cap in a single operation.
    System messages at index 0 are preserved by the trim logic.
    """
    col = _get_collection()
    new_msg = {"role": role, "content": content}

    # Fetch current history to check for system message preservation
    current = await get_history(session_id)
    has_system = bool(current) and current[0].get("role") == "system"

    if has_system:
        # Keep system message + last (MAX-2) non-system messages + new message
        # We do this in app logic: fetch, trim, replace
        system_msg = current[0]
        rest = current[1:]
        rest.append(new_msg)
        # Keep last MAX_HISTORY_MESSAGES - 1 non-system messages
        trimmed_rest = rest[-(MAX_HISTORY_MESSAGES - 1):]
        new_messages = [system_msg] + trimmed_rest

        await col.update_one(
            {"session_id": session_id},
            {"$set": {"messages": new_messages}},
            upsert=True,
        )
    else:
        # No system message — use atomic $push + $slice
        await col.update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "messages": {
                        "$each": [new_msg],
                        "$slice": -MAX_HISTORY_MESSAGES,
                    }
                }
            },
            upsert=True,
        )

    logger.debug(
        "history.append — session=%s, role=%s",
        session_id, role,
    )


async def clear_history(session_id: str) -> None:
    """Delete the history document for a session."""
    col = _get_collection()
    await col.delete_one({"session_id": session_id})


async def message_count(session_id: str) -> int:
    """Return the number of messages stored for a session."""
    history = await get_history(session_id)
    return len(history)


# ── Backwards-compat shim for tests that use get_history_store() ──────────────

class _HistoryStoreShim:
    """
    Thin shim so existing tests that call get_history_store().get() / .append()
    continue to work. Routes should call get_history() / append_to_history() directly.
    """

    def get(self, session_id: str) -> list[dict]:
        raise RuntimeError(
            "HistoryStore is now async. Use 'await get_history(session_id)' instead."
        )

    def append(self, session_id: str, role: str, content: str) -> None:
        raise RuntimeError(
            "HistoryStore is now async. Use 'await append_to_history(session_id, role, content)' instead."
        )

    def message_count(self, session_id: str) -> int:
        raise RuntimeError("HistoryStore is now async.")

    def session_count(self) -> int:
        raise RuntimeError("HistoryStore is now async.")

    def clear(self, session_id: str) -> None:
        raise RuntimeError("HistoryStore is now async.")


def get_history_store() -> "_HistoryStoreShim":
    """Deprecated — use get_history() / append_to_history() directly."""
    return _HistoryStoreShim()
