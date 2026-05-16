"""
tests/integration/test_history_mongodb.py
───────────────────────────────────────────
Real MongoDB integration tests for the motor-backed history service.

Uses a dedicated test database (chotuu_test_db) to avoid touching production data.
Each test gets a clean collection via the autouse fixture.

Requirements: local MongoDB running on mongodb://localhost:27017
Skip automatically if MongoDB is not available.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# ── Test DB setup ─────────────────────────────────────────────────────────────

TEST_DB = "chotuu_test_db"
TEST_COLLECTION = "conversations"
MONGO_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017").split("?")[0]
# Strip any database name from URI for clean test connection
if "/" in MONGO_URI.replace("mongodb://", "").replace("mongodb+srv://", ""):
    parts = MONGO_URI.rsplit("/", 1)
    if len(parts) == 2 and parts[1]:
        MONGO_URI = parts[0]


def _test_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=2000)


async def _is_mongo_available() -> bool:
    try:
        client = _test_client()
        await client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def clean_collection():
    """Drop the test collection before each test for full isolation."""
    if not await _is_mongo_available():
        pytest.skip("MongoDB not available — skipping MongoDB integration tests")

    client = _test_client()
    col = client[TEST_DB][TEST_COLLECTION]
    await col.drop()
    yield col
    await col.drop()
    client.close()


@pytest_asyncio.fixture
async def patched_service(monkeypatch, clean_collection):
    """
    Patch history_service to use the test DB collection instead of production.
    """
    import app.services.history_service as svc

    # Reset the singleton so it gets recreated with test settings
    monkeypatch.setattr(svc, "_client", None)
    monkeypatch.setattr(svc, "_DB_NAME", TEST_DB)

    yield svc

    # Cleanup: reset singleton
    monkeypatch.setattr(svc, "_client", None)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGetHistory:

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_unknown_session(self, patched_service):
        result = await patched_service.get_history("unknown-session")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_messages_after_append(self, patched_service):
        await patched_service.append_to_history("s1", "user", "Hello")
        result = await patched_service.get_history("s1")
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "Hello"}

    @pytest.mark.asyncio
    async def test_returns_all_messages_in_order(self, patched_service):
        await patched_service.append_to_history("s1", "user", "First")
        await patched_service.append_to_history("s1", "assistant", "Second")
        await patched_service.append_to_history("s1", "user", "Third")
        result = await patched_service.get_history("s1")
        assert len(result) == 3
        assert result[0]["content"] == "First"
        assert result[1]["content"] == "Second"
        assert result[2]["content"] == "Third"


class TestAppendToHistory:

    @pytest.mark.asyncio
    async def test_creates_document_on_first_append(self, patched_service, clean_collection):
        await patched_service.append_to_history("new-session", "user", "Hi")
        doc = await clean_collection.find_one({"session_id": "new-session"})
        assert doc is not None
        assert len(doc["messages"]) == 1
        assert doc["messages"][0] == {"role": "user", "content": "Hi"}

    @pytest.mark.asyncio
    async def test_appends_to_existing_session(self, patched_service):
        await patched_service.append_to_history("s1", "user", "msg1")
        await patched_service.append_to_history("s1", "assistant", "msg2")
        result = await patched_service.get_history("s1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_sessions_are_isolated(self, patched_service):
        await patched_service.append_to_history("alice", "user", "Alice message")
        await patched_service.append_to_history("bob", "user", "Bob message")
        alice = await patched_service.get_history("alice")
        bob = await patched_service.get_history("bob")
        assert len(alice) == 1
        assert len(bob) == 1
        assert alice[0]["content"] == "Alice message"
        assert bob[0]["content"] == "Bob message"


class TestHistoryTrimming:

    @pytest.mark.asyncio
    async def test_trims_to_max_history_messages(self, patched_service):
        from app.services.history_service import MAX_HISTORY_MESSAGES
        # Add more than the cap
        for i in range(MAX_HISTORY_MESSAGES + 5):
            await patched_service.append_to_history("s1", "user", f"message {i}")
        result = await patched_service.get_history("s1")
        assert len(result) <= MAX_HISTORY_MESSAGES

    @pytest.mark.asyncio
    async def test_preserves_system_message_at_index_0(self, patched_service):
        from app.services.history_service import MAX_HISTORY_MESSAGES
        # First add a system message
        await patched_service.append_to_history("s1", "system", "You are helpful.")
        # Fill beyond the cap
        for i in range(MAX_HISTORY_MESSAGES + 3):
            await patched_service.append_to_history("s1", "user", f"msg {i}")
        result = await patched_service.get_history("s1")
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful."
        assert len(result) <= MAX_HISTORY_MESSAGES

    @pytest.mark.asyncio
    async def test_keeps_most_recent_messages_after_trim(self, patched_service):
        from app.services.history_service import MAX_HISTORY_MESSAGES
        total = MAX_HISTORY_MESSAGES + 5
        for i in range(total):
            await patched_service.append_to_history("s1", "user", f"message {i}")
        result = await patched_service.get_history("s1")
        # Last message should be the most recent
        assert result[-1]["content"] == f"message {total - 1}"


class TestClearHistory:

    @pytest.mark.asyncio
    async def test_clear_removes_session(self, patched_service):
        await patched_service.append_to_history("s1", "user", "hello")
        await patched_service.clear_history("s1")
        result = await patched_service.get_history("s1")
        assert result == []

    @pytest.mark.asyncio
    async def test_clear_nonexistent_session_does_not_raise(self, patched_service):
        await patched_service.clear_history("does-not-exist")  # should not raise
