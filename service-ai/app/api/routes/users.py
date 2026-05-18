"""
app/api/routes/users.py
────────────────────────
User management endpoints.

Routes:
  GET    /api/v1/users/usage                 — token usage stats for authenticated user
  DELETE /api/v1/chat/history/{session_id}   — clear authenticated conversation history
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, verify_api_key
from app.core.logging import get_logger
from app.services import history_service
from app.services.user_service import get_user_usage as read_user_usage

logger = get_logger(__name__)
router = APIRouter()


class UsageResponse(BaseModel):
    user_id: str
    total_tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    is_anonymous: bool


@router.get(
    "/usage",
    response_model=UsageResponse,
    status_code=status.HTTP_200_OK,
    summary="Get token usage for a user",
    tags=["Users"],
    dependencies=[Depends(verify_api_key)],
)
async def get_user_usage(user: CurrentUser) -> UsageResponse:
    """Return cumulative token usage counters for the authenticated user."""
    doc = await read_user_usage(user["user_id"])
    return UsageResponse(
        user_id=doc["user_id"],
        total_tokens_used=doc.get("total_tokens_used", 0),
        prompt_tokens=doc.get("prompt_tokens", 0),
        completion_tokens=doc.get("completion_tokens", 0),
        is_anonymous=doc.get("is_anonymous", True),
    )


history_router = APIRouter()


@history_router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear conversation history for a session",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_history(session_id: str, user: CurrentUser) -> None:
    """Delete all stored messages for the given session_id."""
    await history_service.delete_history(session_id=session_id, user_id=user["user_id"])
    logger.info("History cleared — session_id=%s, user_id=%s", session_id, user["user_id"])
