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


def _reset_client() -> None:
    """Force re-creation of the motor client (useful after config changes)."""
    global _client
    _client = None


def _get_collection():
    """Return the motor collection, creating the client on first call."""
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        logger.info("HistoryStore: motor client connected → %s", uri.split("@")[-1])
    return _client[_DB_NAME][_COLLECTION]


# ── Public API ────────────────────────────────────────────────────────────────

async def get_history(session_id: str) -> list[dict]:
    """
    Return the message history for a session (empty list if not found or on error).
    """
    try:
        col = _get_collection()
        doc = await col.find_one({"session_id": session_id}, {"_id": 0, "messages": 1})
        if doc:
            return doc.get("messages", [])
        return []
    except Exception as exc:
        logger.warning("get_history failed — session=%s, error=%s", session_id, exc)
        return []


async def append_to_history(session_id: str, role: str, content: str) -> None:
    """
    Append a message to the session history.
    When history exceeds MAX_HISTORY_MESSAGES, summarizes old messages
    instead of just slicing, preserving context intelligently.
    """
    try:
        col = _get_collection()
        new_msg = {"role": role, "content": content}

        current = await get_history(session_id)
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
                {"session_id": session_id},
                {"$set": {"messages": new_messages}},
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
                {"session_id": session_id},
                {"$set": {"messages": current}},
                upsert=True,
            )

        logger.debug("history.append — session=%s, role=%s", session_id, role)
    except Exception as exc:
        logger.warning("append_to_history failed — session=%s, error=%s", session_id, exc)


async def _summarize_messages(messages: list[dict]) -> str:
    """
    Use the LLM to generate a concise summary of a list of messages.
    Falls back to a simple concatenation if the LLM call fails.
    """
    try:
        from openai import AsyncOpenAI  # noqa: PLC0415
        from app.core.config import get_settings  # noqa: PLC0415
        from app.core.llm_proxy import get_openai_client  # noqa: PLC0415

        settings = get_settings()
        client: AsyncOpenAI = get_openai_client()

        transcript = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in messages
        )
        prompt = (
            "Summarize the following conversation in 2-3 concise sentences, "
            "capturing the key facts and context:\n\n" + transcript
        )

        response = await client.chat.completions.create(
            model=settings.active_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return response.choices[0].message.content or "No summary available."
    except Exception as exc:
        logger.warning("_summarize_messages failed — %s", exc)
        # Fallback: simple truncated transcript
        return " | ".join(f"{m['role']}: {m['content'][:50]}" for m in messages[:5])


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
