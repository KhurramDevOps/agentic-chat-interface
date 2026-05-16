"""
app/api/routes/audio.py
────────────────────────
Voice-to-text transcription endpoint using Groq Whisper.

Endpoint:
  POST /api/v1/audio/transcriptions

Accepts an audio file upload (.m4a, .mp3, .wav, .webm, .ogg) and returns
the transcribed text so the frontend can inject it directly into the chat box.

Uses the Groq API's whisper-large-v3 model via the OpenAI-compatible client.
Falls back gracefully if the provider is not Groq (returns a clear error).
"""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from app.api.deps import verify_api_key
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

_SUPPORTED_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/mp3", "audio/wav",
    "audio/x-wav", "audio/webm", "audio/ogg", "audio/m4a",
    "video/mp4",   # some browsers send m4a as video/mp4
    "application/octet-stream",  # generic fallback
}
_WHISPER_MODEL = "whisper-large-v3"


class TranscriptionResponse(BaseModel):
    text: str
    language: str | None = None
    duration: float | None = None


@router.post(
    "/transcriptions",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe audio to text via Groq Whisper",
    tags=["Audio"],
    dependencies=[Depends(verify_api_key)],
)
async def transcribe_audio(
    request: Request,
    file: UploadFile,
) -> TranscriptionResponse:
    """
    Transcribe an uploaded audio file using Groq's whisper-large-v3 model.

    Accepts: .mp3, .mp4, .m4a, .wav, .webm, .ogg
    Returns: { "text": "transcribed content", "language": "en", "duration": 4.2 }
    """
    settings = get_settings()

    if not settings.groq_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "GROQ_NOT_CONFIGURED",
                    "message": "GROQ_API_KEY is not set. Audio transcription requires Groq.",
                    "request_id": "-",
                }
            },
        )

    # Validate content type (lenient — browsers send inconsistent MIME types)
    content_type = (file.content_type or "").lower()
    filename = file.filename or "audio.mp3"

    logger.info(
        "Audio transcription request — filename=%s, content_type=%s",
        filename, content_type,
    )

    # Read file into memory
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMPTY_FILE", "message": "Uploaded file is empty.", "request_id": "-"}},
        )

    if len(audio_bytes) > 25 * 1024 * 1024:  # Groq's 25 MB limit
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": {"code": "FILE_TOO_LARGE", "message": "Audio file exceeds 25 MB limit.", "request_id": "-"}},
        )

    try:
        from groq import AsyncGroq  # type: ignore[import-untyped]

        client = AsyncGroq(api_key=settings.groq_api_key)

        transcription = await client.audio.transcriptions.create(
            file=(filename, io.BytesIO(audio_bytes)),
            model=_WHISPER_MODEL,
            response_format="verbose_json",
        )

        text = getattr(transcription, "text", "") or ""
        language = getattr(transcription, "language", None)
        duration = getattr(transcription, "duration", None)

        logger.info(
            "Transcription complete — chars=%d, language=%s, duration=%s",
            len(text), language, duration,
        )

        return TranscriptionResponse(text=text, language=language, duration=duration)

    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "GROQ_SDK_MISSING",
                    "message": "groq package is not installed. Run: uv add groq",
                    "request_id": "-",
                }
            },
        )
    except Exception as exc:
        logger.exception("Transcription failed — filename=%s", filename)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "TRANSCRIPTION_ERROR",
                    "message": f"Whisper transcription failed: {exc}",
                    "request_id": "-",
                }
            },
        ) from exc
