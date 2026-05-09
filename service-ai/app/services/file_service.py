"""
app/services/file_service.py  (Phase 6)
────────────────────────────────────────
In-memory document store and PDF extraction pipeline.

DocumentStore  — singleton dict mapping doc_id → extracted text
extract_pdf_text() — async PDF → plain text via pypdf
store_document()   — generate UUID, persist to store, return doc_id
get_document()     — retrieve text by doc_id

Constitution compliance:
  - No MongoDB imports or connections.
  - All storage is in-process memory (intentional for Phase 6).
"""

from __future__ import annotations

import io
from uuid import uuid4

import pypdf

from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentStore:
    """
    In-memory registry mapping doc_id → extracted document text.

    Usage:
        store = get_document_store()
        doc_id = store.store_document(text)
        text   = store.get_document(doc_id)
    """

    def __init__(self) -> None:
        self._docs: dict[str, str] = {}

    def store_document(self, text: str) -> str:
        """Persist extracted text and return a new UUID doc_id."""
        doc_id = str(uuid4())
        self._docs[doc_id] = text
        logger.info("DocumentStore: stored doc_id=%s, chars=%d", doc_id, len(text))
        return doc_id

    def get_document(self, doc_id: str) -> str | None:
        """Return the text for doc_id, or None if not found."""
        return self._docs.get(doc_id)

    @property
    def document_count(self) -> int:
        return len(self._docs)


async def extract_pdf_text(file_bytes: bytes) -> str:
    """
    Extract all text from a PDF given its raw bytes.

    Uses pypdf.PdfReader — runs synchronously but is fast enough for
    typical document sizes. Wrap in run_in_executor if needed for very
    large files in production.

    Returns:
        Concatenated plain text from all pages, separated by newlines.
    """
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    full_text = "\n".join(pages)
    logger.info("extract_pdf_text: extracted %d chars from %d pages", len(full_text), len(reader.pages))
    return full_text


# ── Singleton ─────────────────────────────────────────────────────────────────

_document_store: DocumentStore | None = None


def get_document_store() -> DocumentStore:
    """Return the process-wide DocumentStore singleton."""
    global _document_store
    if _document_store is None:
        _document_store = DocumentStore()
        logger.info("DocumentStore initialised.")
    return _document_store
