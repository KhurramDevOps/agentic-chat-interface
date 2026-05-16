"""
app/api/routes/__init__.py  (T007)
───────────────────────────────────
Central API router. All sub-routers are registered here and
included into the FastAPI app via a single prefix in main.py.

Sub-routers are imported and registered as each phase completes:
  Phase 3  → health
  Phase 4  → chat
  Phase 5  → stream, media
"""

from fastapi import APIRouter

router = APIRouter()

# ── Phase 3: Health (T014 / T015) ────────────────────────────────────────────
from app.api.routes.health import router as health_router

router.include_router(health_router, prefix="/health", tags=["Health"])

# ── Phase 4: Chat (T024) ──────────────────────────────────────────────────────
from app.api.routes.chat import router as chat_router

router.include_router(chat_router, prefix="/chat", tags=["Chat"])

# ── Phase 5: Stream (T032) ────────────────────────────────────────────────────
from app.api.routes.stream import router as stream_router

router.include_router(stream_router, prefix="/stream", tags=["Stream"])

# ── Phase 5: Media (T030) ─────────────────────────────────────────────────────
# from app.api.routes.media import router as media_router
# router.include_router(media_router, prefix="/media", tags=["Media"])

# ── Phase 6: Files / RAG (upload + document store) ───────────────────────────
from app.api.routes.files import router as files_router

router.include_router(files_router, prefix="/files", tags=["Files"])

# ── Phase 7: SSE streaming endpoint ──────────────────────────────────────────
from app.api.routes.sse import router as sse_router

router.include_router(sse_router, prefix="/chat", tags=["Chat"])

# ── Phase 8: Audio transcription + TTS (Groq Whisper / PlayAI) ───────────────
from app.api.routes.audio import router as audio_router

router.include_router(audio_router, prefix="/audio", tags=["Audio"])

# ── Phase 8: Vision (Groq llama-4-scout) ─────────────────────────────────────
from app.api.routes.vision import router as vision_router

router.include_router(vision_router, prefix="/chat", tags=["Chat"])

# ── Phase 8: Users (usage stats) ─────────────────────────────────────────────
from app.api.routes.users import router as users_router, history_router

router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(history_router, prefix="/chat/history", tags=["Chat"])
