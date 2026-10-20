"""Every API router is registered here, in one place, so app.py stays a factory."""
from __future__ import annotations

from fastapi import FastAPI

from . import account, awards, bots, coach, endgames, events, games, health, insights, learn, narration, openings, play, puzzles, review, study, vision


def register_routers(app: FastAPI) -> None:
    for module in (health, account, events, bots, play, review, puzzles, coach, openings, learn, games, insights, endgames, vision, awards, study, narration):
        app.include_router(module.router)
