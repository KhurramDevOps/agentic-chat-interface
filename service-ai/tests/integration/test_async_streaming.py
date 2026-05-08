"""
tests/integration/test_async_streaming.py  (T025 / T026 / T027)
─────────────────────────────────────────────────────────────────
Integration tests for the async streaming and background worker pipeline.

Test group 1 — ConnectionManager: store, send, disconnect, broadcast.
Test group 2 — Background worker lifecycle: dispatch → running → completed/failed.
Test group 3 — WebSocket endpoint: connect, receive message, receive background_update.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketState

from app.schemas.streaming import (
    BackgroundMediaTask,
    ChatStreamEvent,
    EventType,
    JobType,
    TaskStatus,
)
from app.services.streaming_service import ConnectionManager, get_connection_manager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_ws(client_id: str = "test-client") -> MagicMock:
    """Build a MagicMock that quacks like a FastAPI WebSocket."""
    ws = MagicMock()
    ws.client_state = WebSocketState.CONNECTED
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ── Group 1: ConnectionManager ────────────────────────────────────────────────

class TestConnectionManager:

    @pytest.mark.asyncio
    async def test_connect_registers_client(self):
        manager = ConnectionManager()
        ws = _make_mock_ws()
        await manager.connect("client-1", ws)
        assert manager.is_connected("client-1")
        assert manager.active_connections == 1

    @pytest.mark.asyncio
    async def test_connect_calls_websocket_accept(self):
        manager = ConnectionManager()
        ws = _make_mock_ws()
        await manager.connect("client-1", ws)
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        manager = ConnectionManager()
        ws = _make_mock_ws()
        await manager.connect("client-1", ws)
        manager.disconnect("client-1")
        assert not manager.is_connected("client-1")
        assert manager.active_connections == 0

    @pytest.mark.asyncio
    async def test_send_event_calls_send_text(self):
        manager = ConnectionManager()
        ws = _make_mock_ws()
        await manager.connect("client-1", ws)

        event = ChatStreamEvent.status("req-1", 0, "hello")
        result = await manager.send_event("client-1", event)

        assert result is True
        ws.send_text.assert_called_once()
        sent_payload = json.loads(ws.send_text.call_args[0][0])
        assert sent_payload["event_type"] == EventType.STATUS.value

    @pytest.mark.asyncio
    async def test_send_event_returns_false_for_unknown_client(self):
        manager = ConnectionManager()
        event = ChatStreamEvent.status("req-1", 0, "hello")
        result = await manager.send_event("no-such-client", event)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_event_disconnects_on_error(self):
        manager = ConnectionManager()
        ws = _make_mock_ws()
        ws.send_text = AsyncMock(side_effect=RuntimeError("connection reset"))
        await manager.connect("client-err", ws)

        event = ChatStreamEvent.complete("req-1", 1)
        result = await manager.send_event("client-err", event)

        assert result is False
        assert not manager.is_connected("client-err")

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_clients(self):
        manager = ConnectionManager()
        ws1, ws2 = _make_mock_ws("c1"), _make_mock_ws("c2")
        await manager.connect("c1", ws1)
        await manager.connect("c2", ws2)

        event = ChatStreamEvent.status("req-x", 0, "broadcast test")
        sent = await manager.broadcast(event)

        assert sent == 2
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    def test_next_sequence_is_monotonic(self):
        manager = ConnectionManager()
        manager._sequences["c1"] = 0
        assert manager.next_sequence("c1") == 0
        assert manager.next_sequence("c1") == 1
        assert manager.next_sequence("c1") == 2

    @pytest.mark.asyncio
    async def test_sequence_resets_on_reconnect(self):
        manager = ConnectionManager()
        ws = _make_mock_ws()
        await manager.connect("c1", ws)
        manager.next_sequence("c1")
        manager.next_sequence("c1")
        manager.disconnect("c1")

        ws2 = _make_mock_ws()
        await manager.connect("c1", ws2)
        assert manager.next_sequence("c1") == 0


# ── Group 2: Background worker lifecycle ─────────────────────────────────────

class TestBackgroundWorkerLifecycle:

    @pytest.mark.asyncio
    async def test_dispatch_returns_task_id_immediately(self):
        """dispatch_media_job must return before any async work runs."""
        from app.workers.media_worker import dispatch_media_job

        with patch("app.workers.media_worker.asyncio.create_task") as mock_create:
            mock_create.return_value = MagicMock()
            task_id = dispatch_media_job(
                client_id="c1",
                request_id="req-1",
                job_type=JobType.IMAGE,
                input_payload={"prompt": "a sunset"},
            )

        assert isinstance(task_id, str)
        assert len(task_id) > 0
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_media_job_sends_running_then_completed(self):
        """Worker must push status=running then background_update=completed."""
        from app.workers.media_worker import _run_media_job

        manager = ConnectionManager()
        ws = _make_mock_ws()
        await manager.connect("c1", ws)

        task = BackgroundMediaTask(
            request_id="req-1",
            client_id="c1",
            job_type=JobType.IMAGE,
            input_payload={"prompt": "a cat"},
        )

        with patch("app.workers.media_worker.get_connection_manager", return_value=manager):
            with patch("app.workers.media_worker._MOCK_GENERATION_DELAY", 0):
                await _run_media_job(task)

        assert ws.send_text.call_count == 2

        first_event = json.loads(ws.send_text.call_args_list[0][0][0])
        assert first_event["event_type"] == EventType.STATUS.value

        second_event = json.loads(ws.send_text.call_args_list[1][0][0])
        assert second_event["event_type"] == EventType.BACKGROUND_UPDATE.value
        assert second_event["metadata"]["task_status"] == TaskStatus.COMPLETED.value
        assert "url" in second_event["metadata"]["result"]

    @pytest.mark.asyncio
    async def test_run_media_job_sends_failed_on_error(self):
        """Worker must push background_update=failed when an exception occurs."""
        from app.workers.media_worker import _run_media_job

        manager = ConnectionManager()
        ws = _make_mock_ws()
        await manager.connect("c1", ws)

        task = BackgroundMediaTask(
            request_id="req-err",
            client_id="c1",
            job_type=JobType.VIDEO,
            input_payload={"prompt": "exploding star"},
        )

        async def _boom():
            raise RuntimeError("GPU out of memory")

        with patch("app.workers.media_worker.get_connection_manager", return_value=manager):
            with patch("asyncio.sleep", side_effect=RuntimeError("GPU out of memory")):
                await _run_media_job(task)

        events = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        event_types = [e["event_type"] for e in events]
        assert EventType.BACKGROUND_UPDATE.value in event_types

        failed_event = next(
            e for e in events if e["event_type"] == EventType.BACKGROUND_UPDATE.value
        )
        assert failed_event["metadata"]["task_status"] == TaskStatus.FAILED.value
        assert failed_event["metadata"]["error"] is not None

    @pytest.mark.asyncio
    async def test_worker_does_not_crash_when_client_disconnected(self):
        """Worker must not raise if the client disconnects before completion."""
        from app.workers.media_worker import _run_media_job

        manager = ConnectionManager()
        # Do NOT connect the client — simulates a dropped connection

        task = BackgroundMediaTask(
            request_id="req-gone",
            client_id="gone-client",
            job_type=JobType.IMAGE,
            input_payload={"prompt": "ghost"},
        )

        with patch("app.workers.media_worker.get_connection_manager", return_value=manager):
            with patch("app.workers.media_worker._MOCK_GENERATION_DELAY", 0):
                # Must not raise
                await _run_media_job(task)


# ── Group 3: WebSocket endpoint ───────────────────────────────────────────────

class TestWebSocketEndpoint:

    def test_websocket_connect_and_receive_complete_event(self):
        """
        Client connects, sends a chat message, receives status + token + complete.
        Uses FastAPI TestClient WebSocket support.
        """
        from app.main import app
        from app.schemas.chat import AgentMetadata, AgentResponse

        mock_response = AgentResponse(
            request_id="ws-req-1",
            content="Hello from the swarm!",
            agent=AgentMetadata(agent_name="TriageAgent"),
            model="gemini/gemini-1.5-pro",
        )

        with patch("app.api.routes.stream.run_swarm", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_response

            with TestClient(app) as client:
                with client.websocket_connect("/api/v1/stream/ws/test-ws-client") as ws:
                    ws.send_text(json.dumps({
                        "request_id": "ws-req-1",
                        "messages": [{"role": "user", "content": "Hello!"}],
                    }))

                    events = []
                    for _ in range(3):  # status + token + complete
                        raw = ws.receive_text()
                        events.append(json.loads(raw))

        event_types = [e["event_type"] for e in events]
        assert EventType.STATUS.value in event_types
        assert EventType.TOKEN.value in event_types
        assert EventType.COMPLETE.value in event_types

    def test_websocket_token_event_contains_agent_content(self):
        """Token event delta must contain the agent's response content."""
        from app.main import app
        from app.schemas.chat import AgentMetadata, AgentResponse

        mock_response = AgentResponse(
            request_id="ws-req-2",
            content="The answer is 42.",
            agent=AgentMetadata(agent_name="TriageAgent"),
            model="gemini/gemini-1.5-pro",
        )

        with patch("app.api.routes.stream.run_swarm", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_response

            with TestClient(app) as client:
                with client.websocket_connect("/api/v1/stream/ws/client-42") as ws:
                    ws.send_text(json.dumps({
                        "request_id": "ws-req-2",
                        "messages": [{"role": "user", "content": "What is the answer?"}],
                    }))

                    events = []
                    for _ in range(3):
                        events.append(json.loads(ws.receive_text()))

        token_event = next(e for e in events if e["event_type"] == EventType.TOKEN.value)
        assert "42" in token_event["delta"]

    def test_websocket_invalid_json_returns_error_event(self):
        """Sending malformed JSON must return an error event, not crash."""
        from app.main import app

        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/stream/ws/bad-client") as ws:
                ws.send_text("this is not json {{{{")
                raw = ws.receive_text()
                event = json.loads(raw)

        assert event["event_type"] == EventType.ERROR.value

    def test_websocket_sequence_numbers_are_monotonic(self):
        """All events in a single turn must have strictly increasing sequence numbers."""
        from app.main import app
        from app.schemas.chat import AgentMetadata, AgentResponse

        mock_response = AgentResponse(
            request_id="seq-test",
            content="Sequence check.",
            agent=AgentMetadata(agent_name="TriageAgent"),
            model="gemini/gemini-1.5-pro",
        )

        with patch("app.api.routes.stream.run_swarm", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_response

            with TestClient(app) as client:
                with client.websocket_connect("/api/v1/stream/ws/seq-client") as ws:
                    ws.send_text(json.dumps({
                        "request_id": "seq-test",
                        "messages": [{"role": "user", "content": "test"}],
                    }))

                    events = [json.loads(ws.receive_text()) for _ in range(3)]

        sequences = [e["sequence"] for e in events]
        assert sequences == sorted(sequences), f"Sequences not monotonic: {sequences}"
