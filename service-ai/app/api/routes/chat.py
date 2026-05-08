"""
app/api/routes/chat.py  (T024)
────────────────────────────────
OpenAI-compatible chat completion endpoint.

Routes:
  POST /api/v1/chat/completions — non-streaming chat via TriageAgent swarm

Constitution compliance:
  - No MongoDB imports or connections.
  - Delegates all LLM work to the swarm; route is thin orchestration only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.agents.swarm import run_swarm
from app.api.deps import get_request_id, http_error
from app.core.logging import get_logger
from app.schemas.chat import AgentResponse, ChatRequest

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
        "and returns the final agent response."
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

    logger.info(
        "POST /chat/completions — request_id=%s, model=%s",
        body.request_id,
        body.model,
    )

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

    return response
