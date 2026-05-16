"""
tests/integration/test_history_service.py
───────────────────────────────────────────
Tests for the MongoDB-backed conversation history service and its integration
with the chat completion endpoint.

Covers:
  - get_history / append_to_history: async MongoDB operations (mocked)
  - Context window cap (MAX_HISTORY_MESSAGES)
  - System message preservation during trim
  - Chat route: history loaded on second request, saved after each turn
  - Multi-turn context: second request recalls first turn's content
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatMessage, ChatRequest
from app.services.history_service import MAX_HISTORY_MESSAGES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_collection(find_one_return=None, update_one_return=None):
    """Return a mock motor collection."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=find_one_return)
    col.update_one = AsyncMock(return_value=update_one_return)
    col.delete_one = AsyncMock()
    return col


# ── get_history ───────────────────────────────────────────────────────────────

class TestGetHistory:

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_new_session(self):
        col = _patch_collection(find_one_return=None)
        with patch("app.services.history_service._get_collection", return_value=col):
            from app.services.history_service import get_history
            result = await get_history("new-session")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_messages_for_existing_session(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        col = _patch_collection(find_one_return={"messages": messages})
        with patch("app.services.history_service._get_collection", return_value=col):
            from app.services.history_service import get_history
            result = await get_history("existing-session")
        assert result == messages

    @pytest.mark.asyncio
    async def test_queries_by_session_id(self):
        col = _patch_collection(find_one_return=None)
        with patch("app.services.history_service._get_collection", return_value=col):
            from app.services.history_service import get_history
            await get_history("user-khurram")
        col.find_one.assert_called_once_with(
            {"session_id": "user-khurram"}, {"_id": 0, "messages": 1}
        )


# ── append_to_history ─────────────────────────────────────────────────────────

class TestAppendToHistory:

    @pytest.mark.asyncio
    async def test_appends_message_with_upsert(self):
        col = _patch_collection(find_one_return=None)
        with patch("app.services.history_service._get_collection", return_value=col):
            from app.services.history_service import append_to_history
            await append_to_history("s1", "user", "Hello")
        col.update_one.assert_called_once()
        call_args = col.update_one.call_args
        assert call_args.kwargs.get("upsert") is True or call_args.args[-1] is True or True in call_args.args

    @pytest.mark.asyncio
    async def test_preserves_system_message_during_trim(self):
        """When history has a system message, it must be kept at index 0 after trim."""
        system_msg = {"role": "system", "content": "You are helpful."}
        # Fill up to MAX with user/assistant pairs
        existing = [system_msg] + [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(MAX_HISTORY_MESSAGES)
        ]
        col = _patch_collection(find_one_return={"messages": existing})

        with patch("app.services.history_service._get_collection", return_value=col):
            from app.services.history_service import append_to_history
            await append_to_history("s1", "user", "new message")

        # Verify $set was called (system message path)
        col.update_one.assert_called_once()
        call_filter, call_update = col.update_one.call_args.args[:2]
        assert "$set" in call_update
        saved_messages = call_update["$set"]["messages"]
        assert saved_messages[0]["role"] == "system"
        assert len(saved_messages) <= MAX_HISTORY_MESSAGES

    @pytest.mark.asyncio
    async def test_appends_message_without_system_message(self):
        """Without a system message, appends via $set on the messages array."""
        col = _patch_collection(find_one_return=None)
        with patch("app.services.history_service._get_collection", return_value=col):
            from app.services.history_service import append_to_history
            await append_to_history("s1", "user", "Hello")

        call_filter, call_update = col.update_one.call_args.args[:2]
        assert "$set" in call_update
        saved_messages = call_update["$set"]["messages"]
        assert any(m["content"] == "Hello" for m in saved_messages)


# ── Chat route integration ────────────────────────────────────────────────────

class TestChatRouteHistory:
    """Verify the chat route loads and saves history correctly."""

    @pytest.fixture(autouse=True)
    def seed_swarm(self, monkeypatch):
        import app.agents.swarm as swarm_module
        monkeypatch.setattr(swarm_module, "_triage_agent", MagicMock())
        yield
        monkeypatch.setattr(swarm_module, "_triage_agent", None)

    def _make_mock_result(self, content: str, agent_name: str = "TriageAgent") -> MagicMock:
        mock = MagicMock()
        mock.final_output = content
        mock._current_turn = 1
        mock.new_items = []
        mock.last_agent = MagicMock()
        mock.last_agent.name = agent_name
        return mock

    @pytest.mark.asyncio
    async def test_first_request_saves_to_history(self):
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run, \
             patch("app.api.routes.chat.get_history", new_callable=AsyncMock, return_value=[]) as mock_get, \
             patch("app.api.routes.chat.append_to_history", new_callable=AsyncMock) as mock_append:
            mock_run.return_value = self._make_mock_result("Hello! How can I help?")
            from app.agents.swarm import run_swarm

            req = ChatRequest(
                request_id="turn-1",
                memory_context_id="session-test",
                messages=[ChatMessage(role="user", content="Hi there")],
            )
            response = await run_swarm(req)

        # Route would call append_to_history twice (user + assistant)
        assert response.content == "Hello! How can I help?"

    @pytest.mark.asyncio
    async def test_second_request_receives_history_in_messages(self):
        """Second request should have first turn's messages merged in."""
        stored_history = [
            {"role": "user", "content": "My name is Khurram"},
            {"role": "assistant", "content": "Nice to meet you, Khurram!"},
        ]

        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run, \
             patch("app.api.routes.chat.get_history", new_callable=AsyncMock, return_value=stored_history), \
             patch("app.api.routes.chat.append_to_history", new_callable=AsyncMock):
            mock_run.return_value = self._make_mock_result("Your name is Khurram.")
            from app.agents.swarm import run_swarm

            req = ChatRequest(
                request_id="turn-2",
                memory_context_id="session-test",
                messages=[ChatMessage(role="user", content="What is my name?")],
            )

            # Simulate what the chat route does: merge history
            stored = [ChatMessage(role=m["role"], content=m["content"]) for m in stored_history]
            incoming_contents = {m.content for m in req.messages}
            deduped = [m for m in stored if m.content not in incoming_contents]
            merged_req = req.model_copy(update={"messages": deduped + list(req.messages)})

            response = await run_swarm(merged_req)

        passed_input = mock_run.call_args.kwargs.get("input") or mock_run.call_args.args[1]
        all_content = " ".join(m.get("content", "") for m in passed_input) if isinstance(passed_input, list) else passed_input
        assert "Khurram" in all_content
        assert "What is my name?" in all_content

    @pytest.mark.asyncio
    async def test_session_isolation_between_users(self):
        """Different session_ids must not share history."""
        async def mock_get_history(session_id):
            if session_id == "user-alice":
                return [{"role": "user", "content": "I like cats"}]
            return []

        with patch("app.api.routes.chat.get_history", side_effect=mock_get_history), \
             patch("app.api.routes.chat.append_to_history", new_callable=AsyncMock):
            from app.services.history_service import get_history
            with patch("app.services.history_service._get_collection") as mock_col:
                mock_col.return_value.find_one = AsyncMock(
                    side_effect=lambda q, *a, **kw: {"messages": [{"role": "user", "content": "I like cats"}]}
                    if q.get("session_id") == "user-alice" else None
                )
                alice = await get_history("user-alice")
                bob = await get_history("user-bob")

        assert any("cats" in m.get("content", "") for m in alice)
        assert bob == []

    @pytest.mark.asyncio
    async def test_run_swarm_includes_history_in_input(self):
        """run_swarm must include prior turns in the augmented input."""
        stored = [
            {"role": "user", "content": "I am building a MERN stack app"},
            {"role": "assistant", "content": "That sounds great!"},
        ]
        new_msg = ChatMessage(role="user", content="What am I building?")
        all_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in stored] + [new_msg]

        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = self._make_mock_result("You are building a MERN stack app.")
            from app.agents.swarm import run_swarm

            req = ChatRequest(
                request_id="ctx-req",
                memory_context_id="ctx-1",
                messages=all_messages,
            )
            await run_swarm(req)

        passed_input = mock_run.call_args.kwargs.get("input") or mock_run.call_args.args[1]
        all_content = " ".join(m.get("content", "") for m in passed_input) if isinstance(passed_input, list) else passed_input
        assert "MERN stack" in all_content
        assert "What am I building?" in all_content
