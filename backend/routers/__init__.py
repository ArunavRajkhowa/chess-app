"""Every API router is registered here, in one place, so app.py stays a factory."""
from __future__ import annotations

from fastapi import FastAPI

from . import awards, bots, coach, endgames, games, health, insights, learn, openings, play, puzzles, review, vision


def register_routers(app: FastAPI) -> None:
    for module in (health, bots, play, review, puzzles, coach, openings, learn, games, insights, endgames, vision, awards):
        app.include_router(module.router)
