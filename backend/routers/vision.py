"""Board vision trainer scores: best score per mode, kept in the player store."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..storage.db import database

router = APIRouter(prefix="/api/vision", tags=["vision"])
MODES = ("find", "name")


class VisionScore(BaseModel):
    mode: str = Field(pattern="^(find|name)$")
    score: int = Field(ge=0, le=500)
    seconds: int = Field(30, ge=10, le=120)


@router.get("")
async def best() -> dict:
    return {"best": await database.get_player_value("vision_best", {m: 0 for m in MODES})}


@router.post("/score")
async def record(req: VisionScore) -> dict:
    best = await database.get_player_value("vision_best", {m: 0 for m in MODES})
    new_best = req.score > best.get(req.mode, 0)
    if new_best:
        best[req.mode] = req.score
        await database.set_player_value("vision_best", best)
    return {"best": best, "new_best": new_best}
