"""
app/workers/media_worker.py  (T029 / T033)
───────────────────────────────────────────
Background worker for long-running media generation jobs.

Flow:
  1. MediaAgent calls dispatch_media_job() — returns immediately with task_id.
  2. dispatch_media_job() schedules _run_media_job() as an asyncio Task.
  3. _run_media_job() simulates work (asyncio.sleep), then pushes a
     ChatStreamEvent(event_type=background_update) to the client via
     the ConnectionManager singleton.

Constitution compliance:
  - No MongoDB imports or connections.
  - No blocking I/O — asyncio.sleep mocks the long-running work.
  - ConnectionManager send errors are isolated; worker never crashes.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.schemas.streaming import (
    BackgroundMediaTask,
    ChatStreamEvent,
    JobType,
    TaskStatus,
)
from app.services.streaming_service import get_connection_manager

logger = get_logger(__name__)

# Simulated generation time (seconds) — replace with real API call in production
_MOCK_GENERATION_DELAY = 3


def dispatch_media_job(
    client_id: str,
    request_id: str,
    job_type: JobType,
    input_payload: dict,
) -> str:
    """
    Schedule a background media generation job and return the task_id immediately.

    This function is synchronous and non-blocking — it creates an asyncio Task
    and returns before any work is done.

    Args:
        client_id:     WebSocket client to push the completion event to.
        request_id:    Originating chat request ID for correlation.
        job_type:      image | video | audio
        input_payload: Job-specific parameters (prompt, dimensions, etc.)

    Returns:
        task_id string — the caller should surface this to the user immediately.
    """
    task = BackgroundMediaTask(
        request_id=request_id,
        client_id=client_id,
        job_type=job_type,
        input_payload=input_payload,
    )

    # Schedule the async worker — fire and forget
    asyncio.create_task(
        _run_media_job(task),
        name=f"media-job-{task.task_id}",
    )

    logger.info(
        "Media job dispatched — task_id=%s, job_type=%s, client_id=%s",
        task.task_id, job_type.value, client_id,
    )
    return task.task_id


async def _run_media_job(task: BackgroundMediaTask) -> None:
    """
    Execute the media generation job asynchronously.

    Steps:
      1. Transition to RUNNING, push status update.
      2. Simulate work with asyncio.sleep.
      3. Transition to COMPLETED, push background_update with result.
      4. On any error, transition to FAILED and push error event.
    """
    manager = get_connection_manager()

    # ── RUNNING ───────────────────────────────────────────────────────────
    task = task.transition(TaskStatus.RUNNING)
    seq = manager.next_sequence(task.client_id)
    await manager.send_event(
        task.client_id,
        ChatStreamEvent.status(
            request_id=task.request_id,
            sequence=seq,
            message=f"Media generation started — task_id={task.task_id}",
        ),
    )

    try:
        logger.info(
            "Media job running — task_id=%s, delay=%ds",
            task.task_id, _MOCK_GENERATION_DELAY,
        )
        await asyncio.sleep(_MOCK_GENERATION_DELAY)

        # ── COMPLETED ─────────────────────────────────────────────────────
        mock_url = (
            f"https://cdn.example.com/generated/"
            f"{task.job_type.value}/{task.task_id}.png"
        )
        result_payload = {
            "url": mock_url,
            "job_type": task.job_type.value,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        task = task.transition(TaskStatus.COMPLETED)
        task = task.model_copy(update={"result_payload": result_payload})

        seq = manager.next_sequence(task.client_id)
        await manager.send_event(
            task.client_id,
            ChatStreamEvent.background_update(
                request_id=task.request_id,
                sequence=seq,
                task_id=task.task_id,
                task_status=TaskStatus.COMPLETED,
                result=result_payload,
            ),
        )
        logger.info("Media job completed — task_id=%s, url=%s", task.task_id, mock_url)

    except Exception as exc:
        # ── FAILED ────────────────────────────────────────────────────────
        logger.exception("Media job failed — task_id=%s", task.task_id)
        task = task.transition(TaskStatus.FAILED)
        task = task.model_copy(update={"error_message": str(exc)})

        seq = manager.next_sequence(task.client_id)
        await manager.send_event(
            task.client_id,
            ChatStreamEvent.background_update(
                request_id=task.request_id,
                sequence=seq,
                task_id=task.task_id,
                task_status=TaskStatus.FAILED,
                error=str(exc),
            ),
        )
