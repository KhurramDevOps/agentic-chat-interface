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

Fixes applied:
  - Short-term memory: full MongoDB history merged before every swarm call.
  - Long-term memory: Mem0 queried with correct v2 filters syntax before swarm.
  - Title generation: lightweight LLM call on first turn, streamed as title_update.
  - Tool crash guard: Mem0 failures are caught and never crash the stream.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.swarm import stream_swarm, get_last_stream_usage
from app.core.logging import get_logger
from app.core.type_guards import ensure_dict
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.streaming import ChatStreamEvent
from app.services.history_service import append_to_history, get_history, message_count
from app.services.streaming_service import get_connection_manager
from app.services.user_service import record_token_usage

logger = get_logger(__name__)
router = APIRouter()


# ── Mem0 helpers ──────────────────────────────────────────────────────────────

async def _get_mem0_context(user_id: str, query: str) -> str:
    """
    Query Mem0 for facts relevant to this user and query.
    Injects results as a system message before the swarm call.

    FIX: mem0 v2 AsyncMemoryClient.search() does NOT accept user_id as a
    top-level parameter — it must go inside filters={"user_id": ...}.
    """
    try:
        from mem0 import AsyncMemoryClient  # noqa: PLC0415
        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        if not settings.mem0_api_key:
            return ""

        client = AsyncMemoryClient(api_key=settings.mem0_api_key)

        # ✅ Correct mem0 v2 syntax
        raw = await client.search(
            query=query,
            filters={"user_id": user_id},
            limit=5,
        )

        # v2 returns {"results": [...]}; older versions return a plain list
        if isinstance(raw, dict):
            results = raw.get("results", [])
        elif isinstance(raw, list):
            results = raw
        else:
            results = []

        facts = []
        for r in results:
            text = (r.get("memory") or r.get("text") or "") if isinstance(r, dict) else str(r)
            if text:
                facts.append(text)

        if not facts:
            return ""

        return "Relevant facts about this user:\n" + "\n".join(f"- {f}" for f in facts)

    except Exception as exc:
        # Never crash the stream over a Mem0 failure
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
        logger.debug("Mem0 save OK — user_id=%s, turns=%d", user_id, len(messages))

    except Exception as exc:
        logger.warning("Mem0 save failed — user_id=%s, error=%s", user_id, exc)


# ── Title generation ──────────────────────────────────────────────────────────

async def _generate_title(user_message: str) -> str:
    """
    Generate a 3-4 word session title from the first user message.
    Falls back to a truncated version of the message on failure.
    """
    try:
        from app.core.llm_proxy import get_openai_client  # noqa: PLC0415
        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        client = get_openai_client()

        response = await client.chat.completions.create(
            model=settings.active_model,
            messages=[{
                "role": "user",
                "content": (
                    "Generate a concise 3-4 word title for a chat session that starts with "
                    "this message. Return ONLY the title, no punctuation, no quotes.\n\n"
                    "Message: " + user_message[:200]
                ),
            }],
            max_tokens=20,
        )
        title = response.choices[0].message.content or ""
        return title.strip().strip('"').strip("'")

    except Exception as exc:
        logger.warning("Title generation failed — %s", exc)
        return user_message[:30] + ("…" if len(user_message) > 30 else "")


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str) -> None:
    """
    Persistent WebSocket endpoint for a single chat client.

    Expected payload from frontend:
      {
        "request_id":        "uuid",
        "messages":          [{"role": "user", "content": "..."}],
        "model":             "gemini/gemini-1.5-pro",
        "memory_context_id": "session-uuid",
        "user_id":           "mongodb-user-id"
      }
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
                        request_id="unknown", sequence=seq,
                        message=f"Invalid JSON payload: {exc}",
                    ),
                )
                continue

            request_id   = payload.get("request_id") or client_id
            user_id      = payload.get("user_id") or client_id
            messages_raw = payload.get("messages", [])

            if not messages_raw:
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
                        request_id=request_id, sequence=seq,
                        message=f"Request validation error: {exc}",
                    ),
                )
                continue

            session_id    = request.memory_context_id or client_id
            user_message  = request.last_user_message
            is_first_turn = (await message_count(session_id)) == 0

            # ── Short-term memory: load full history and merge ────────────
            history = await get_history(session_id)
            if history:
                stored   = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
                incoming = {m.content for m in request.messages}
                deduped  = [m for m in stored if m.content not in incoming]
                request  = request.model_copy(
                    update={"messages": deduped + list(request.messages)}
                )

            # ── Long-term memory: inject Mem0 facts as system message ─────
            mem0_context = await _get_mem0_context(user_id, user_message)
            if mem0_context:
                mem0_msg = ChatMessage(role="system", content=mem0_context)
                request  = request.model_copy(
                    update={"messages": [mem0_msg] + list(request.messages)}
                )
                logger.info("Mem0 context injected — user_id=%s, chars=%d",
                            user_id, len(mem0_context))

            # ── Status ────────────────────────────────────────────────────
            seq = manager.next_sequence(client_id)
            await manager.send_event(
                client_id,
                ChatStreamEvent.status(
                    request_id=request_id, sequence=seq,
                    message="Processing your message...",
                ),
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
                            ChatStreamEvent.token(
                                request_id=request_id, sequence=seq, delta=delta,
                            ),
                        )
            except Exception as exc:
                logger.exception("Swarm streaming error — client_id=%s", client_id)
                seq = manager.next_sequence(client_id)
                await manager.send_event(
                    client_id,
                    ChatStreamEvent.error(
                        request_id=request_id, sequence=seq,
                        message=f"Agent error: {exc}",
                    ),
                )
                continue

            # ── Complete ──────────────────────────────────────────────────
            seq = manager.next_sequence(client_id)
            await manager.send_event(
                client_id,
                ChatStreamEvent.complete(request_id=request_id, sequence=seq),
            )

            # ── Title update on first turn ────────────────────────────────
            if is_first_turn:
                title = await _generate_title(user_message)
                if title:
                    await websocket.send_text(json.dumps({
                        "event_type": "title_update",
                        "request_id": request_id,
                        "title": title,
                    }))
                    logger.info("Title sent — session=%s, title=%s", session_id, title)

            # ── Persist to short-term history ─────────────────────────────
            await append_to_history(session_id, "user", user_message)
            if full_response:
                await append_to_history(session_id, "assistant", full_response)

            # ── Record token usage ────────────────────────────────────────
            usage = get_last_stream_usage()
            if usage.get("total_tokens"):
                await record_token_usage(
                    user_id=user_id,
                    session_id=session_id,
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                )

            # ── Save to Mem0 for long-term memory ─────────────────────────
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
