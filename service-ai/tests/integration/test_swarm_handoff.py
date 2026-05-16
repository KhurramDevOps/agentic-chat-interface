"""
tests/integration/test_swarm_handoff.py  (T017 / T018 / T019)
───────────────────────────────────────────────────────────────
Integration tests for the multi-agent swarm.

Test 1 — TriageAgent routes research intent to ResearchAgent.
Test 2 — MemoryAgent tools (add_memory / search_memory) execute without crashing.
Test 3 — Conversation context (messages) is preserved across a handoff.

Strategy:
  - We do NOT call the live Gemini API in these tests.
  - We patch Runner.run to return a controlled RunResult so tests are
    deterministic, fast, and free of external dependencies.
  - Tool-level tests (Test 2) call the @function_tool functions directly
    to validate they are type-safe and return expected shapes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import AgentMetadata, AgentResponse, ChatMessage, ChatRequest


# ── Module-level fixture: seed the swarm singleton so tests don't need lifespan ──

@pytest.fixture(autouse=True)
def seed_swarm(monkeypatch):
    """Pre-seed _triage_agent so run_swarm() doesn't raise RuntimeError."""
    import app.agents.swarm as swarm_module
    monkeypatch.setattr(swarm_module, "_triage_agent", MagicMock())
    yield
    monkeypatch.setattr(swarm_module, "_triage_agent", None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_request(content: str, memory_context_id: str | None = None) -> ChatRequest:
    return ChatRequest(
        request_id="test-req-001",
        messages=[ChatMessage(role="user", content=content)],
        memory_context_id=memory_context_id,
    )


def _make_mock_result(
    final_output: str,
    last_agent_name: str,
    new_items: list | None = None,
    turns: int = 1,
) -> MagicMock:
    """Build a MagicMock that quacks like a RunResult."""
    mock_result = MagicMock()
    mock_result.final_output = final_output
    mock_result._current_turn = turns
    mock_result.new_items = new_items or []

    mock_agent = MagicMock()
    mock_agent.name = last_agent_name
    mock_result.last_agent = mock_agent

    return mock_result


# ── Test 1: Triage → ResearchAgent handoff ────────────────────────────────────

class TestTriageHandoffToResearch:
    """Verify TriageAgent routes research/current-events intent to ResearchAgent."""

    @pytest.mark.asyncio
    async def test_research_intent_routes_to_research_agent(self):
        """
        When the user asks about current events, the swarm should
        complete with ResearchAgent as the last_agent.
        """
        from agents import HandoffOutputItem

        # Simulate a handoff item in new_items
        handoff_item = MagicMock(spec=HandoffOutputItem)
        handoff_item.agent = MagicMock()
        handoff_item.agent.name = "ResearchAgent"

        mock_result = _make_mock_result(
            final_output="Here are the latest news results for your query.",
            last_agent_name="ResearchAgent",
            new_items=[handoff_item],
            turns=2,
        )

        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            response = await run_swarm(_make_request("What's the weather like today?"))

        assert isinstance(response, AgentResponse)
        assert response.agent.agent_name == "ResearchAgent"
        assert response.agent.handoff_occurred is True
        assert "ResearchAgent" in response.agent.handoff_chain

    @pytest.mark.asyncio
    async def test_research_handoff_preserves_request_id(self):
        mock_result = _make_mock_result(
            final_output="Research complete.",
            last_agent_name="ResearchAgent",
        )
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            req = _make_request("Search for recent AI news")
            response = await run_swarm(req)

        assert response.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_casual_chat_stays_with_triage(self):
        """Casual greetings should be handled by TriageAgent without handoff."""
        mock_result = _make_mock_result(
            final_output="Hello! How can I help you today?",
            last_agent_name="TriageAgent",
            new_items=[],
            turns=1,
        )
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            response = await run_swarm(_make_request("Hello!"))

        assert response.agent.agent_name == "TriageAgent"
        assert response.agent.handoff_occurred is False

    @pytest.mark.asyncio
    async def test_runner_receives_correct_input(self):
        """Runner.run must be called with the last user message as input."""
        mock_result = _make_mock_result("ok", "TriageAgent")
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            await run_swarm(_make_request("Tell me about black holes"))

        call_kwargs = mock_run.call_args
        assert call_kwargs is not None
        passed_input = call_kwargs.kwargs.get("input") or call_kwargs.args[1]
        # input is now a list of message dicts
        if isinstance(passed_input, list):
            all_content = " ".join(m.get("content", "") for m in passed_input)
        else:
            all_content = passed_input
        assert "black holes" in all_content


# ── Test 2: MemoryAgent tool safety ───────────────────────────────────────────

class TestMemoryAgentTools:
    """Verify mem0 tools execute without crashing and return expected shapes."""

    def test_add_memory_returns_string(self):
        from app.agents.domain_agents import add_memory
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            add_memory.on_invoke_tool(None, '{"context_id": "ctx-1", "content": "User prefers dark mode"}')  # type: ignore[attr-defined]
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_search_memory_returns_string(self):
        from app.agents.domain_agents import search_memory
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            search_memory.on_invoke_tool(None, '{"context_id": "ctx-1", "query": "dark mode preference"}')  # type: ignore[attr-defined]
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_memory_rejects_empty_content(self):
        from app.agents.domain_agents import add_memory
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            add_memory.on_invoke_tool(None, '{"context_id": "ctx-1", "content": "   "}')  # type: ignore[attr-defined]
        )
        assert "empty" in result.lower() or "error" in result.lower()

    def test_web_search_returns_string(self):
        from app.agents.domain_agents import tavily_search
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            tavily_search.on_invoke_tool(None, '{"query": "latest AI news"}')  # type: ignore[attr-defined]
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_memory_agent_swarm_call_does_not_crash(self):
        """MemoryAgent path through the swarm must not raise."""
        from agents import HandoffOutputItem

        handoff_item = MagicMock(spec=HandoffOutputItem)
        handoff_item.agent = MagicMock()
        handoff_item.agent.name = "MemoryAgent"

        mock_result = _make_mock_result(
            final_output="I've stored that preference for you.",
            last_agent_name="MemoryAgent",
            new_items=[handoff_item],
            turns=2,
        )
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            response = await run_swarm(
                _make_request("Remember that I prefer dark mode", memory_context_id="user-42")
            )

        assert response.agent.agent_name == "MemoryAgent"
        assert isinstance(response.content, str)


