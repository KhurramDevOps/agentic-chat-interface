"""
app/api/routes/audio.py
────────────────────────
Audio endpoints: speech-to-text (Whisper) and text-to-speech (PlayAI via Groq).

Endpoints:
  POST /api/v1/audio/transcriptions  — audio file → transcribed text
  POST /api/v1/audio/speech          — text → streaming audio (MP3)
"""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import verify_api_key
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

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

    content_type = (file.content_type or "").lower()
    filename = file.filename or "audio.mp3"

    logger.info(
        "Audio transcription request — filename=%s, content_type=%s",
        filename, content_type,
    )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMPTY_FILE", "message": "Uploaded file is empty.", "request_id": "-"}},
        )

    if len(audio_bytes) > 25 * 1024 * 1024:
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

        logger.info("Transcription complete — chars=%d, language=%s", len(text), language)
        return TranscriptionResponse(text=text, language=language, duration=duration)

    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "GROQ_SDK_MISSING",
                               "message": "groq package is not installed. Run: uv add groq", "request_id": "-"}},
        )
    except Exception as exc:
        logger.exception("Transcription failed — filename=%s", filename)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "TRANSCRIPTION_ERROR",
                               "message": f"Whisper transcription failed: {exc}", "request_id": "-"}},
        ) from exc


@router.post(
    "/speech",
    summary="Convert text to speech via gTTS",
    tags=["Audio"],
    dependencies=[Depends(verify_api_key)],
)
async def text_to_speech(
    text: str = Form(..., description="Text to synthesise into speech."),
    lang: str = Form(default="en", description="BCP-47 language code, e.g. 'en', 'ur', 'fr'."),
) -> StreamingResponse:
    """
    Convert text to speech using Google Text-to-Speech (gTTS).

    Returns a streaming MP3 audio response the browser can play directly.

    - text: The text to speak (form field)
    - lang: Language code (default: 'en')
    """
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMPTY_TEXT", "message": "text field cannot be empty.", "request_id": "-"}},
        )

    logger.info("TTS request — chars=%d, lang=%s", len(text), lang)

    try:
        import asyncio  # noqa: PLC0415
        from gtts import gTTS  # type: ignore[import-untyped]

        buf = io.BytesIO()

        # gTTS is synchronous — run in executor to avoid blocking the event loop
        def _synthesise() -> None:
            tts = gTTS(text=text[:4096], lang=lang, slow=False)
            tts.write_to_fp(buf)
            buf.seek(0)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _synthesise)

        audio_bytes = buf.read()
        logger.info("TTS complete — audio_bytes=%d", len(audio_bytes))

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )

    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "GTTS_MISSING",
                               "message": "gtts package is not installed. Run: uv add gtts", "request_id": "-"}},
        )
    except Exception as exc:
        logger.exception("TTS failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "TTS_ERROR",
                               "message": f"Text-to-speech failed: {exc}", "request_id": "-"}},
        ) from exc
