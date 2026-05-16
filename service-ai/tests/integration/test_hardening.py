"""
tests/integration/test_hardening.py
─────────────────────────────────────
Tests for production hardening features:
  - Auth: 401 rejection without API key
  - Auth: pass-through when API_KEY is empty (dev mode)
  - SSE endpoint: correct event-stream format and token events
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient


# ── Auth unit tests ───────────────────────────────────────────────────────────

class TestVerifyApiKey:

    @pytest.mark.asyncio
    async def test_rejects_missing_key_when_configured(self):
        """verify_api_key must raise 401 when key is set but header is missing."""
        from app.api.deps import verify_api_key

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        with patch("app.api.deps.get_settings") as mock_settings:
            mock_settings.return_value.api_key = "secret"
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_wrong_key(self):
        """verify_api_key must raise 401 for wrong key."""
        from app.api.deps import verify_api_key

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"x-api-key": "wrong"}

        with patch("app.api.deps.get_settings") as mock_settings:
            mock_settings.return_value.api_key = "correct"
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_passes_correct_key(self):
        """verify_api_key must not raise for the correct key."""
        from app.api.deps import verify_api_key

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"x-api-key": "correct"}

        with patch("app.api.deps.get_settings") as mock_settings:
            mock_settings.return_value.api_key = "correct"
            await verify_api_key(mock_request)  # should not raise

    @pytest.mark.asyncio
    async def test_skips_auth_when_key_empty(self):
        """When API_KEY is empty, auth is disabled — no exception raised."""
        from app.api.deps import verify_api_key

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        with patch("app.api.deps.get_settings") as mock_settings:
            mock_settings.return_value.api_key = ""
            await verify_api_key(mock_request)  # should not raise


# ── SSE endpoint tests ────────────────────────────────────────────────────────

async def _mock_stream(*args, **kwargs):
    yield "Hello"
    yield " world"


class TestSSEEndpoint:

    @pytest.fixture(autouse=True)
    def seed_swarm(self, monkeypatch):
        import app.agents.swarm as swarm_module
        monkeypatch.setattr(swarm_module, "_triage_agent", MagicMock())
        yield
        monkeypatch.setattr(swarm_module, "_triage_agent", None)

    def test_sse_returns_event_stream_content_type(self):
        """SSE endpoint must return text/event-stream."""
        from app.main import app
        with patch("app.api.routes.sse.stream_swarm", side_effect=_mock_stream), \
             patch("app.api.routes.sse.get_history", new_callable=AsyncMock, return_value=[]), \
             patch("app.api.routes.sse.append_to_history", new_callable=AsyncMock), \
             patch("app.api.deps.get_settings") as mock_settings:
            mock_settings.return_value.api_key = ""
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/chat/stream",
                    json={
                        "request_id": "sse-test",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_sse_response_contains_token_events(self):
        """SSE response body must contain data: lines with token type."""
        from app.main import app
        with patch("app.api.routes.sse.stream_swarm", side_effect=_mock_stream), \
             patch("app.api.routes.sse.get_history", new_callable=AsyncMock, return_value=[]), \
             patch("app.api.routes.sse.append_to_history", new_callable=AsyncMock), \
             patch("app.api.deps.get_settings") as mock_settings:
            mock_settings.return_value.api_key = ""
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/chat/stream",
                    json={
                        "request_id": "sse-test",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
        body = resp.text
        assert "data:" in body
        assert "token" in body

    def test_sse_response_ends_with_complete_event(self):
        """SSE stream must terminate with a complete event."""
        from app.main import app
        with patch("app.api.routes.sse.stream_swarm", side_effect=_mock_stream), \
             patch("app.api.routes.sse.get_history", new_callable=AsyncMock, return_value=[]), \
             patch("app.api.routes.sse.append_to_history", new_callable=AsyncMock), \
             patch("app.api.deps.get_settings") as mock_settings:
            mock_settings.return_value.api_key = ""
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/chat/stream",
                    json={
                        "request_id": "sse-test",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
        assert "complete" in resp.text
