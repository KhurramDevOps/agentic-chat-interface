"""
tests/unit/test_logging.py
───────────────────────────
Unit tests for the emoji logging formatter.
"""

from __future__ import annotations

import logging

import pytest

from app.core.logging import EmojiFormatter, JsonFormatter, RequestIdFilter, _module_emoji


class TestModuleEmoji:

    def test_swarm_gets_brain_emoji(self):
        assert _module_emoji("app.agents.swarm") == "🧠"

    def test_chat_route_gets_speech_emoji(self):
        assert _module_emoji("app.api.routes.chat") == "💬"

    def test_audio_route_gets_mic_emoji(self):
        assert _module_emoji("app.api.routes.audio") == "🎤"

    def test_vision_route_gets_art_emoji(self):
        assert _module_emoji("app.api.routes.vision") == "🎨"

    def test_history_service_gets_db_emoji(self):
        assert _module_emoji("app.services.history") == "💾"

    def test_main_gets_rocket_emoji(self):
        assert _module_emoji("app.main") == "🚀"

    def test_unknown_module_gets_clipboard(self):
        assert _module_emoji("some.unknown.module") == "📋"


class TestEmojiFormatter:

    def _make_record(self, name: str, level: int, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name=name, level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        return record

    def test_info_contains_green_circle(self):
        fmt = EmojiFormatter()
        record = self._make_record("app.main", logging.INFO, "startup")
        output = fmt.format(record)
        assert "🟢" in output

    def test_error_contains_red_circle(self):
        fmt = EmojiFormatter()
        record = self._make_record("app.main", logging.ERROR, "crash")
        output = fmt.format(record)
        assert "🔴" in output

    def test_warning_contains_yellow_circle(self):
        fmt = EmojiFormatter()
        record = self._make_record("app.main", logging.WARNING, "watch out")
        output = fmt.format(record)
        assert "🟡" in output

    def test_message_present_in_output(self):
        fmt = EmojiFormatter()
        record = self._make_record("app.agents.swarm", logging.INFO, "swarm ready")
        output = fmt.format(record)
        assert "swarm ready" in output

    def test_module_emoji_injected(self):
        fmt = EmojiFormatter()
        record = self._make_record("app.agents.swarm", logging.INFO, "test")
        output = fmt.format(record)
        assert "🧠" in output

    def test_timestamp_present(self):
        fmt = EmojiFormatter()
        record = self._make_record("app.main", logging.INFO, "test")
        output = fmt.format(record)
        # Timestamp format: 2026-05-16T10:23:01
        assert "T" in output and "-" in output


class TestRequestIdFilter:

    def test_injects_default_request_id(self):
        f = RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.request_id == "-"  # type: ignore[attr-defined]

    def test_injects_custom_request_id(self):
        f = RequestIdFilter(request_id="abc-123")
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.request_id == "abc-123"  # type: ignore[attr-defined]

    def test_filter_returns_true(self):
        f = RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is True


class TestJsonFormatter:

    def test_output_is_valid_json(self):
        import json
        fmt = JsonFormatter()
        record = logging.LogRecord("app.main", logging.INFO, "", 0, "hello", (), None)
        record.request_id = "req-1"  # type: ignore[attr-defined]
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
        assert parsed["request_id"] == "req-1"
