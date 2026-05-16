"""
tests/integration/test_api_endpoints.py
─────────────────────────────────────────
Comprehensive endpoint tests covering:
  - Health (basic + detailed)
  - Users / token usage
  - Chat history delete
  - Vision endpoint
  - Audio transcription + TTS
  - File upload
  - Auth enforcement
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

API_HEADERS = {"X-API-Key": "super-secret-key"}


def _client():
    from app.main import app
    return TestClient(app)


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealthEndpoints:

    def test_liveness_returns_ok(self):
        resp = _client().get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_readiness_returns_200(self):
        resp = _client().get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert "status" in resp.json()

    def test_health_summary_returns_200(self):
        resp = _client().get("/api/v1/health")
        assert resp.status_code == 200

    def test_detailed_health_all_ok(self):
        with patch("app.api.routes.health._check_mongodb", new=AsyncMock(return_value="ok")):
            with patch("app.api.routes.health._check_llm", new=AsyncMock(return_value="ok")):
                resp = _client().get("/api/v1/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["checks"]["mongodb"] == "ok"
        assert data["checks"]["llm_provider"] == "ok"

    def test_detailed_health_degraded_on_mongo_failure(self):
        with patch("app.api.routes.health._check_mongodb",
                   new=AsyncMock(return_value="error:timeout")):
            with patch("app.api.routes.health._check_llm", new=AsyncMock(return_value="ok")):
                resp = _client().get("/api/v1/health/detailed")
        assert resp.json()["status"] == "degraded"

    def test_detailed_health_degraded_on_llm_failure(self):
        with patch("app.api.routes.health._check_mongodb", new=AsyncMock(return_value="ok")):
            with patch("app.api.routes.health._check_llm",
                       new=AsyncMock(return_value="error:HTTP 503")):
                resp = _client().get("/api/v1/health/detailed")
        assert resp.json()["status"] == "degraded"

    def test_detailed_health_has_mem0_field(self):
        with patch("app.api.routes.health._check_mongodb", new=AsyncMock(return_value="ok")):
            with patch("app.api.routes.health._check_llm", new=AsyncMock(return_value="ok")):
                resp = _client().get("/api/v1/health/detailed")
        assert "mem0" in resp.json()["checks"]


# ── Auth enforcement ──────────────────────────────────────────────────────────

class TestAuthEnforcement:

    def test_chat_completions_requires_key(self):
        resp = _client().post("/api/v1/chat/completions", json={
            "request_id": "r1",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert resp.status_code == 401

    def test_sse_stream_requires_key(self):
        resp = _client().post("/api/v1/chat/stream", json={
            "request_id": "r1",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert resp.status_code == 401

    def test_users_usage_requires_key(self):
        resp = _client().get("/api/v1/users/some-user/usage")
        assert resp.status_code == 401

    def test_history_delete_requires_key(self):
        resp = _client().delete("/api/v1/chat/history/session-1")
        assert resp.status_code == 401

    def test_audio_transcription_requires_key(self):
        resp = _client().post("/api/v1/audio/transcriptions",
                              files={"file": ("a.mp3", b"data", "audio/mpeg")})
        assert resp.status_code == 401

    def test_vision_requires_key(self):
        resp = _client().post("/api/v1/chat/vision",
                              files={"file": ("img.jpg", b"data", "image/jpeg")})
        assert resp.status_code == 401


# ── Users / token usage ───────────────────────────────────────────────────────

class TestUsersEndpoints:

    def test_get_usage_returns_correct_fields(self):
        mock_doc = {
            "user_id": "anon_u1", "session_id": "u1",
            "is_anonymous": True, "total_tokens_used": 100,
            "prompt_tokens": 60, "completion_tokens": 40,
        }
        with patch("app.api.routes.users.get_or_create_user",
                   new=AsyncMock(return_value=mock_doc)):
            resp = _client().get("/api/v1/users/anon_u1/usage", headers=API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens_used"] == 100
        assert data["prompt_tokens"] == 60
        assert data["completion_tokens"] == 40
        assert data["is_anonymous"] is True

    def test_get_usage_zero_for_new_user(self):
        mock_doc = {
            "user_id": "anon_new", "session_id": "new",
            "is_anonymous": True, "total_tokens_used": 0,
            "prompt_tokens": 0, "completion_tokens": 0,
        }
        with patch("app.api.routes.users.get_or_create_user",
                   new=AsyncMock(return_value=mock_doc)):
            resp = _client().get("/api/v1/users/anon_new/usage", headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["total_tokens_used"] == 0


# ── Chat history delete ───────────────────────────────────────────────────────

class TestHistoryDelete:

    def test_delete_returns_204(self):
        with patch("app.api.routes.users.clear_history", new=AsyncMock()) as m:
            resp = _client().delete("/api/v1/chat/history/sess-1", headers=API_HEADERS)
        assert resp.status_code == 204
        m.assert_called_once_with("sess-1")

    def test_delete_different_sessions_isolated(self):
        calls = []
        async def _clear(sid):
            calls.append(sid)

        with patch("app.api.routes.users.clear_history", side_effect=_clear):
            _client().delete("/api/v1/chat/history/sess-a", headers=API_HEADERS)
            _client().delete("/api/v1/chat/history/sess-b", headers=API_HEADERS)

        assert "sess-a" in calls
        assert "sess-b" in calls


# ── Vision endpoint ───────────────────────────────────────────────────────────

class TestVisionEndpoint:

    def _mock_groq_vision(self, analysis: str = "A beautiful landscape."):
        mock_choice = MagicMock()
        mock_choice.message.content = analysis
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        return patch("app.api.routes.vision.AsyncGroq", return_value=mock_client)

    def test_vision_returns_analysis(self):
        from app.api.routes import vision  # ensure import path
        with self._mock_groq_vision("A cat sitting on a mat."):
            resp = _client().post(
                "/api/v1/chat/vision",
                headers=API_HEADERS,
                files={"file": ("test.jpg", b"\xff\xd8\xff" + b"\x00" * 100, "image/jpeg")},
                data={"prompt": "What is in this image?"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis" in data
        assert "cat" in data["analysis"].lower()

    def test_vision_rejects_empty_file(self):
        with patch("app.api.routes.vision.AsyncGroq"):
            resp = _client().post(
                "/api/v1/chat/vision",
                headers=API_HEADERS,
                files={"file": ("empty.jpg", b"", "image/jpeg")},
                data={"prompt": "describe"},
            )
        assert resp.status_code == 400

    def test_vision_returns_model_name(self):
        with self._mock_groq_vision("Some analysis."):
            resp = _client().post(
                "/api/v1/chat/vision",
                headers=API_HEADERS,
                files={"file": ("img.png", b"\x89PNG" + b"\x00" * 50, "image/png")},
                data={"prompt": "describe"},
            )
        assert resp.status_code == 200
        assert "model" in resp.json()


# ── Audio transcription ───────────────────────────────────────────────────────

class TestAudioTranscription:

    def _mock_groq_transcription(self, text: str = "Hello world"):
        mock_result = MagicMock()
        mock_result.text = text
        mock_result.language = "en"
        mock_result.duration = 2.5

        mock_transcriptions = MagicMock()
        mock_transcriptions.create = AsyncMock(return_value=mock_result)

        mock_audio = MagicMock()
        mock_audio.transcriptions = mock_transcriptions

        mock_client = MagicMock()
        mock_client.audio = mock_audio

        return patch("app.api.routes.audio.AsyncGroq", return_value=mock_client)

    def test_transcription_returns_text(self):
        with self._mock_groq_transcription("The quick brown fox"):
            resp = _client().post(
                "/api/v1/audio/transcriptions",
                headers=API_HEADERS,
                files={"file": ("audio.mp3", b"\xff\xfb" + b"\x00" * 100, "audio/mpeg")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "The quick brown fox"
        assert data["language"] == "en"

    def test_transcription_rejects_empty_file(self):
        with self._mock_groq_transcription():
            resp = _client().post(
                "/api/v1/audio/transcriptions",
                headers=API_HEADERS,
                files={"file": ("empty.mp3", b"", "audio/mpeg")},
            )
        assert resp.status_code == 400


# ── TTS endpoint ──────────────────────────────────────────────────────────────

class TestTTSEndpoint:

    def test_tts_returns_audio_mpeg(self):
        fake_mp3 = b"\xff\xfb\x90\x00" + b"\x00" * 200  # fake MP3 header

        def _fake_gtts(text, lang, slow):
            m = MagicMock()
            def _write(fp):
                fp.write(fake_mp3)
            m.write_to_fp = _write
            return m

        with patch("app.api.routes.audio.gTTS", side_effect=_fake_gtts):
            resp = _client().post(
                "/api/v1/audio/speech",
                headers=API_HEADERS,
                data={"text": "Hello world", "lang": "en"},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/mpeg")
        assert len(resp.content) > 0

    def test_tts_rejects_empty_text(self):
        resp = _client().post(
            "/api/v1/audio/speech",
            headers=API_HEADERS,
            data={"text": "   "},
        )
        assert resp.status_code == 400

    def test_tts_requires_api_key(self):
        resp = _client().post("/api/v1/audio/speech", data={"text": "hi"})
        assert resp.status_code == 401


# ── File upload ───────────────────────────────────────────────────────────────

class TestFileUpload:

    def test_upload_pdf_returns_doc_id(self):
        fake_pdf = b"%PDF-1.4 fake content"

        with patch("app.api.routes.files.extract_pdf_text",
                   new=AsyncMock(return_value="Extracted text from PDF")):
            with patch("app.services.file_service.DocumentStore.store_document",
                       new=AsyncMock(return_value="test-doc-uuid")):
                resp = _client().post(
                    "/api/v1/files/upload",
                    headers=API_HEADERS,
                    files={"file": ("doc.pdf", fake_pdf, "application/pdf")},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert "doc_id" in data

    def test_upload_rejects_non_pdf(self):
        resp = _client().post(
            "/api/v1/files/upload",
            headers=API_HEADERS,
            files={"file": ("image.png", b"\x89PNG", "image/png")},
        )
        assert resp.status_code == 422

    def test_upload_rejects_empty_file(self):
        resp = _client().post(
            "/api/v1/files/upload",
            headers=API_HEADERS,
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 422
