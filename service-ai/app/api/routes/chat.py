"""
app/api/routes/chat.py  (T024)
────────────────────────────────
OpenAI-compatible chat completion endpoint.

Routes:
  POST /api/v1/chat/completions — non-streaming chat via TriageAgent swarm

History flow:
  1. Derive session_id from memory_context_id (or request_id fallback).
  2. Load existing history from HistoryStore.
  3. Merge history + new user message into request.messages.
  4. Run swarm with full context.
  5. Append user message + assistant response to history.

Constitution compliance:
  - No MongoDB imports or connections.
  - Delegates all LLM work to the swarm; route is thin orchestration only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.agents.swarm import run_swarm
from app.api.deps import get_request_id, http_error
from app.core.logging import get_logger
from app.schemas.chat import AgentResponse, ChatMessage, ChatRequest
from app.services.history_service import get_history_store

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/completions",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat completion via TriageAgent swarm",
    description=(
        "Accepts an OpenAI-style chat request, routes it through the "
        "TriageAgent swarm (with handoffs to Research/Memory agents), "
        "and returns the final agent response. Maintains conversation "
        "history per session_id across requests."
    ),
    tags=["Chat"],
)
async def chat_completions(
    body: ChatRequest,
    request_id: str = Depends(get_request_id),
) -> AgentResponse:
    # Stamp the request_id from the header if the client didn't supply one
    if body.request_id == "":
        body = body.model_copy(update={"request_id": request_id})

    session_id = body.memory_context_id or body.request_id

    logger.info(
        "POST /chat/completions — request_id=%s, session_id=%s, model=%s",
        body.request_id,
        session_id,
        body.model,
    )

    # ── Load history and merge with incoming messages ─────────────────────
    store = get_history_store()
    history = store.get(session_id)

    if history:
        # Prepend stored history to the incoming messages.
        # The client may send only the latest user message — we enrich it
        # with the full session context from the store.
        stored_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history]

        # Avoid duplicating messages the client already sent
        incoming_contents = {m.content for m in body.messages}
        deduped_history = [m for m in stored_messages if m.content not in incoming_contents]

        merged_messages = deduped_history + list(body.messages)
        body = body.model_copy(update={"messages": merged_messages})

        logger.info(
            "history loaded — session=%s, history_msgs=%d, total_msgs=%d",
            session_id, len(history), len(merged_messages),
        )

    # ── Run swarm ─────────────────────────────────────────────────────────
    try:
        response = await run_swarm(body)
    except Exception as exc:
        logger.exception("Swarm execution failed — request_id=%s", body.request_id)
        raise http_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="SWARM_ERROR",
            message=f"Agent swarm encountered an error: {exc}",
            request_id=body.request_id,
        ) from exc

    # ── Persist user message + assistant response to history ──────────────
    user_message = body.last_user_message
    store.append(session_id, "user", user_message)
    store.append(session_id, "assistant", response.content)

    logger.info(
        "history saved — session=%s, total_msgs=%d",
        session_id, store.message_count(session_id),
    )

    return response