# ── Test 3: Context preservation across handoff ───────────────────────────────

class TestContextPreservation:
    """Verify conversation history is preserved during a handoff."""

    @pytest.mark.asyncio
    async def test_multi_turn_messages_passed_to_runner(self):
        """Runner.run must receive the last user message from a multi-turn conversation."""
        mock_result = _make_mock_result("Research complete.", "ResearchAgent")
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            request = ChatRequest(
                request_id="ctx-test-001",
                messages=[
                    ChatMessage(role="user", content="Hello"),
                    ChatMessage(role="assistant", content="Hi there!"),
                    ChatMessage(role="user", content="Now search for quantum computing news"),
                ],
            )
            await run_swarm(request)

        call_kwargs = mock_run.call_args
        passed_input = call_kwargs.kwargs.get("input") or call_kwargs.args[1]
        if isinstance(passed_input, list):
            all_content = " ".join(m.get("content", "") for m in passed_input)
        else:
            all_content = passed_input
        assert "quantum computing" in all_content

    @pytest.mark.asyncio
    async def test_response_contains_model_field(self):
        """AgentResponse must echo back the model from the request."""
        mock_result = _make_mock_result("Done.", "TriageAgent")
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            req = ChatRequest(
                request_id="model-test",
                messages=[ChatMessage(role="user", content="hi")],
                model="gemini/gemini-1.5-pro",
            )
            response = await run_swarm(req)

        assert response.model == "gemini/gemini-1.5-pro"

    @pytest.mark.asyncio
    async def test_handoff_chain_includes_triage_as_origin(self):
        """Handoff chain must always start with TriageAgent."""
        mock_result = _make_mock_result("Result.", "ResearchAgent")
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            response = await run_swarm(_make_request("search for something"))

        assert response.agent.handoff_chain[0] == "TriageAgent"

    @pytest.mark.asyncio
    async def test_turns_used_reflected_in_metadata(self):
        """AgentMetadata.turns_used must match the RunResult._current_turn."""
        mock_result = _make_mock_result("Done.", "ResearchAgent", turns=3)
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            from app.agents.swarm import run_swarm

            response = await run_swarm(_make_request("deep research on fusion energy"))

        assert response.agent.turns_used == 3
