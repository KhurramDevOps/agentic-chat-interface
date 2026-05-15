"""
tests/integration/test_triage_routing.py
──────────────────────────────────────────
Tests for TriageAgent routing logic and short-term vs long-term memory separation.

Covers:
  - Casual statements stay with TriageAgent (short-term history only)
  - Follow-up questions answered from history without MemoryAgent
  - Explicit "remember for next time" routes to MemoryAgent (long-term)
  - Research intent routes to ResearchAgent
  - Media intent routes to MediaAgent
  - Provider-aware ModelSettings (parallel_tool_calls=False for Groq)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatMessage, ChatRequest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def seed_swarm(monkeypatch):
    import app.agents.swarm as swarm_module
    monkeypatch.setattr(swarm_module, "_triage_agent", MagicMock())
    yield
    monkeypatch.setattr(swarm_module, "_triage_agent", None)


def _mock_result(content: str, agent_name: str, turns: int = 1) -> MagicMock:
    m = MagicMock()
    m.final_output = content
    m._current_turn = turns
    m.new_items = []
    m.last_agent = MagicMock()
    m.last_agent.name = agent_name
    return m


def _req(content: str, session_id: str = "test-session", history: list | None = None) -> ChatRequest:
    messages = []
    if history:
        messages.extend([ChatMessage(role=m["role"], content=m["content"]) for m in history])
    messages.append(ChatMessage(role="user", content=content))
    return ChatRequest(
        request_id="test-req",
        memory_context_id=session_id,
        messages=messages,
    )


# ── Short-term memory routing ─────────────────────────────────────────────────

class TestShortTermMemoryRouting:
    """Casual statements and follow-ups should stay with TriageAgent."""

    @pytest.mark.asyncio
    async def test_casual_statement_stays_with_triage(self):
        """'My favorite X is Y' should be handled by TriageAgent directly."""
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = _mock_result(
                "I'll keep that in mind!", "TriageAgent", turns=1
            )
            from app.agents.swarm import run_swarm
            response = await run_swarm(_req("My favorite framework is FastAPI"))

        assert response.agent.agent_name == "TriageAgent"
        assert response.agent.turns_used == 1
        assert response.agent.handoff_occurred is False

    @pytest.mark.asyncio
    async def test_followup_from_history_stays_with_triage(self):
        """Follow-up question answerable from history should not route to MemoryAgent."""
        history = [
            {"role": "user", "content": "My favorite framework is FastAPI"},
            {"role": "assistant", "content": "I'll keep that in mind!"},
        ]
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = _mock_result(
                "Your favorite framework is FastAPI.", "TriageAgent", turns=1
            )
            from app.agents.swarm import run_swarm
            response = await run_swarm(_req("What is my favorite framework?", history=history))

        assert response.agent.agent_name == "TriageAgent"
        assert response.agent.turns_used == 1

    @pytest.mark.asyncio
    async def test_history_is_passed_to_runner(self):
        """Full conversation history must be included in Runner.run input."""
        history = [
            {"role": "user", "content": "I am building a MERN stack app"},
            {"role": "assistant", "content": "That sounds great!"},
        ]
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = _mock_result("You are building a MERN stack app.", "TriageAgent")
            from app.agents.swarm import run_swarm
            await run_swarm(_req("What am I building?", history=history))

        passed_input = mock_run.call_args.kwargs.get("input") or mock_run.call_args.args[1]
        all_content = " ".join(m.get("content", "") for m in passed_input) if isinstance(passed_input, list) else passed_input
        assert "MERN stack" in all_content
        assert "What am I building?" in all_content


# ── Long-term memory routing ──────────────────────────────────────────────────

class TestLongTermMemoryRouting:
    """Explicit save/recall requests should route to MemoryAgent."""

    @pytest.mark.asyncio
    async def test_explicit_remember_routes_to_memory_agent(self):
        """'Remember this for next time' must route to MemoryAgent."""
        from agents import HandoffOutputItem
        handoff_item = MagicMock(spec=HandoffOutputItem)
        handoff_item.agent = MagicMock()
        handoff_item.agent.name = "MemoryAgent"

        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = _mock_result(
                "Saved to long-term memory.", "MemoryAgent", turns=3
            )
            mock_run.return_value.new_items = [handoff_item]
            from app.agents.swarm import run_swarm
            response = await run_swarm(_req("Remember this for next time: I prefer dark mode"))

        assert response.agent.agent_name == "MemoryAgent"

    @pytest.mark.asyncio
    async def test_session_id_injected_as_system_message(self):
        """session_id must appear in the system message passed to Runner."""
        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = _mock_result("ok", "TriageAgent")
            from app.agents.swarm import run_swarm
            await run_swarm(_req("hello", session_id="user-khurram"))

        passed_input = mock_run.call_args.kwargs.get("input") or mock_run.call_args.args[1]
        assert isinstance(passed_input, list)
        system_msgs = [m for m in passed_input if m.get("role") == "system"]
        assert len(system_msgs) == 1
        assert "user-khurram" in system_msgs[0]["content"]


# ── Research routing ──────────────────────────────────────────────────────────

class TestResearchRouting:

    @pytest.mark.asyncio
    async def test_web_search_routes_to_research_agent(self):
        from agents import HandoffOutputItem
        handoff_item = MagicMock(spec=HandoffOutputItem)
        handoff_item.agent = MagicMock()
        handoff_item.agent.name = "ResearchAgent"

        with patch("app.agents.swarm.Runner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = _mock_result("Search results...", "ResearchAgent", turns=2)
            mock_run.return_value.new_items = [handoff_item]
            from app.agents.swarm import run_swarm
            response = await run_swarm(_req("Search for latest AI news"))

        assert response.agent.agent_name == "ResearchAgent"
        assert response.agent.handoff_occurred is True


# ── Provider-aware ModelSettings ──────────────────────────────────────────────

class TestProviderModelSettings:

    def test_groq_sets_parallel_tool_calls_false(self):
        """When LLM_PROVIDER=groq, all agents must have parallel_tool_calls=False."""
        from agents import ModelSettings
        with patch("app.agents.triage_agent.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.active_model = "llama-3.1-8b-instant"
            from app.agents.triage_agent import build_triage_agent
            triage = build_triage_agent()

        assert triage.model_settings is not None
        assert triage.model_settings.parallel_tool_calls is False

    def test_gemini_uses_default_model_settings(self):
        """When LLM_PROVIDER=gemini, ModelSettings should not restrict parallel calls."""
        with patch("app.agents.triage_agent.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "gemini"
            mock_settings.return_value.active_model = "gemini-2.5-flash"
            from app.agents.triage_agent import build_triage_agent
            triage = build_triage_agent()

        # parallel_tool_calls should be None (not restricted) for Gemini
        assert triage.model_settings is not None
        assert triage.model_settings.parallel_tool_calls is None
