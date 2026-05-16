"""
app/schemas/streaming.py  (T028)
──────────────────────────────────
Pydantic models for streaming events and media task records.

Maps to ChatStreamEvent and BackgroundMediaTask in the data model spec.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    TOKEN            = "token"
    STATUS           = "status"
    ERROR            = "error"
    COMPLETE         = "complete"
    BACKGROUND_UPDATE = "background_update"


class JobType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class TaskStatus(str, Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


# ── Streaming event ───────────────────────────────────────────────────────────

class ChatStreamEvent(BaseModel):
    """
    Outbound incremental event pushed over WebSocket or SSE.

    Validation rules (from data model spec):
      - sequence must be monotonic per request.
      - event_type=complete must terminate the stream.
      - event_type=background_update carries async task status changes.
    """

    event_type: EventType
    request_id: str
    sequence: int = Field(..., ge=0, description="Monotonically increasing per request.")
    delta: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def token(cls, request_id: str, sequence: int, delta: str) -> "ChatStreamEvent":
        return cls(event_type=EventType.TOKEN, request_id=request_id,
                   sequence=sequence, delta=delta)

    @classmethod
    def status(cls, request_id: str, sequence: int, message: str) -> "ChatStreamEvent":
        return cls(event_type=EventType.STATUS, request_id=request_id,
                   sequence=sequence, delta=message)

    @classmethod
    def complete(cls, request_id: str, sequence: int) -> "ChatStreamEvent":
        return cls(event_type=EventType.COMPLETE, request_id=request_id,
                   sequence=sequence)

    @classmethod
    def background_update(
        cls,
        request_id: str,
        sequence: int,
        task_id: str,
        task_status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> "ChatStreamEvent":
        return cls(
            event_type=EventType.BACKGROUND_UPDATE,
            request_id=request_id,
            sequence=sequence,
            metadata={
                "task_id": task_id,
                "task_status": task_status.value,
                "result": result,
                "error": error,
            },
        )

    @classmethod
    def error(cls, request_id: str, sequence: int, message: str) -> "ChatStreamEvent":
        return cls(event_type=EventType.ERROR, request_id=request_id,
                   sequence=sequence, delta=message)


# ── Background media task ─────────────────────────────────────────────────────

class BackgroundMediaTask(BaseModel):
    """
    Task record for a deferred media generation job.

    State machine: queued → running → completed | failed
    """

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    client_id: str = Field(description="WebSocket client_id to push updates to.")
    job_type: JobType
    status: TaskStatus = TaskStatus.QUEUED
    input_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def transition(self, new_status: TaskStatus) -> "BackgroundMediaTask":
        """Return a copy with updated status and updated_at timestamp."""
        valid: dict[TaskStatus, set[TaskStatus]] = {
            TaskStatus.QUEUED:    {TaskStatus.RUNNING},
            TaskStatus.RUNNING:   {TaskStatus.COMPLETED, TaskStatus.FAILED},
            TaskStatus.COMPLETED: set(),
            TaskStatus.FAILED:    set(),
        }
        if new_status not in valid[self.status]:
            raise ValueError(
                f"Invalid state transition: {self.status} → {new_status}. "
                f"Allowed: {valid[self.status]}"
            )
        return self.model_copy(
            update={
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
