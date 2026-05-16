"""
tests/integration/test_phase3_features.py
──────────────────────────────────────────
Integration tests for Phase 3 features:
  - GET  /api/v1/users/{user_id}/usage
  - DELETE /api/v1/chat/history/{session_id}
  - GET  /api/v1/health/detailed
  - calculate tool
  - fetch_url tool
  - run_python tool
  - DocumentStore (MongoDB-backed)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client():
    from app.main import app
    return TestClient(app)


API_KEY_HEADERS = {"X-API-Key": "super-secret-key"}


# ── Group 1: Users endpoint ───────────────────────────────────────────────────

class TestUsersEndpoint:

    def test_get_usage_returns_200(self):
        mock_doc = {
            "user_id": "anon_test-user",
            "session_id": "test-user",
            "is_anonymous": True,
            "total_tokens_used": 500,
            "prompt_tokens": 300,
            "completion_tokens": 200,
        }
        with patch(
            "app.api.routes.users.get_or_create_user",
            new=AsyncMock(return_value=mock_doc),
        ):
            resp = _client().get(
                "/api/v1/users/anon_test-user/usage",
                headers=API_KEY_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens_used"] == 500
        assert data["prompt_tokens"] == 300
        assert data["completion_tokens"] == 200

    def test_get_usage_requires_api_key(self):
        resp = _client().get("/api/v1/users/some-user/usage")
        assert resp.status_code == 401


# ── Group 2: History delete endpoint ─────────────────────────────────────────

class TestHistoryDelete:

    def test_delete_history_returns_204(self):
        with patch(
            "app.api.routes.users.clear_history",
            new=AsyncMock(),
        ) as mock_clear:
            resp = _client().delete(
                "/api/v1/chat/history/my-session",
                headers=API_KEY_HEADERS,
            )
        assert resp.status_code == 204
        mock_clear.assert_called_once_with("my-session")

    def test_delete_history_requires_api_key(self):
        resp = _client().delete("/api/v1/chat/history/my-session")
        assert resp.status_code == 401


# ── Group 3: Detailed health ──────────────────────────────────────────────────

class TestDetailedHealth:

    def test_detailed_health_returns_200(self):
        with patch("app.api.routes.health._check_mongodb", new=AsyncMock(return_value="ok")):
            with patch("app.api.routes.health._check_llm", new=AsyncMock(return_value="ok")):
                resp = _client().get("/api/v1/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        assert data["checks"]["mongodb"] == "ok"
        assert data["checks"]["llm_provider"] == "ok"

    def test_detailed_health_degraded_on_mongo_error(self):
        with patch(
            "app.api.routes.health._check_mongodb",
            new=AsyncMock(return_value="error:connection refused"),
        ):
            with patch("app.api.routes.health._check_llm", new=AsyncMock(return_value="ok")):
                resp = _client().get("/api/v1/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["mongodb"].startswith("error:")


# ── Group 4: calculate tool ───────────────────────────────────────────────────

class TestCalculateTool:

    def _calc(self, expr: str) -> str:
        from app.agents.domain_agents import calculate
        # function_tool wraps the function; call the underlying fn directly
        return calculate.on_invoke_tool(MagicMock(), expr)  # type: ignore

    def test_basic_addition(self):
        from app.agents.domain_agents import calculate
        # Access the raw function via the tool's fn attribute
        result = calculate.fn(expression="2 + 3")  # type: ignore
        assert result == "5"

    def test_float_division(self):
        from app.agents.domain_agents import calculate
        result = calculate.fn(expression="10 / 4")  # type: ignore
        assert "2.5" in result

    def test_power(self):
        from app.agents.domain_agents import calculate
        result = calculate.fn(expression="2 ** 10")  # type: ignore
        assert result == "1024"

    def test_division_by_zero(self):
        from app.agents.domain_agents import calculate
        result = calculate.fn(expression="1 / 0")  # type: ignore
        assert "zero" in result.lower()

    def test_rejects_function_calls(self):
        from app.agents.domain_agents import calculate
        result = calculate.fn(expression="__import__('os').system('ls')")  # type: ignore
        assert "Error" in result


# ── Group 5: run_python tool ──────────────────────────────────────────────────

class TestRunPythonTool:

    def test_simple_print(self):
        from app.agents.domain_agents import run_python
        result = run_python.fn(code="print('hello world')")  # type: ignore
        assert "hello world" in result

    def test_math_output(self):
        from app.agents.domain_agents import run_python
        result = run_python.fn(code="print(sum(range(1, 11)))")  # type: ignore
        assert "55" in result

    def test_blocks_os_import(self):
        from app.agents.domain_agents import run_python
        result = run_python.fn(code="import os\nprint(os.getcwd())")  # type: ignore
        assert "Error" in result or "not allowed" in result

    def test_timeout_enforcement(self):
        from app.agents.domain_agents import run_python
        result = run_python.fn(code="while True: pass")  # type: ignore
        assert "timeout" in result.lower()


# ── Group 6: fetch_url tool ───────────────────────────────────────────────────

class TestFetchUrlTool:

    def test_rejects_non_http_url(self):
        from app.agents.domain_agents import fetch_url
        result = fetch_url.fn(url="ftp://example.com")  # type: ignore
        assert "Error" in result

    def test_fetches_and_strips_html(self):
        import httpx
        from app.agents.domain_agents import fetch_url

        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Hello</h1><p>World</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)

        with patch("app.agents.domain_agents.httpx.Client", return_value=mock_client):
            result = fetch_url.fn(url="https://example.com")  # type: ignore

        assert "<html>" not in result
        assert "Hello" in result
        assert "World" in result


# ── Group 7: DocumentStore (MongoDB-backed) ───────────────────────────────────

class TestDocumentStore:

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self):
        from app.services.file_service import DocumentStore

        store = DocumentStore()

        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock()
        mock_col.find_one = AsyncMock(return_value={"text": "hello document"})

        with patch("app.services.file_service._get_collection", return_value=mock_col):
            doc_id = await store.store_document("hello document", filename="test.pdf")
            text = await store.get_document(doc_id)

        assert isinstance(doc_id, str)
        assert len(doc_id) > 0
        assert text == "hello document"

    @pytest.mark.asyncio
    async def test_fallback_on_mongo_error(self):
        from app.services.file_service import DocumentStore, _fallback

        store = DocumentStore()

        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock(side_effect=Exception("mongo down"))

        with patch("app.services.file_service._get_collection", return_value=mock_col):
            doc_id = await store.store_document("fallback text")

        # Should be in the in-memory fallback
        assert doc_id in _fallback
        assert _fallback[doc_id] == "fallback text"

    @pytest.mark.asyncio
    async def test_delete_document(self):
        from app.services.file_service import DocumentStore

        store = DocumentStore()

        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_col = MagicMock()
        mock_col.delete_one = AsyncMock(return_value=mock_result)

        with patch("app.services.file_service._get_collection", return_value=mock_col):
            deleted = await store.delete_document("some-doc-id")

        assert deleted is True
