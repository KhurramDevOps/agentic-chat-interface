"""
app/services/streaming_service.py
───────────────────────────────────
ConnectionManager — singleton that tracks active WebSocket connections.

This is the critical bridge between:
  - The WebSocket route  (registers / deregisters clients)
  - The background worker (looks up a client_id and pushes events)

Design:
  - One dict keyed by client_id → WebSocket instance.
  - All send operations are fire-and-forget with error isolation so a
    dropped connection never crashes the background worker.
  - Thread-safe for asyncio (single-threaded event loop); no locks needed.

Constitution compliance:
  - No MongoDB imports or connections.
  - No blocking I/O — all WebSocket sends are awaited.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import WebSocket

from app.core.logging import get_logger
from app.schemas.streaming import ChatStreamEvent

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ConnectionManager:
    """
    In-memory registry of active WebSocket connections.

    Usage:
        manager = get_connection_manager()          # singleton
        await manager.connect(client_id, websocket)
        await manager.send_event(client_id, event)
        manager.disconnect(client_id)
    """

    def __init__(self) -> None:
        # client_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # Per-client sequence counter for ChatStreamEvent monotonicity
        self._sequences: dict[str, int] = {}

    # ── Connection lifecycle ──────────────────────────────────────────────

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections[client_id] = websocket
        self._sequences[client_id] = 0
        logger.info("WebSocket connected — client_id=%s, total=%d",
                    client_id, len(self._connections))

    def disconnect(self, client_id: str) -> None:
        """Remove a client from the registry (called on close or error)."""
        self._connections.pop(client_id, None)
        self._sequences.pop(client_id, None)
        logger.info("WebSocket disconnected — client_id=%s, remaining=%d",
                    client_id, len(self._connections))

    # ── Sending ───────────────────────────────────────────────────────────

    async def send_event(self, client_id: str, event: ChatStreamEvent) -> bool:
        """
        Send a ChatStreamEvent to a specific client.

        Returns True if sent successfully, False if client not found or send failed.
        Errors are logged but never re-raised — a dead connection must not
        crash the background worker.
        """
        ws = self._connections.get(client_id)
        if ws is None:
            logger.warning(
                "send_event: client_id=%s not connected (event_type=%s)",
                client_id, event.event_type,
            )
            return False

        try:
            await ws.send_text(event.model_dump_json())
            logger.debug(
                "send_event OK — client_id=%s, event_type=%s, seq=%d",
                client_id, event.event_type, event.sequence,
            )
            return True
        except Exception as exc:
            logger.warning(
                "send_event failed — client_id=%s, error=%s", client_id, exc
            )
            self.disconnect(client_id)
            return False

    async def broadcast(self, event: ChatStreamEvent) -> int:
        """
        Send an event to ALL connected clients.
        Returns the number of successful sends.
        """
        sent = 0
        for client_id in list(self._connections):
            if await self.send_event(client_id, event):
                sent += 1
        return sent

    # ── Sequence helpers ──────────────────────────────────────────────────

    def next_sequence(self, client_id: str) -> int:
        """Return and increment the monotonic sequence counter for a client."""
        seq = self._sequences.get(client_id, 0)
        self._sequences[client_id] = seq + 1
        return seq

    # ── Introspection ─────────────────────────────────────────────────────

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    def is_connected(self, client_id: str) -> bool:
        return client_id in self._connections


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Return the process-wide ConnectionManager singleton."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
        logger.info("ConnectionManager initialised.")
    return _manager
