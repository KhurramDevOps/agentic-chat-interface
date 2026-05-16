"""
tests/integration/test_services.py
────────────────────────────────────
Tests for HistoryService and UserService with mocked MongoDB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── HistoryService ────────────────────────────────────────────────────────────

class TestHistoryService:

    @pytest.mark.asyncio
    async def test_get_history_returns_messages(self):
        from app.services.history_service import get_history

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value={
            "session_id": "s1",
            "messages": [{"role": "user", "content": "hello"}],
        })

        with patch("app.services.history_service._get_collection", return_value=mock_col):
            result = await get_history("s1")

        assert result == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_get_history_returns_empty_for_missing_session(self):
        from app.services.history_service import get_history

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=None)

        with patch("app.services.history_service._get_collection", return_value=mock_col):
            result = await get_history("nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_history_returns_empty_on_error(self):
        from app.services.history_service import get_history

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(side_effect=Exception("mongo down"))

        with patch("app.services.history_service._get_collection", return_value=mock_col):
            result = await get_history("s1")

        assert result == []

    @pytest.mark.asyncio
    async def test_append_to_history_upserts(self):
        from app.services.history_service import append_to_history

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=None)
        mock_col.update_one = AsyncMock()

        with patch("app.services.history_service._get_collection", return_value=mock_col):
            await append_to_history("s1", "user", "hello")

        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        assert call_args[1]["upsert"] is True

    @pytest.mark.asyncio
    async def test_append_preserves_existing_messages(self):
        from app.services.history_service import append_to_history

        existing = [{"role": "user", "content": "first message"}]
        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value={"messages": existing})
        mock_col.update_one = AsyncMock()

        with patch("app.services.history_service._get_collection", return_value=mock_col):
            await append_to_history("s1", "assistant", "response")

        # The update_one call should include both messages
        call_args = mock_col.update_one.call_args
        new_messages = call_args[0][1]["$set"]["messages"]
        assert len(new_messages) == 2
        assert new_messages[0]["content"] == "first message"
        assert new_messages[1]["content"] == "response"

    @pytest.mark.asyncio
    async def test_clear_history_deletes_document(self):
        from app.services.history_service import clear_history

        mock_col = MagicMock()
        mock_col.delete_one = AsyncMock()

        with patch("app.services.history_service._get_collection", return_value=mock_col):
            await clear_history("s1")

        mock_col.delete_one.assert_called_once_with({"session_id": "s1"})

    @pytest.mark.asyncio
    async def test_message_count_returns_correct_number(self):
        from app.services.history_service import message_count

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value={
            "messages": [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"},
            ]
        })

        with patch("app.services.history_service._get_collection", return_value=mock_col):
            count = await message_count("s1")

        assert count == 3


# ── UserService ───────────────────────────────────────────────────────────────

class TestUserService:

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing_user(self):
        from app.services.user_service import get_or_create_user

        existing = {
            "user_id": "anon_s1", "session_id": "s1",
            "is_anonymous": True, "total_tokens_used": 50,
            "prompt_tokens": 30, "completion_tokens": 20,
        }
        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=existing)
        mock_col.update_one = AsyncMock()

        with patch("app.services.user_service._get_collection", return_value=mock_col):
            result = await get_or_create_user("s1")

        assert result["user_id"] == "anon_s1"
        assert result["total_tokens_used"] == 50

    @pytest.mark.asyncio
    async def test_get_or_create_inserts_new_user(self):
        from app.services.user_service import get_or_create_user

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=None)
        mock_col.insert_one = AsyncMock()

        with patch("app.services.user_service._get_collection", return_value=mock_col):
            result = await get_or_create_user("new-session")

        mock_col.insert_one.assert_called_once()
        assert result["session_id"] == "new-session"
        assert result["is_anonymous"] is True
        assert result["total_tokens_used"] == 0

    @pytest.mark.asyncio
    async def test_get_or_create_uses_provided_user_id(self):
        from app.services.user_service import get_or_create_user

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=None)
        mock_col.insert_one = AsyncMock()

        with patch("app.services.user_service._get_collection", return_value=mock_col):
            result = await get_or_create_user("s1", user_id="real-user-123")

        assert result["user_id"] == "real-user-123"
        assert result["is_anonymous"] is False

    @pytest.mark.asyncio
    async def test_record_token_usage_increments_counters(self):
        from app.services.user_service import record_token_usage

        mock_col = MagicMock()
        mock_col.update_one = AsyncMock()

        with patch("app.services.user_service._get_collection", return_value=mock_col):
            await record_token_usage("s1", prompt_tokens=100, completion_tokens=50)

        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        inc = call_args[0][1]["$inc"]
        assert inc["prompt_tokens"] == 100
        assert inc["completion_tokens"] == 50
        assert inc["total_tokens_used"] == 150

    @pytest.mark.asyncio
    async def test_record_token_usage_skips_zeros(self):
        from app.services.user_service import record_token_usage

        mock_col = MagicMock()
        mock_col.update_one = AsyncMock()

        with patch("app.services.user_service._get_collection", return_value=mock_col):
            await record_token_usage("s1", prompt_tokens=0, completion_tokens=0)

        mock_col.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_returns_fallback_on_error(self):
        from app.services.user_service import get_or_create_user

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(side_effect=Exception("mongo down"))

        with patch("app.services.user_service._get_collection", return_value=mock_col):
            result = await get_or_create_user("s1")

        # Should return a transient profile, not raise
        assert result["session_id"] == "s1"
        assert result["total_tokens_used"] == 0
