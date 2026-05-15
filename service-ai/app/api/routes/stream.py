"""
app/api/routes/stream.py  (T032)
──────────────────────────────────
WebSocket streaming endpoint for real-time tokens and background task updates.

Endpoint:
  WS /api/v1/stream/ws/{client_id}

Protocol:
  Client → Server : JSON matching ChatRequest schema
  Server → Client : JSON-serialised ChatStreamEvent messages

  Event sequence for a normal chat turn:
    status(sequence=0)   "Processing your message..."
    token(sequence=1..N) incremental output chunks  [future: streaming LLM]
    complete(sequence=N) terminal marker

  For a media generation request:
    status(sequence=0)   "Dispatching media job..."
    complete(sequence=1) immediate acknowledgment
    background_update    pushed later by the background worker

Constitution compliance:
  - No MongoDB imports or connections.
  - All long-running work is dispatched to background tasks via run_swarm /
    MediaAgent — the WebSocket handler never blocks.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.agents.swarm import run_swarm, stream_swarm
from app.core.logging import get_logger
from app.core.type_guards import ensure_dict
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.streaming import ChatStreamEvent
from app.services.history_service import get_history_store
from app.services.streaming_service import get_connection_manager

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str) -> None:
    """
    Persistent WebSocket endpoint for a single chat client.

    - Registers the connection with ConnectionManager on connect.
    - Listens for incoming JSON chat messages in a loop.
    - Routes each message through the TriageAgent swarm.
    - Streams the response back as ChatStreamEvent messages.
    - Deregisters on disconnect or error.
    """
    manager = get_connection_manager()
    await manager.connect(client_id, websocket)

    logger.info("WebSocket session started — client_id=%s", client_id)

    try:
        while True:
            # ── Receive ───────────────────────────────────────────────────
            raw = await websocket.receive_text()

            try:
                payload = json.loads(raw)
                ensure_dict(payload, "WebSocket message payload")
            except (json.JSONDecodeError, TypeError) as exc:
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(
                        request_id="unknown",
                        sequence=seq,
                        message=f"Invalid JSON payload: {exc}",
                    ),
                )
                continue

            # Build ChatRequest — use client_id as request_id if not supplied
            request_id = payload.get("request_id") or client_id
            messages_raw = payload.get("messages", [])
            if not messages_raw:
                # Treat bare string as a single user message
                content = payload.get("content") or payload.get("message") or str(payload)
                messages_raw = [{"role": "user", "content": content}]

            try:
                request = ChatRequest(
                    request_id=request_id,
                    messages=[ChatMessage(**m) for m in messages_raw],
                    model=payload.get("model", "gemini/gemini-1.5-pro"),
                    stream=True,
                    memory_context_id=payload.get("memory_context_id"),
                )
            except Exception as exc:
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(
                        request_id=request_id,
                        sequence=seq,
                        message=f"Request validation error: {exc}",
                    ),
                )
                continue

            # ── Load and merge conversation history ───────────────────────
            session_id = request.memory_context_id or client_id
            history_store = get_history_store()
            history = history_store.get(session_id)

            if history:
                stored_messages = [
                    ChatMessage(role=m["role"], content=m["content"])
                    for m in history
                ]
                incoming_contents = {m.content for m in request.messages}
                deduped = [m for m in stored_messages if m.content not in incoming_contents]
                request = request.model_copy(
                    update={"messages": deduped + list(request.messages)}
                )

            # ── Status: processing ────────────────────────────────────────
            seq = manager.next_sequence(client_id)
            await manager.send_event(
                client_id,
                ChatStreamEvent.status(
                    request_id=request_id,
                    sequence=seq,
                    message="Processing your message...",
                ),
            )

            # ── Stream tokens token-by-token ──────────────────────────────
            full_response = ""
            try:
                async for delta in stream_swarm(request):
                    if delta:
                        full_response += delta
                        seq = manager.next_sequence(client_id)
                        await manager.send_event(
                            client_id,
                            ChatStreamEvent.token(
                                request_id=request_id,
                                sequence=seq,
                                delta=delta,
                            ),
                        )
            except Exception as exc:
                logger.exception("Swarm streaming error — client_id=%s", client_id)
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(
                        request_id=request_id,
                        sequence=seq,
                        message=f"Agent error: {exc}",
                    ),
                )
                continue

            # ── Complete ──────────────────────────────────────────────────
            seq = manager.next_sequence(client_id)
            await manager.send_event(
                client_id,
                ChatStreamEvent.complete(
                    request_id=request_id,
                    sequence=seq,
                ),
            )

            # ── Save turn to history ──────────────────────────────────────
            history_store.append(session_id, "user", request.last_user_message)
            if full_response:
                history_store.append(session_id, "assistant", full_response)

            logger.info(
                "WebSocket turn complete — client_id=%s, response_len=%d",
                client_id, len(full_response),
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected — client_id=%s", client_id)
    except Exception as exc:
        logger.exception("WebSocket error — client_id=%s, error=%s", client_id, exc)
    finally:
        manager.disconnect(client_id)
