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

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.swarm import stream_swarm
from app.core.logging import get_logger
from app.core.type_guards import ensure_dict
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.streaming import ChatStreamEvent
from app.services.history_service import append_to_history, get_history, message_count
from app.services.streaming_service import get_connection_manager

logger = get_logger(__name__)
router = APIRouter()


# ── Mem0 helper ───────────────────────────────────────────────────────────────

async def _get_mem0_context(user_id: str, query: str) -> str:
    """
    Query Mem0 for facts relevant to this user and query.
    Returns a formatted string to inject into the system prompt.
    Returns empty string if Mem0 is unavailable or no facts found.
    """
    try:
        from mem0 import AsyncMemoryClient  # noqa: PLC0415
        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        if not settings.mem0_api_key:
            return ""

        client = AsyncMemoryClient(api_key=settings.mem0_api_key)
        results = await client.search(query=query, user_id=user_id, limit=5)

        if not results:
            return ""

        facts = [r.get("memory", "") for r in results if r.get("memory")]
        if not facts:
            return ""

        return "Relevant facts about this user:\n" + "\n".join(f"- {f}" for f in facts)

    except Exception as exc:
        logger.warning("Mem0 query failed — user_id=%s, error=%s", user_id, exc)
        return ""


async def _save_to_mem0(user_id: str, messages: list[dict]) -> None:
    """
    Save the current turn to Mem0 for long-term memory.
    Fire-and-forget — errors are logged but never raised.
    """
    try:
        from mem0 import AsyncMemoryClient  # noqa: PLC0415
        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        if not settings.mem0_api_key:
            return

        client = AsyncMemoryClient(api_key=settings.mem0_api_key)
        await client.add(messages=messages, user_id=user_id)

    except Exception as exc:
        logger.warning("Mem0 save failed — user_id=%s, error=%s", user_id, exc)


# ── Title generation helper ───────────────────────────────────────────────────

async def _generate_title(user_message: str) -> str:
    """
    Generate a 3-4 word session title from the first user message.
    Falls back to a truncated version of the message on failure.
    """
    try:
        from openai import AsyncOpenAI  # noqa: PLC0415
        from app.core.llm_proxy import get_openai_client  # noqa: PLC0415
        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        client: AsyncOpenAI = get_openai_client()

        response = await client.chat.completions.create(
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

@router.websocket("/ws/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str) -> None:
    """
    Persistent WebSocket endpoint for a single chat client.

    The payload sent by the frontend must include:
      {
        "request_id":       "uuid",
        "messages":         [{"role": "user", "content": "..."}],
        "model":            "groq/llama-3.3-70b-versatile",
        "memory_context_id": "session-uuid",
        "user_id":          "mongodb-user-id"   ← injected by frontend from JWT
      }
    """
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
                    messages=[ChatMessage(**m) for m in messages_raw],
                    model=payload.get("model", "groq/llama-3.3-70b-versatile"),
                    stream=True,
                    memory_context_id=payload.get("memory_context_id"),
                )
            except Exception as exc:
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(request_id=request_id, sequence=seq,
                                         message=f"Request validation error: {exc}"),
                )
                continue

            session_id      = request.memory_context_id or client_id
            user_message    = request.last_user_message
            is_first_turn   = (await message_count(session_id)) == 0

            # ── Issue 2: Load full history and merge ──────────────────────
            history = await get_history(session_id)
            if history:
                stored = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
                incoming = {m.content for m in request.messages}
                deduped  = [m for m in stored if m.content not in incoming]
                request  = request.model_copy(
                    update={"messages": deduped + list(request.messages)}
                )

            # ── Issue 3: Inject Mem0 long-term memory as system message ───
            mem0_context = await _get_mem0_context(user_id, user_message)
            if mem0_context:
                mem0_msg = ChatMessage(role="system", content=mem0_context)
                request  = request.model_copy(
                    update={"messages": [mem0_msg] + list(request.messages)}
                )
                logger.info("Mem0 context injected — user_id=%s, facts=%d chars",
                            user_id, len(mem0_context))

            # ── Status ────────────────────────────────────────────────────
            seq = manager.next_sequence(client_id)
            await manager.send_event(
                client_id,
                ChatStreamEvent.status(request_id=request_id, sequence=seq,
                                       message="Processing your message..."),
            )

            # ── Stream tokens ─────────────────────────────────────────────
            full_response = ""
            try:
                async for delta in stream_swarm(request):
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
            await append_to_history(session_id, "user", user_message)
            if full_response:
                await append_to_history(session_id, "assistant", full_response)

            # ── Issue 3: Save turn to Mem0 for long-term memory ───────────
            await _save_to_mem0(user_id, [
                {"role": "user",      "content": user_message},
                {"role": "assistant", "content": full_response},
            ])

            logger.info("Turn complete — client_id=%s, response_len=%d",
                        client_id, len(full_response))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected — client_id=%s", client_id)
    except Exception as exc:
        logger.exception("WebSocket error — client_id=%s, error=%s", client_id, exc)
    finally:
        manager.disconnect(client_id)
