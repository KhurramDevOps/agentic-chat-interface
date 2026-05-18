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

import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_HISTORY_MESSAGES = 20

_DB_NAME = "chotuu_db"
_HISTORY_COLLECTION = "conversations"
_SESSIONS_COLLECTION = "chat_sessions"

# ── Motor client singleton ────────────────────────────────────────────────────

_client: AsyncIOMotorClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _reset_client() -> None:
    """Force re-creation of the motor client (useful after config changes)."""
    global _client, _client_loop
    if _client is not None:
        _client.close()
    _client = None
    _client_loop = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_ids(session_id: str, user_id: str) -> None:
    if not session_id or not session_id.strip():
        raise ValueError("session_id is required for history operations.")
    if not user_id or not user_id.strip():
        raise ValueError("user_id is required for history operations.")


def _get_db():
    """Return the motor collection, creating the client on first call."""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        if _client is not None:
            _client.close()
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        _client_loop = loop
        logger.info("HistoryStore: motor client connected → %s", uri.split("@")[-1])
    return _client[_DB_NAME]


def _get_collection():
    return _get_db()[_HISTORY_COLLECTION]


def _get_sessions_collection():
    return _get_db()[_SESSIONS_COLLECTION]


# ── Public API ────────────────────────────────────────────────────────────────

async def get_history(session_id: str, user_id: str) -> list[dict]:
    """
    Return the message history for a session (empty list if not found or on error).
    """
    _require_ids(session_id, user_id)
    try:
        col = _get_collection()
        doc = await col.find_one(
            {"session_id": session_id, "user_id": user_id},
            {"_id": 0, "messages": 1},
        )
        if doc:
            return doc.get("messages", [])
        return []
    except Exception as exc:
        logger.warning("get_history failed — session=%s, error=%s", session_id, exc)
        return []


async def append_to_history(session_id: str, user_id: str, role: str, content: str) -> None:
    """
    Append a message to the session history.
    When history exceeds MAX_HISTORY_MESSAGES, summarizes old messages
    instead of just slicing, preserving context intelligently.
    """
    _require_ids(session_id, user_id)
    try:
        col = _get_collection()
        new_msg = {"role": role, "content": content}

        current = await get_history(session_id=session_id, user_id=user_id)
        has_system = bool(current) and current[0].get("role") == "system"

        if has_system:
            system_msg = current[0]
            rest = current[1:]
            rest.append(new_msg)

            if len(rest) > MAX_HISTORY_MESSAGES - 1:
                # Summarize messages 0..9 of rest, keep 10+ and new message
                to_summarize = rest[:10]
                to_keep = rest[10:]
                summary_text = await _summarize_messages(to_summarize)
                summary_msg = {"role": "system", "content": f"Summary of previous conversation: {summary_text}"}
                new_messages = [system_msg, summary_msg] + to_keep
            else:
                new_messages = [system_msg] + rest

            await col.update_one(
                {"session_id": session_id, "user_id": user_id},
                {
                    "$set": {"messages": new_messages, "updated_at": _now()},
                    "$setOnInsert": {
                        "session_id": session_id,
                        "user_id": user_id,
                        "created_at": _now(),
                    },
                },
                upsert=True,
            )
        else:
            current.append(new_msg)
            if len(current) > MAX_HISTORY_MESSAGES:
                to_summarize = current[:10]
                to_keep = current[10:]
                summary_text = await _summarize_messages(to_summarize)
                summary_msg = {"role": "system", "content": f"Summary of previous conversation: {summary_text}"}
                current = [summary_msg] + to_keep

            await col.update_one(
                {"session_id": session_id, "user_id": user_id},
                {
                    "$set": {"messages": current, "updated_at": _now()},
                    "$setOnInsert": {
                        "session_id": session_id,
                        "user_id": user_id,
                        "created_at": _now(),
                    },
                },
                upsert=True,
            )

        await _touch_session(session_id=session_id, user_id=user_id, content=content)
        logger.debug("history.append — session=%s, role=%s", session_id, role)
    except Exception as exc:
        logger.warning("append_to_history failed — session=%s, error=%s", session_id, exc)


async def _summarize_messages(messages: list[dict]) -> str:
    """
    Use the LLM to generate a concise summary of a list of messages.
    Falls back to a simple concatenation if the LLM call fails.
    """
    try:
        from app.core.config import get_settings  # noqa: PLC0415
        from app.core.llm_proxy import chat_completion_with_fallback  # noqa: PLC0415

        settings = get_settings()

        transcript = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in messages
        )
        prompt = (
            "Summarize the following conversation in 2-3 concise sentences, "
            "capturing the key facts and context:\n\n" + transcript
        )

        response = await chat_completion_with_fallback(
            model=settings.active_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return response.choices[0].message.content or "No summary available."
    except Exception as exc:
        logger.warning("_summarize_messages failed — %s", exc)
        # Fallback: simple truncated transcript
        return " | ".join(f"{m['role']}: {m['content'][:50]}" for m in messages[:5])


async def save_message(session_id: str, user_id: str, role: str, content: str) -> None:
    """Alias used by routes that treat each turn as an audit event."""
    await append_to_history(session_id=session_id, user_id=user_id, role=role, content=content)


async def clear_history(session_id: str, user_id: str) -> None:
    """Delete the history document for a session."""
    _require_ids(session_id, user_id)
    col = _get_collection()
    await col.delete_one({"session_id": session_id, "user_id": user_id})
    await _get_sessions_collection().delete_one({"session_id": session_id, "user_id": user_id})


async def delete_history(session_id: str, user_id: str) -> None:
    """Compatibility alias for authenticated session deletion."""
    await clear_history(session_id=session_id, user_id=user_id)


async def get_sessions_for_user(user_id: str) -> list[dict]:
    if not user_id or not user_id.strip():
        raise ValueError("user_id is required to list sessions.")
    cursor = (
        _get_sessions_collection()
        .find({"user_id": user_id})
        .sort("last_message_at", -1)
        .limit(50)
    )
    sessions = await cursor.to_list(length=50)
    for session in sessions:
        if "_id" in session:
            session["_id"] = str(session["_id"])
    return sessions


async def message_count(session_id: str, user_id: str) -> int:
    """Return the number of messages stored for a session."""
    history = await get_history(session_id=session_id, user_id=user_id)
    return len(history)


async def create_indexes() -> None:
    """Create ownership and session indexes used by API routes."""
    await _get_collection().create_index([("user_id", 1), ("session_id", 1)])
    await _get_collection().create_index([("session_id", 1), ("updated_at", 1)])
    await _get_sessions_collection().create_index([("user_id", 1), ("last_message_at", -1)])


async def _touch_session(session_id: str, user_id: str, content: str) -> None:
    snippet = (content or "").strip()[:60]
    name = snippet or "New Chat"
    await _get_sessions_collection().update_one(
        {"session_id": session_id, "user_id": user_id},
        {
            "$set": {"last_message_at": _now()},
            "$setOnInsert": {
                "session_id": session_id,
                "user_id": user_id,
                "name": name,
                "is_named": bool(snippet),
                "created_at": _now(),
            },
        },
        upsert=True,
    )


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
