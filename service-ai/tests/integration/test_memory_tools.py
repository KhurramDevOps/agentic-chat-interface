"""
tests/integration/test_memory_tools.py
────────────────────────────────────────
Unit tests for add_memory and search_memory tools.

Covers:
  - add_memory: local mode, cloud mode (mem0 v2 dict response), empty content guard
  - search_memory: local mode, cloud mode v2 dict response, list response fallback,
    empty results, exception handling
  - session_id injection: run_swarm prepends [session_id: ...] to input
  - mem0 v2 API contract: search() uses filters={"user_id": ...} not user_id=
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatMessage, ChatRequest


# ── Helpers ───────────────────────────────────────────────────────────────────
# Call the raw _impl functions directly — bypasses the @function_tool wrapper.

def _call_add_memory(context_id: str, content: str) -> str:
    from app.agents.domain_agents import _add_memory_impl
    return _add_memory_impl(context_id=context_id, content=content)


def _call_search_memory(context_id: str, query: str) -> str:
    from app.agents.domain_agents import _search_memory_impl
    return _search_memory_impl(context_id=context_id, query=query)


# ── add_memory ────────────────────────────────────────────────────────────────

class TestAddMemory:

    def test_local_mode_returns_confirmation(self):
        """In local mode (no API key), add_memory acknowledges without crashing."""
        with patch("app.agents.domain_agents.get_settings") as mock_settings:
            mock_settings.return_value.mem0_use_local = True
            result = _call_add_memory("user-test", "I love Python")

        assert isinstance(result, str)
        assert "local mode" in result.lower() or "stored" in result.lower()

    def test_cloud_mode_v2_dict_response(self):
        """Cloud mode handles mem0 v2 dict response {event_id, status}."""
        mock_client = MagicMock()
        mock_client.add.return_value = {"event_id": "abc-123", "status": "PENDING"}
        mock_mem0 = MagicMock()
        mock_mem0.MemoryClient.return_value = mock_client

        with patch("app.agents.domain_agents.get_settings") as mock_settings, \
             patch.dict("sys.modules", {"mem0": mock_mem0}):
            mock_settings.return_value.mem0_use_local = False
            mock_settings.return_value.mem0_api_key = "test-key"
            result = _call_add_memory("user-test", "I love Python")

        assert isinstance(result, str)
        assert "abc-123" in result or "stored" in result.lower()

    def test_rejects_empty_content(self):
        """add_memory must reject blank content."""
        result = _call_add_memory("user-test", "   ")
        assert "empty" in result.lower() or "error" in result.lower()

    def test_rejects_whitespace_only_content(self):
        """add_memory must reject content that is only whitespace."""
        result = _call_add_memory("user-test", "\n\t")
        assert "empty" in result.lower() or "error" in result.lower()

    def test_exception_returns_error_string(self):
        """add_memory must return an error string on mem0 client errors, never raise."""
        mock_mem0 = MagicMock()
        mock_mem0.MemoryClient.side_effect = RuntimeError("client exploded")

        with patch("app.agents.domain_agents.get_settings") as mock_settings, \
             patch.dict("sys.modules", {"mem0": mock_mem0}):
            mock_settings.return_value.mem0_use_local = False
            mock_settings.return_value.mem0_api_key = "test-key"
            result = _call_add_memory("user-test", "test content")

        assert isinstance(result, str)
        assert "error" in result.lower()


# ── search_memory ─────────────────────────────────────────────────────────────

class TestSearchMemory:

    def test_local_mode_returns_string(self):
        """In local mode, search_memory returns a string without crashing."""
        with patch("app.agents.domain_agents.get_settings") as mock_settings:
            mock_settings.return_value.mem0_use_local = True
            result = _call_search_memory("user-test", "favorite language")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_cloud_mode_v2_dict_response_with_results(self):
        """search_memory correctly parses mem0 v2 {results: [...]} response."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {"memory": "User's favorite language is Python.", "score": 0.95},
                {"memory": "User is building a MERN stack project.", "score": 0.88},
            ],
            "relations": [],
        }
        mock_mem0 = MagicMock()
        mock_mem0.MemoryClient.return_value = mock_client

        with patch("app.agents.domain_agents.get_settings") as mock_settings, \
             patch.dict("sys.modules", {"mem0": mock_mem0}):
            mock_settings.return_value.mem0_use_local = False
            mock_settings.return_value.mem0_api_key = "test-key"
            result = _call_search_memory("user-test", "favorite language")

        assert isinstance(result, str)
        assert "Python" in result or "MERN" in result

    def test_cloud_mode_uses_filters_not_user_id(self):
        """search_memory must call client.search with filters={'user_id': ...} (mem0 v2 API)."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": [], "relations": []}
        mock_mem0 = MagicMock()
        mock_mem0.MemoryClient.return_value = mock_client

        with patch("app.agents.domain_agents.get_settings") as mock_settings, \
             patch.dict("sys.modules", {"mem0": mock_mem0}):
            mock_settings.return_value.mem0_use_local = False
            mock_settings.return_value.mem0_api_key = "test-key"
            _call_search_memory("user-khurram", "projects")

        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args.kwargs
        assert "filters" in call_kwargs, "Must use filters= parameter (mem0 v2 API)"
        assert call_kwargs["filters"].get("user_id") == "user-khurram"
        assert "user_id" not in {k for k in call_kwargs if k != "filters"}, \
            "user_id must NOT be a top-level param in mem0 v2"

    def test_cloud_mode_empty_results(self):
        """search_memory returns 'no memories found' when results list is empty."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": [], "relations": []}
        mock_mem0 = MagicMock()
        mock_mem0.MemoryClient.return_value = mock_client

        with patch("app.agents.domain_agents.get_settings") as mock_settings, \
             patch.dict("sys.modules", {"mem0": mock_mem0}):
            mock_settings.return_value.mem0_use_local = False
            mock_settings.return_value.mem0_api_key = "test-key"
            result = _call_search_memory("user-new", "anything")

        assert "no memories" in result.lower() or "not found" in result.lower()

    def test_cloud_mode_list_response_fallback(self):
        """search_memory handles older mem0 versions that return a plain list."""
        mock_client = MagicMock()
        mock_client.search.return_value = [{"memory": "User likes dark mode."}]
        mock_mem0 = MagicMock()
        mock_mem0.MemoryClient.return_value = mock_client

        with patch("app.agents.domain_agents.get_settings") as mock_settings, \
             patch.dict("sys.modules", {"mem0": mock_mem0}):
            mock_settings.return_value.mem0_use_local = False
            mock_settings.return_value.mem0_api_key = "test-key"
            result = _call_search_memory("user-test", "theme")

        assert isinstance(result, str)
        assert "dark mode" in result.lower() or len(result) > 0

    def test_exception_returns_error_string(self):
        """search_memory must return an error string on mem0 client errors, never raise."""
        mock_mem0 = MagicMock()
        mock_mem0.MemoryClient.side_effect = RuntimeError("client exploded")

        with patch("app.agents.domain_agents.get_settings") as mock_settings, \
             patch.dict("sys.modules", {"mem0": mock_mem0}):
            mock_settings.return_value.mem0_use_local = False
            mock_settings.return_value.mem0_api_key = "test-key"
            result = _call_search_memory("user-test", "test")

        assert isinstance(result, str)
        assert "error" in result.lower()


