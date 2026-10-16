"""Every API router is registered here, in one place, so app.py stays a factory."""
from __future__ import annotations

from fastapi import FastAPI

from . import bots, coach, games, health, insights, learn, openings, play, puzzles, review


def register_routers(app: FastAPI) -> None:
    for module in (health, bots, play, review, puzzles, coach, openings, learn, games, insights):
        app.include_router(module.router)
