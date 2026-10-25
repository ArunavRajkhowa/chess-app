"""GET /api/bots: the roster the play page shows."""
from __future__ import annotations

from fastapi import APIRouter

from ..bots.roster import bot_public
from ..bots.specialists import all_bots

router = APIRouter(prefix="/api", tags=["bots"])


@router.get("/bots")
async def list_bots() -> dict:
    """The classic roster, then the generated specialists (tier "specialist", with their specialty)."""
    return {"bots": [bot_public(b) for b in all_bots()]}
