"""
app/api/routes/vision.py
─────────────────────────
Image analysis endpoint using Groq vision model.

Endpoint:
  POST /api/v1/chat/vision

Accepts an image file + text prompt, encodes the image as base64,
and sends it to Groq's llama-3.2-11b-vision-preview model.
Returns the text analysis.
"""

from __future__ import annotations

import base64
import io

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from groq import AsyncGroq  # type: ignore[import-untyped]
from pydantic import BaseModel

from app.api.deps import verify_api_key
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
_SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/gif",
    "image/webp", "application/octet-stream",
}


class VisionResponse(BaseModel):
    analysis: str
    model: str


@router.post(
    "/vision",
    response_model=VisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyse an image with a text prompt using Groq vision",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def analyse_image(
    file: UploadFile,
    prompt: str = Form(default="Describe this image in detail."),
) -> VisionResponse:
    """
    Upload an image and ask a question about it.

    - file:   Image file (.jpg, .png, .gif, .webp)
    - prompt: What you want to know about the image (form field)

    Returns the model's text analysis.
    """
    settings = get_settings()

    if not settings.groq_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "GROQ_NOT_CONFIGURED",
                               "message": "GROQ_API_KEY is required for vision.", "request_id": "-"}},
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMPTY_FILE", "message": "Image file is empty.", "request_id": "-"}},
        )

    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": {"code": "FILE_TOO_LARGE", "message": "Image exceeds 20 MB limit.", "request_id": "-"}},
        )

    content_type = (file.content_type or "image/jpeg").lower().split(";")[0].strip()
    if content_type not in _SUPPORTED_IMAGE_TYPES:
        content_type = "image/jpeg"  # safe fallback

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64_image}"

    logger.info(
        "Vision request — filename=%s, size=%d, prompt_len=%d",
        file.filename, len(image_bytes), len(prompt),
    )

    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=1024,
        )

        analysis = response.choices[0].message.content or ""
        logger.info("Vision analysis complete — chars=%d", len(analysis))

        return VisionResponse(analysis=analysis, model=_VISION_MODEL)

    except Exception as exc:
        logger.exception("Vision analysis failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "VISION_ERROR",
                               "message": f"Vision analysis failed: {exc}", "request_id": "-"}},
        ) from exc
