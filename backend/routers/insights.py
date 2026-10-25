"""Insights API: what the reviewed games say about the player. Everything comes from stored reviews
and puzzle attempts (backend/insights/); a stat with no data is null, never a made-up zero."""
from __future__ import annotations

from fastapi import APIRouter

from ..insights.build import build
from .account import Player

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/me")
async def me(player: Player) -> dict:
    return await build(player)
