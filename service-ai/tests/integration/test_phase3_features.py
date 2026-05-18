"""
tests/integration/test_phase3_features.py
──────────────────────────────────────────
Integration tests for Phase 3 features:
  - GET  /api/v1/users/usage
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


API_KEY_HEADERS = {
    "X-API-Key": "super-secret-key",
    "x-user-id": "test-user-123",
    "x-user-email": "test@example.com",
}


# ── Group 1: Users endpoint ───────────────────────────────────────────────────

class TestUsersEndpoint:

    def test_get_usage_returns_200(self):
        mock_doc = {
            "user_id": "test-user-123",
            "session_id": "test-user",
            "is_anonymous": False,
            "total_tokens_used": 500,
            "prompt_tokens": 300,
            "completion_tokens": 200,
        }
        with patch(
            "app.api.routes.users.read_user_usage",
            new=AsyncMock(return_value=mock_doc),
        ):
            resp = _client().get(
                "/api/v1/users/usage",
                headers=API_KEY_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens_used"] == 500
        assert data["prompt_tokens"] == 300
        assert data["completion_tokens"] == 200

    def test_get_usage_requires_api_key(self):
        resp = _client().get("/api/v1/users/usage")
        assert resp.status_code == 401


# ── Group 2: History delete endpoint ─────────────────────────────────────────

class TestHistoryDelete:

    def test_delete_history_returns_204(self):
        with patch(
            "app.api.routes.users.history_service.delete_history",
            new=AsyncMock(),
        ) as mock_clear:
            resp = _client().delete(
                "/api/v1/chat/history/my-session",
                headers=API_KEY_HEADERS,
            )
        assert resp.status_code == 204
        mock_clear.assert_called_once_with(session_id="my-session", user_id="test-user-123")

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

    def test_basic_addition(self):
        from app.agents.domain_agents import _calculate_impl
        assert _calculate_impl("2 + 3") == "5"

    def test_float_division(self):
        from app.agents.domain_agents import _calculate_impl
        assert "2.5" in _calculate_impl("10 / 4")

    def test_power(self):
        from app.agents.domain_agents import _calculate_impl
        assert _calculate_impl("2 ** 10") == "1024"

    def test_division_by_zero(self):
        from app.agents.domain_agents import _calculate_impl
        assert "zero" in _calculate_impl("1 / 0").lower()

    def test_rejects_function_calls(self):
        from app.agents.domain_agents import _calculate_impl
        assert "Error" in _calculate_impl("__import__('os').system('ls')")


# ── Group 5: run_python tool ──────────────────────────────────────────────────

class TestRunPythonTool:

    def test_simple_print(self):
        from app.agents.domain_agents import _run_python_impl
        assert "hello world" in _run_python_impl("print('hello world')")

    def test_math_output(self):
        from app.agents.domain_agents import _run_python_impl
        assert "55" in _run_python_impl("print(sum(range(1, 11)))")

    def test_blocks_os_import(self):
        from app.agents.domain_agents import _run_python_impl
        result = _run_python_impl("import os\nprint(os.getcwd())")
        assert "Error" in result or "not allowed" in result

    def test_timeout_enforcement(self):
        from app.agents.domain_agents import _run_python_impl
        result = _run_python_impl("while True: pass")
        assert "timeout" in result.lower()


# ── Group 6: fetch_url tool ───────────────────────────────────────────────────

class TestFetchUrlTool:

    @pytest.mark.asyncio
    async def test_rejects_non_http_url(self):
        from app.agents.domain_agents import _fetch_url_impl
        assert "Error" in await _fetch_url_impl("ftp://example.com")

    @pytest.mark.asyncio
    async def test_fetches_allowlisted_content(self):
        from app.agents.domain_agents import _fetch_url_impl

        mock_response = MagicMock()
        mock_response.text = "Hello\nWorld"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.agents.domain_agents.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_url_impl("https://api.tavily.com/search")

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
