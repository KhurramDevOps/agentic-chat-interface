"""
app/services/memory_service.py
───────────────────────────────
Shared long-term memory helpers for every chat entry point.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

import litellm
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_DB_NAME = "chotuu_db"
_COLLECTION = "long_term_memories"
_client: AsyncIOMotorClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _get_db():
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        if _client is not None:
            _client.close()
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        _client_loop = loop
        logger.info("MemoryService: motor client connected → %s", uri.split("@")[-1])
    return _client[_DB_NAME]


async def get_memory_context_for_user(user_id: str) -> str:
    """
    Retrieve top relevant long-term memories for a user.
    Call this at the start of EVERY chat request.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id is required for memory lookup.")

    memories = await (
        _get_db()[_COLLECTION]
        .find({"user_id": user_id})
        .sort("importance", -1)
        .limit(5)
        .to_list(length=5)
    )

    if not memories:
        return ""

    memory_lines = [f"- {m['content']}" for m in memories if m.get("content")]
    if not memory_lines:
        return ""
    return "Relevant things I remember about you:\n" + "\n".join(memory_lines)


async def extract_memories_background(
    messages: list[dict],
    user_id: str,
    session_id: str,
) -> None:
    """
    Extract and store important facts from conversation.
    Always fire-and-forget; failures never affect the user response.
    """
    try:
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required for memory extraction.")

        settings = get_settings()
        conversation = "\n".join(
            f"{m['role'].upper()}: {str(m['content'])[:300]}"
            for m in messages[-10:]
        )

        response = await litellm.acompletion(
            model=f"groq/{settings.fast_model}",
            messages=[{
                "role": "user",
                "content": (
                    "Extract important facts about the USER from this conversation "
                    "(name, preferences, goals, job, important dates). "
                    "Return ONLY a JSON array, no other text:\n"
                    '[{"content": "User prefers dark mode", "importance": 8, "tags": ["preference"]}]\n'
                    "Importance 1-10. Only include facts scored 7+. "
                    "Return [] if nothing worth saving.\n\n"
                    f"Conversation:\n{conversation}"
                ),
            }],
            max_tokens=300,
            api_key=settings.groq_api_key,
        )

        raw = (response.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        facts = json.loads(raw or "[]")
        if not isinstance(facts, list):
            return

        col = _get_db()[_COLLECTION]
        for fact in facts:
            if not isinstance(fact, dict) or not fact.get("content"):
                continue
            importance = int(fact.get("importance", 7))
            if importance < 7:
                continue

            existing = await col.find_one({
                "user_id": user_id,
                "content": {"$regex": fact["content"][:40], "$options": "i"},
            })
            if existing:
                continue

            now = datetime.now(timezone.utc)
            await col.insert_one({
                "user_id": user_id,
                "content": fact["content"],
                "importance": importance,
                "source_session_id": session_id,
                "tags": fact.get("tags", []),
                "created_at": now,
                "last_accessed_at": now,
            })
    except Exception as exc:
        logger.warning("Memory extraction failed | user:%s | %s", user_id, exc)


async def create_indexes() -> None:
    await _get_db()[_COLLECTION].create_index([("user_id", 1), ("importance", -1)])
