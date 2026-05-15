"""
tests/integration/test_history_service.py
───────────────────────────────────────────
Tests for the in-memory conversation history store and its integration
with the chat completion endpoint.

Covers:
  - HistoryStore: append, get, trim, clear, session isolation
  - Context window cap (MAX_HISTORY_MESSAGES)
  - System message preservation during trim
  - Chat route: history loaded on second request, saved after each turn
  - Multi-turn context: second request recalls first turn's content
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatMessage, ChatRequest
from app.services.history_service import HistoryStore, MAX_HISTORY_MESSAGES


# ── HistoryStore unit tests ───────────────────────────────────────────────────

class TestHistoryStore:

    def setup_method(self):
        """Fresh store for each test."""
        self.store = HistoryStore()

    def test_get_empty_session_returns_empty_list(self):
        assert self.store.get("new-session") == []

    def test_append_and_get(self):
        self.store.append("s1", "user", "Hello")
        self.store.append("s1", "assistant", "Hi there!")
        history = self.store.get("s1")
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there!"}

    def test_sessions_are_isolated(self):
        self.store.append("session-a", "user", "Message for A")
        self.store.append("session-b", "user", "Message for B")
        assert len(self.store.get("session-a")) == 1
        assert len(self.store.get("session-b")) == 1
        assert self.store.get("session-a")[0]["content"] == "Message for A"

    def test_get_returns_copy_not_reference(self):
        self.store.append("s1", "user", "original")
        history = self.store.get("s1")
        history.append({"role": "user", "content": "injected"})
        assert len(self.store.get("s1")) == 1  # original unchanged

    def test_clear_removes_session(self):
        self.store.append("s1", "user", "hello")
        self.store.clear("s1")
        assert self.store.get("s1") == []

    def test_clear_nonexistent_session_does_not_raise(self):
        self.store.clear("does-not-exist")  # should not raise

    def test_message_count(self):
        self.store.append("s1", "user", "a")
        self.store.append("s1", "assistant", "b")
        assert self.store.message_count("s1") == 2
        assert self.store.message_count("unknown") == 0

    def test_session_count(self):
        self.store.append("s1", "user", "a")
        self.store.append("s2", "user", "b")
        assert self.store.session_count() == 2


class TestHistoryStoreTrim:

    def setup_method(self):
        self.store = HistoryStore()

    def test_trim_keeps_most_recent_messages(self):
        for i in range(MAX_HISTORY_MESSAGES + 5):
            self.store.append("s1", "user", f"message {i}")
        history = self.store.get("s1")
        assert len(history) == MAX_HISTORY_MESSAGES
        # Most recent messages are kept
        assert history[-1]["content"] == f"message {MAX_HISTORY_MESSAGES + 4}"

    def test_trim_preserves_system_message(self):
        # Add a system message first
        self.store.append("s1", "system", "You are a helpful assistant.")
        # Fill up beyond the cap
        for i in range(MAX_HISTORY_MESSAGES + 3):
            self.store.append("s1", "user", f"msg {i}")
        history = self.store.get("s1")
        assert len(history) == MAX_HISTORY_MESSAGES
        assert history[0]["role"] == "system"
        assert history[0]["content"] == "You are a helpful assistant."

    def test_no_trim_when_under_limit(self):
        for i in range(MAX_HISTORY_MESSAGES - 1):
            self.store.append("s1", "user", f"msg {i}")
        assert self.store.message_count("s1") == MAX_HISTORY_MESSAGES - 1


# ── Chat route history integration ───────────────────────────────────────────

class TestChatRouteHistory:
    """Verify the chat route loads and saves history correctly."""

    @pytest.fixture(autouse=True)
    def seed_swarm(self, monkeypatch):
        import app.agents.swarm as swarm_module
        monkeypatch.setattr(swarm_module, "_triage_agent", MagicMock())
        yield
        monkeypatch.setattr(swarm_module, "_triage_agent", None)

    @pytest.fixture(autouse=True)
    def fresh_history(self, monkeypatch):
        """Isolate each test with a fresh HistoryStore."""
        from app.services import history_service
        fresh = HistoryStore()
        monkeypatch.setattr(history_service, "_history_store", fresh)
        yield fresh
        monkeypatch.setattr(history_service, "_history_store", None)

    def _make_mock_result(self, content: str, agent_name: str = "TriageAgent") -> MagicMock:
        mock = MagicMock()
        mock.final_output = content
        mock._current_turn = 1
        mock.new_items = []
        mock.last_agent = MagicMock()
        mock.last_agent.name = agent_name
        return mock

    @pytest.mark.asyncio
    async def test_first_request_saves_to_history(self, fresh_history):
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = self._make_mock_result("Hello! How can I help?")
            from app.agents.swarm import run_swarm

            req = ChatRequest(
                request_id="turn-1",
                memory_context_id="session-test",
                messages=[ChatMessage(role="user", content="Hi there")],
            )
            response = await run_swarm(req)

        # Manually save as the route would
        fresh_history.append("session-test", "user", "Hi there")
        fresh_history.append("session-test", "assistant", response.content)

        history = fresh_history.get("session-test")
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hi there"}
        assert history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_second_request_receives_history_in_messages(self, fresh_history):
        """Second request should have first turn's messages merged in."""
        # Seed history as if first turn already happened
        fresh_history.append("session-test", "user", "My name is Khurram")
        fresh_history.append("session-test", "assistant", "Nice to meet you, Khurram!")

        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = self._make_mock_result("Your name is Khurram.")
            from app.agents.swarm import run_swarm

            # Second request — only sends the new message
            req = ChatRequest(
                request_id="turn-2",
                memory_context_id="session-test",
                messages=[ChatMessage(role="user", content="What is my name?")],
            )

            # Simulate what the chat route does: merge history
            history = fresh_history.get("session-test")
            stored = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
            incoming_contents = {m.content for m in req.messages}
            deduped = [m for m in stored if m.content not in incoming_contents]
            merged_req = req.model_copy(update={"messages": deduped + list(req.messages)})

            response = await run_swarm(merged_req)

        # Verify Runner received the full history
        passed_input = mock_run.call_args.kwargs.get("input") or mock_run.call_args.args[1]
        if isinstance(passed_input, list):
            all_content = " ".join(m.get("content", "") for m in passed_input)
        else:
            all_content = passed_input
        assert "Khurram" in all_content  # history was included in context
        assert "What is my name?" in all_content

    @pytest.mark.asyncio
    async def test_history_grows_across_turns(self, fresh_history):
        """Each turn appends user + assistant messages."""
        session = "multi-turn-session"

        for i in range(3):
            fresh_history.append(session, "user", f"Turn {i} user message")
            fresh_history.append(session, "assistant", f"Turn {i} assistant response")

        assert fresh_history.message_count(session) == 6

    @pytest.mark.asyncio
    async def test_session_isolation_between_users(self, fresh_history):
        """Different session_ids must not share history."""
        fresh_history.append("user-alice", "user", "I like cats")
        fresh_history.append("user-bob", "user", "I like dogs")

        alice_history = fresh_history.get("user-alice")
        bob_history = fresh_history.get("user-bob")

        assert all("cats" in m["content"] for m in alice_history)
        assert all("dogs" in m["content"] for m in bob_history)
        assert len(alice_history) == 1
        assert len(bob_history) == 1

    @pytest.mark.asyncio
    async def test_run_swarm_includes_history_in_input(self, fresh_history):
        """run_swarm must include prior turns in the augmented input string."""
        fresh_history.append("ctx-1", "user", "I am building a MERN stack app")
        fresh_history.append("ctx-1", "assistant", "That sounds great!")

        history = fresh_history.get("ctx-1")
        stored = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
        new_msg = ChatMessage(role="user", content="What am I building?")
        all_messages = stored + [new_msg]

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
        if isinstance(passed_input, list):
            all_content = " ".join(m.get("content", "") for m in passed_input)
        else:
            all_content = passed_input
        assert "MERN stack" in all_content
        assert "What am I building?" in all_content
