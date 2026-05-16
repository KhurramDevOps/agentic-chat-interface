"""
app/services/user_service.py
─────────────────────────────
User identity and token metering service.

Collection: chotuu_db.users
Document shape:
  {
    "user_id":           "anon_<session_id>",   # or real user_id from gateway
    "session_id":        "test-user",
    "is_anonymous":      true,
    "total_tokens_used": 1234,
    "prompt_tokens":     800,
    "completion_tokens": 434,
    "created_at":        "2026-...",
    "last_seen_at":      "2026-..."
  }

Constitution compliance:
  - No blocking I/O — all MongoDB calls are awaited via motor.
  - No MongoDB URI in Settings — reads MONGODB_URI from os.environ directly.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.logging import get_logger

logger = get_logger(__name__)

_DB_NAME = "chotuu_db"
_COLLECTION = "users"

_client: AsyncIOMotorClient | None = None


def _get_collection():
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        logger.info("UserService: motor client connected → %s", uri.split("@")[-1])
    return _client[_DB_NAME][_COLLECTION]


async def get_or_create_user(session_id: str, user_id: str | None = None) -> dict:
    """
    Return the user document for the given session_id, creating one if absent.

    If user_id is provided (e.g. from a gateway JWT), it is used as the
    primary identifier. Otherwise an anonymous profile is created keyed by
    session_id with a prefixed anon_ user_id.

    Returns the full user document (without MongoDB _id).
    """
    col = _get_collection()
    effective_user_id = user_id or f"anon_{session_id}"

    try:
        doc = await col.find_one(
            {"user_id": effective_user_id},
            {"_id": 0},
        )
        if doc:
            # Refresh last_seen_at
            await col.update_one(
                {"user_id": effective_user_id},
                {"$set": {"last_seen_at": _now()}},
            )
            return doc

        # Create new profile
        new_user = {
            "user_id": effective_user_id,
            "session_id": session_id,
            "is_anonymous": user_id is None,
            "total_tokens_used": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "created_at": _now(),
            "last_seen_at": _now(),
        }
        await col.insert_one(new_user)
        logger.info(
            "UserService: new user created — user_id=%s, anonymous=%s",
            effective_user_id, user_id is None,
        )
        return {k: v for k, v in new_user.items() if k != "_id"}

    except Exception as exc:
        logger.warning("get_or_create_user failed — session=%s, error=%s", session_id, exc)
        # Return a transient in-memory profile so the request still succeeds
        return {
            "user_id": effective_user_id,
            "session_id": session_id,
            "is_anonymous": True,
            "total_tokens_used": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }


async def record_token_usage(
    session_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    user_id: str | None = None,
) -> None:
    """
    Atomically increment token counters for the user associated with session_id.
    Creates the user profile first if it doesn't exist.
    """
    if prompt_tokens == 0 and completion_tokens == 0:
        return

    col = _get_collection()
    effective_user_id = user_id or f"anon_{session_id}"
    total = prompt_tokens + completion_tokens

    try:
        result = await col.update_one(
            {"user_id": effective_user_id},
            {
                "$inc": {
                    "total_tokens_used": total,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                "$set": {"last_seen_at": _now()},
            },
            upsert=True,
        )
        logger.info(
            "Token usage recorded — user_id=%s, prompt=%d, completion=%d, total_delta=%d",
            effective_user_id, prompt_tokens, completion_tokens, total,
        )
    except Exception as exc:
        logger.warning(
            "record_token_usage failed — user_id=%s, error=%s", effective_user_id, exc
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