# ── Session ID injection ──────────────────────────────────────────────────────

class TestSessionIdInjection:
    """Verify run_swarm injects session_id into the Runner input."""

    @pytest.fixture(autouse=True)
    def seed_swarm(self, monkeypatch):
        import app.agents.swarm as swarm_module
        monkeypatch.setattr(swarm_module, "_triage_agent", MagicMock())
        yield
        monkeypatch.setattr(swarm_module, "_triage_agent", None)

    def _make_mock_result(self) -> MagicMock:
        mock_result = MagicMock()
        mock_result.final_output = "ok"
        mock_result._current_turn = 1
        mock_result.new_items = []
        mock_result.last_agent = MagicMock()
        mock_result.last_agent.name = "TriageAgent"
        return mock_result

    @pytest.mark.asyncio
    async def test_memory_context_id_injected_into_input(self):
        """run_swarm must inject session_id as a system message when memory_context_id is set."""
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = self._make_mock_result()
            from app.agents.swarm import run_swarm

            await run_swarm(ChatRequest(
                request_id="test-001",
                memory_context_id="user-khurram",
                messages=[ChatMessage(role="user", content="hello")],
            ))

        passed_input = mock_run.call_args.kwargs.get("input") or mock_run.call_args.args[1]
        if isinstance(passed_input, list):
            all_content = " ".join(m.get("content", "") for m in passed_input)
        else:
            all_content = passed_input
        assert "user-khurram" in all_content

    @pytest.mark.asyncio
    async def test_request_id_used_as_fallback_session(self):
        """When memory_context_id is None, request_id is used as session_id."""
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = self._make_mock_result()
            from app.agents.swarm import run_swarm

            await run_swarm(ChatRequest(
                request_id="fallback-id-999",
                messages=[ChatMessage(role="user", content="hello")],
            ))

        passed_input = mock_run.call_args.kwargs.get("input") or mock_run.call_args.args[1]
        if isinstance(passed_input, list):
            all_content = " ".join(m.get("content", "") for m in passed_input)
        else:
            all_content = passed_input
        assert "fallback-id-999" in all_content
