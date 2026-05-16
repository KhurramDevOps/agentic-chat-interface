"""
app/workers/media_worker.py  (T029 / T033)
───────────────────────────────────────────
Background worker for long-running media generation jobs.

Flow:
  1. MediaAgent calls dispatch_media_job() — returns immediately with task_id.
  2. dispatch_media_job() schedules _run_media_job() as an asyncio Task.
  3. _run_media_job() polls the Pollinations URL until it returns HTTP 200
     with an image content-type, then pushes a background_update event.

Constitution compliance:
  - No MongoDB imports or connections.
  - All I/O is async (httpx.AsyncClient).
  - ConnectionManager send errors are isolated; worker never crashes.
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger
from app.schemas.streaming import (
    BackgroundMediaTask,
    ChatStreamEvent,
    JobType,
    TaskStatus,
)
from app.services.streaming_service import get_connection_manager

logger = get_logger(__name__)

# Polling config
_POLL_INTERVAL_SECONDS = 2
_POLL_MAX_ATTEMPTS = 30          # 30 × 2s = 60s max wait
_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Reference to the main FastAPI event loop — set once at app startup via
# set_main_event_loop(). Allows sync function_tools running in thread
# executors to safely schedule coroutines back onto the main loop.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store the main event loop. Call this once from the FastAPI lifespan."""
    global _main_loop
    _main_loop = loop
    logger.info("media_worker: main event loop registered.")


def dispatch_media_job(
    client_id: str,
    request_id: str,
    job_type: JobType,
    input_payload: dict,
) -> str:
    """
    Schedule a background media generation job and return the task_id immediately.

    Safe to call from both async contexts and sync function_tools running in
    thread executors (how the openai-agents SDK invokes sync tools).

    Strategy:
      - If called from an async context (running loop in current thread),
        use call_soon_threadsafe to create a Task on that loop.
      - If called from a thread executor (no running loop), use
        run_coroutine_threadsafe against the stored main loop.

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

    try:
        # Called from an async context — schedule directly on the running loop.
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(
            lambda: loop.create_task(
                _run_media_job(task),
                name=f"media-job-{task.task_id}",
            )
        )
    except RuntimeError:
        # Called from a thread executor — use the stored main loop reference.
        if _main_loop is not None and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(_run_media_job(task), _main_loop)
        else:
            logger.warning(
                "dispatch_media_job: no event loop available — "
                "task_id=%s will not execute.", task.task_id
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
      2. Build the Pollinations URL from the prompt.
      3. Poll the URL every _POLL_INTERVAL_SECONDS until it returns HTTP 200
         with an image content-type (max _POLL_MAX_ATTEMPTS attempts).
      4. Transition to COMPLETED and push background_update with the URL.
      5. On timeout or any error, transition to FAILED and push error event.
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
        prompt = task.input_payload.get("prompt", "a beautiful abstract image")
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1024&height=1024&nologo=true"
        )

        logger.info(
            "Media job polling — task_id=%s, url=%s",
            task.task_id, image_url,
        )

        # ── Poll until image is ready ─────────────────────────────────────
        verified = False
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for attempt in range(1, _POLL_MAX_ATTEMPTS + 1):
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                try:
                    resp = await client.get(image_url)
                    content_type = resp.headers.get("content-type", "")
                    ct_base = content_type.split(";")[0].strip().lower()

                    logger.debug(
                        "Poll attempt %d/%d — status=%d, content-type=%s",
                        attempt, _POLL_MAX_ATTEMPTS, resp.status_code, ct_base,
                    )

                    if resp.status_code == 200 and ct_base in _IMAGE_CONTENT_TYPES:
                        verified = True
                        break
                except httpx.RequestError as exc:
                    logger.warning(
                        "Poll attempt %d failed — task_id=%s, error=%s",
                        attempt, task.task_id, exc,
                    )

        if not verified:
            raise TimeoutError(
                f"Image not ready after {_POLL_MAX_ATTEMPTS * _POLL_INTERVAL_SECONDS}s — "
                f"url={image_url}"
            )

        # ── COMPLETED ─────────────────────────────────────────────────────
        result_payload = {
            "url": image_url,
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
        logger.info("Media job completed — task_id=%s, url=%s", task.task_id, image_url)

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
