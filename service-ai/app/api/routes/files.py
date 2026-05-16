"""
app/api/routes/files.py  (Phase 6)
────────────────────────────────────
PDF upload endpoint for the in-memory RAG pipeline.

Endpoint:
  POST /api/v1/files/upload

Accepts a multipart PDF upload, extracts text via pypdf, stores it in
the in-memory DocumentStore, and returns the doc_id for use with the
analyze_document agent tool.

Constitution compliance:
  - No MongoDB imports or connections.
  - All storage is in-process via DocumentStore singleton.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.core.logging import get_logger
from app.services.file_service import extract_pdf_text, get_document_store

logger = get_logger(__name__)
router = APIRouter()

_ALLOWED_CONTENT_TYPES = {"application/pdf"}
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_document(file: UploadFile) -> dict:
    """
    Upload a PDF document for in-memory RAG analysis.

    - Validates the file is a PDF (content-type or .pdf extension).
    - Extracts all text via pypdf.
    - Stores the text in DocumentStore and returns the doc_id.

    The returned doc_id can be passed to the ResearchAgent's
    analyze_document tool to query the document content.
    """
    # ── Validate ──────────────────────────────────────────────────────────
    filename = file.filename or ""
    content_type = file.content_type or ""

    is_pdf = (
        content_type in _ALLOWED_CONTENT_TYPES
        or filename.lower().endswith(".pdf")
    )
    if not is_pdf:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PDF files are supported. Please upload a .pdf file.",
        )

    # ── Read ──────────────────────────────────────────────────────────────
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {_MAX_FILE_SIZE // (1024*1024)} MB.",
        )

    # ── Extract & store ───────────────────────────────────────────────────
    try:
        text = await extract_pdf_text(file_bytes)
    except Exception as exc:
        logger.warning("PDF extraction failed — filename=%s, error=%s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract text from PDF: {exc}",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text could be extracted from this PDF (it may be image-only).",
        )

    store = get_document_store()
    doc_id = await store.store_document(text, filename=filename)

    logger.info("Document uploaded — doc_id=%s, filename=%s", doc_id, filename)

    return {
        "doc_id": doc_id,
        "filename": filename,
        "char_count": len(text),
        "message": "Document processed and persisted successfully.",
    }
