"""
app/api/routes/stream.py
─────────────────────────
WebSocket streaming endpoint.

Endpoint: WS /api/v1/stream/ws/{client_id}

Event sequence per turn:
  status       "Processing your message..."
  token x N    incremental text deltas
  complete     terminal marker
  title_update (first turn only) — 3-4 word session title for the sidebar

Issue 2 fix: full history is loaded from MongoDB and merged before every
             swarm call — the AI always has full context.

Issue 3 fix: Mem0 is queried for long-term user facts before the swarm call.
             Facts are injected as a system message so the AI knows the user.

Issue 4 fix: on the first turn of a session, a lightweight LLM call generates
             a 3-4 word title which is streamed back as a title_update event.
"""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.agents.swarm import get_stream_usage, stream_swarm
from app.api.deps import SERVICE_API_KEY
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.type_guards import ensure_dict
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.streaming import ChatStreamEvent
from app.services import history_service, memory_service
from app.services.streaming_service import get_connection_manager
from app.services.user_service import record_token_usage

logger = get_logger(__name__)
router = APIRouter()


# ── Title generation helper ───────────────────────────────────────────────────

async def _generate_title(user_message: str) -> str:
    """
    Generate a 3-4 word session title from the first user message.
    Falls back to a truncated version of the message on failure.
    """
    try:
        from app.core.llm_proxy import chat_completion_with_fallback  # noqa: PLC0415
        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()

        response = await chat_completion_with_fallback(
            model=settings.active_model,
            messages=[{
                "role": "user",
                "content": (
                    "Generate a concise 3-4 word title for a chat session that starts with this message. "
                    "Return ONLY the title, no punctuation, no quotes.\n\n"
                    "Message: " + user_message[:200]
                ),
            }],
            max_tokens=20,
        )
        title = response.choices[0].message.content or ""
        return title.strip().strip('"').strip("'")

    except Exception as exc:
        logger.warning("Title generation failed — %s", exc)
        # Fallback: first 30 chars of the message
        return user_message[:30] + ("…" if len(user_message) > 30 else "")


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws")
@router.websocket("/ws/{client_id}")
async def websocket_chat(
    websocket: WebSocket,
    client_id: str | None = None,
    token: str | None = Query(None),
    api_key: str | None = Query(None),
) -> None:
    """
    Persistent WebSocket endpoint for a single chat client.

    The payload sent by the frontend must include:
      {
        "request_id":       "uuid",
        "messages":         [{"role": "user", "content": "..."}],
        "model":            "gemini/gemini-1.5-pro",
        "memory_context_id": "session-uuid",
        "user_id":          "mongodb-user-id"   ← injected by frontend from JWT
      }
    """
    user_id = _resolve_websocket_user_id(websocket, token=token, api_key=api_key)
    if not user_id:
        await websocket.close(code=1008)
        return

    client_id = client_id or user_id
    manager = get_connection_manager()
    await manager.connect(client_id, websocket)
    logger.info("WebSocket session started — client_id=%s", client_id)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                payload = json.loads(raw)
                ensure_dict(payload, "WebSocket message payload")
            except (json.JSONDecodeError, TypeError) as exc:
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(request_id="unknown", sequence=seq,
                                         message=f"Invalid JSON: {exc}"),
                )
                continue

            request_id = payload.get("request_id") or client_id
            user_id    = payload.get("user_id") or client_id  # Issue 3: Mem0 user key
            messages_raw = payload.get("messages", [])

            if not messages_raw:
                content = payload.get("content") or payload.get("message") or str(payload)
                messages_raw = [{"role": "user", "content": content}]

            try:
                request = ChatRequest(
                    request_id=request_id,
                    messages=[ChatMessage.model_validate(m) for m in messages_raw],
                    model=payload.get("model") or get_settings().active_model,
                    stream=True,
                    session_id=payload.get("session_id"),
                    memory_context_id=payload.get("memory_context_id") or payload.get("session_id"),
                )
            except Exception as exc:
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(request_id=request_id, sequence=seq,
                                         message=f"Request validation error: {exc}"),
                )
                continue

            session_id      = request.session_id or request.memory_context_id or client_id
            user_message    = request.last_user_message
            is_first_turn   = (await history_service.message_count(session_id, user_id)) == 0

            # ── Issue 2: Load full history and merge ──────────────────────
            history = await history_service.get_history(session_id=session_id, user_id=user_id)
            if history:
                stored = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
                incoming = {m.text_content for m in request.normalized_messages()}
                deduped  = [m for m in stored if m.text_content not in incoming]
                request  = request.model_copy(
                    update={"messages": deduped + request.normalized_messages()}
                )

            memory_context = await memory_service.get_memory_context_for_user(user_id=user_id)
            if memory_context:
                mem0_msg = ChatMessage(role="system", content=memory_context)
                request  = request.model_copy(
                    update={"messages": [mem0_msg] + request.normalized_messages()}
                )
                logger.info("Memory context injected — user_id=%s, chars=%d",
                            user_id, len(memory_context))

            await history_service.save_message(
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=user_message,
            )

            # ── Status ────────────────────────────────────────────────────
            seq = manager.next_sequence(client_id)
            await manager.send_event(
                client_id,
                ChatStreamEvent.status(request_id=request_id, sequence=seq,
                                       message="Processing your message..."),
            )

            # ── Stream tokens ─────────────────────────────────────────────
            full_response = ""
            result_container: dict = {}
            try:
                async for delta in stream_swarm(request, result_container=result_container):
                    if delta:
                        full_response += delta
                        seq = manager.next_sequence(client_id)
                        await manager.send_event(
                            client_id,
                            ChatStreamEvent.token(request_id=request_id,
                                                  sequence=seq, delta=delta),
                        )
            except Exception as exc:
                logger.exception("Swarm streaming error — client_id=%s", client_id)
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(request_id=request_id, sequence=seq,
                                         message=f"Agent error: {exc}"),
                )
                continue

            # ── Complete ──────────────────────────────────────────────────
            seq = manager.next_sequence(client_id)
            await manager.send_event(
                client_id,
                ChatStreamEvent.complete(request_id=request_id, sequence=seq),
            )

            # ── Issue 4: Generate and stream title on first turn ──────────
            if is_first_turn:
                title = await _generate_title(user_message)
                if title:
                    title_event = {
                        "event_type": "title_update",
                        "request_id": request_id,
                        "title": title,
                    }
                    await websocket.send_text(json.dumps(title_event))
                    logger.info("Title generated — session=%s, title=%s", session_id, title)

            # ── Persist turn to short-term history ────────────────────────
            if full_response:
                await history_service.save_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    content=full_response,
                )

            usage = get_stream_usage(result_container.get("result"))
            await record_token_usage(
                session_id=session_id,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                user_id=user_id,
            )

            asyncio.create_task(
                memory_service.extract_memories_background(
                    messages=[
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": full_response},
                    ],
                    user_id=user_id,
                    session_id=session_id,
                )
            )

            logger.info("Turn complete — client_id=%s, response_len=%d",
                        client_id, len(full_response))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected — client_id=%s", client_id)
    except Exception as exc:
        logger.exception("WebSocket error — client_id=%s, error=%s", client_id, exc)
    finally:
        manager.disconnect(client_id)


def _resolve_websocket_user_id(
    websocket: WebSocket,
    token: str | None,
    api_key: str | None,
) -> str | None:
    header_api_key = websocket.headers.get("x-api-key")
    supplied_api_key = api_key or header_api_key
    expected_key = SERVICE_API_KEY or get_settings().api_key
    if expected_key and supplied_api_key != expected_key:
        return None

    header_user_id = websocket.headers.get("x-user-id")
    if header_user_id:
        return header_user_id

    if token:
        return _verify_token_and_get_user_id(token)
    return None


def _verify_token_and_get_user_id(token: str) -> str | None:
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        return None
    try:
        import jwt  # type: ignore[import-untyped]  # noqa: PLC0415
        decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        return decoded.get("id") or decoded.get("sub") or decoded.get("user_id")
    except Exception as exc:
        logger.warning("WebSocket JWT verification failed — %s", exc)
        return None
