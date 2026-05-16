"""
app/services/file_service.py  (Phase 6 → Phase 8 refactor)
────────────────────────────────────────────────────────────
MongoDB-backed document store and PDF extraction pipeline.

Documents are persisted in chotuu_db.documents so they survive server restarts.
Falls back to an in-memory dict if MongoDB is unavailable (dev convenience).

Collection: chotuu_db.documents
Document shape:
  {
    "doc_id":     "uuid4",
    "filename":   "report.pdf",
    "text":       "extracted plain text...",
    "char_count": 12345,
    "created_at": "2026-..."
  }

Constitution compliance:
  - Reads MONGODB_URI from os.environ directly (not from Settings).
  - No blocking I/O in async paths — motor for all DB calls.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from uuid import uuid4

import pypdf
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.logging import get_logger

logger = get_logger(__name__)

_DB_NAME = "chotuu_db"
_COLLECTION = "documents"

_client: AsyncIOMotorClient | None = None
# In-memory fallback when MongoDB is unreachable
_fallback: dict[str, str] = {}


def _get_collection():
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        logger.info("FileService: motor client connected → %s", uri.split("@")[-1])
    return _client[_DB_NAME][_COLLECTION]


class DocumentStore:
    """
    MongoDB-backed document store.

    store_document() and get_document() are async.
    get_document_sync() is available for sync @function_tool callbacks.
    Falls back to an in-memory dict on MongoDB errors.
    """

    async def store_document(self, text: str, filename: str = "upload.pdf") -> str:
        """Persist extracted text and return a new UUID doc_id."""
        doc_id = str(uuid4())
        doc = {
            "doc_id": doc_id,
            "filename": filename,
            "text": text,
            "char_count": len(text),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            col = _get_collection()
            await col.insert_one(doc)
            logger.info(
                "FileService: stored doc_id=%s, filename=%s, chars=%d",
                doc_id, filename, len(text),
            )
        except Exception as exc:
            logger.warning("FileService: MongoDB store failed, using fallback — %s", exc)
            _fallback[doc_id] = text
        return doc_id

    async def get_document(self, doc_id: str) -> str | None:
        """Return the text for doc_id, or None if not found."""
        if doc_id in _fallback:
            return _fallback[doc_id]
        try:
            col = _get_collection()
            doc = await col.find_one({"doc_id": doc_id}, {"_id": 0, "text": 1})
            if doc:
                return doc.get("text")
            return None
        except Exception as exc:
            logger.warning(
                "FileService: MongoDB get failed — doc_id=%s, error=%s", doc_id, exc
            )
            return None

    def get_document_sync(self, doc_id: str) -> str | None:
        """
        Synchronous document lookup for use inside sync @function_tool callbacks.
        Checks the in-memory fallback first, then uses asyncio to run the coroutine.
        """
        if doc_id in _fallback:
            return _fallback[doc_id]
        try:
            import asyncio  # noqa: PLC0415
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_document(doc_id))
        except Exception as exc:
            logger.warning(
                "FileService: sync get failed — doc_id=%s, error=%s", doc_id, exc
            )
            return None

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document by doc_id. Returns True if deleted."""
        _fallback.pop(doc_id, None)
        try:
            col = _get_collection()
            result = await col.delete_one({"doc_id": doc_id})
            return result.deleted_count > 0
        except Exception as exc:
            logger.warning("FileService: MongoDB delete failed — %s", exc)
            return False

    @property
    def document_count(self) -> int:
        """Returns in-memory fallback count only (sync property)."""
        return len(_fallback)


async def extract_pdf_text(file_bytes: bytes) -> str:
    """
    Extract all text from a PDF given its raw bytes.

    Uses pypdf.PdfReader synchronously — fast enough for typical documents.
    Returns concatenated plain text from all pages.
    """
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n".join(pages)
    logger.info(
        "extract_pdf_text: %d chars from %d pages", len(full_text), len(reader.pages)
    )
    return full_text


# ── Singleton ─────────────────────────────────────────────────────────────────

_document_store: DocumentStore | None = None


def get_document_store() -> DocumentStore:
    """Return the process-wide DocumentStore singleton."""
    global _document_store
    if _document_store is None:
        _document_store = DocumentStore()
        logger.info("DocumentStore initialised (MongoDB-backed).")
    return _document_store
