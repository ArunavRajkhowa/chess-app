"""GET /api/bots: the roster the play page shows."""
from __future__ import annotations

from fastapi import APIRouter

from ..bots.roster import BOTS, bot_public

router = APIRouter(prefix="/api", tags=["bots"])


@router.get("/bots")
async def list_bots() -> dict:
    return {"bots": [bot_public(b) for b in BOTS]}
