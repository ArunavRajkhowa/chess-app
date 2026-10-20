"""Narration API: one sentence in, one MP3 out (cached). 204 means "no audio: let the browser speak"."""
from __future__ import annotations

from fastapi import APIRouter, Query, Response

from ..narration import MAX_TEXT, synthesize
from ..settings import settings

router = APIRouter(prefix="/api/narration", tags=["narration"])


@router.get("")
async def narration(text: str = Query(min_length=1, max_length=MAX_TEXT)) -> Response:
    data = await synthesize(text)
    if data is None:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    return Response(content=data, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/voice")
async def voice() -> dict:
    return {"tts": settings.NARRATION_TTS, "voice": settings.NARRATION_VOICE}
