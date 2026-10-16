"""Every API router is registered here, in one place, so app.py stays a factory."""
from __future__ import annotations

from fastapi import FastAPI

from . import bots, health, play


def register_routers(app: FastAPI) -> None:
    for module in (health, bots, play):
        app.include_router(module.router)
