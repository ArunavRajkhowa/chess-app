"""Owns the engine processes. Two engines run for the life of the app: `play` answers bot moves
and `analysis` answers evaluations and game review. Each engine runs one command at a time,
guarded by its own lock, so a long review never blocks a bot reply."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import chess
import chess.engine

from ..settings import settings
from .locator import engine_kind, find_engine_command

LOGGER = logging.getLogger("chess.engine_pool")

class IllegalPosition(ValueError):
    """A position the engine must never see: Stockfish crashes, and stays dead, on a board
    python-chess calls invalid (a missing king, the side not to move in check)."""


def _require_legal(board: chess.Board) -> None:
    if not board.is_valid():
        raise IllegalPosition(f"illegal position {board.fen()!r}: {board.status()!r}")


# Options python-chess manages itself; passing them in configure() raises.
_MANAGED = {"MultiPV", "Ponder", "UCI_Chess960", "UCI_Variant", "UCI_AnalyseMode", "UCI_Opponent"}


@dataclass
class EngineSlot:
    name: str
    engine: chess.engine.Protocol
    transport: Any
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    applied_options: dict[str, Any] = field(default_factory=dict)

    async def configure(self, options: dict[str, Any]) -> None:
        """Applies only the options that changed since the last call; the engine keeps state."""
        delta = {k: v for k, v in options.items() if self.applied_options.get(k) != v and k not in _MANAGED}
        if delta:
            await self.engine.configure(delta)
            self.applied_options.update(delta)


class EnginePool:
    def __init__(self) -> None:
        self.slots: dict[str, EngineSlot] = {}
        self.command: list[str] = []
        self.kind: str = ""
        self.id_name: str = ""

    async def start(self) -> None:
        self.command = find_engine_command()
        self.kind = engine_kind(self.command)
        for name in ("play", "analysis"):
            transport, engine = await chess.engine.popen_uci(self.command)
            slot = EngineSlot(name=name, engine=engine, transport=transport)
            base = {"Hash": settings.ENGINE_HASH_MB}
            if "Threads" in engine.options and engine.options["Threads"].max >= settings.ENGINE_THREADS:
                base["Threads"] = settings.ENGINE_THREADS
            await slot.configure(base)
            self.slots[name] = slot
        self.id_name = self.slots["analysis"].engine.id.get("name", "unknown")
        LOGGER.info("engine started: %s via %s (%s)", self.id_name, self.kind, " ".join(self.command))

    async def stop(self) -> None:
        for slot in self.slots.values():
            try:
                await slot.engine.quit()
            except (chess.engine.EngineError, OSError, asyncio.TimeoutError):
                LOGGER.warning("engine %s did not quit cleanly", slot.name, exc_info=True)
        self.slots.clear()

    @property
    def ready(self) -> bool:
        return bool(self.slots)

    async def analyse(
        self,
        board: chess.Board,
        *,
        depth: int | None = None,
        time_seconds: float | None = None,
        nodes: int | None = None,
        multipv: int = 1,
        slot: str = "analysis",
    ) -> list[chess.engine.InfoDict]:
        """Full-strength analysis. Returns one InfoDict per principal variation, best first."""
        _require_legal(board)
        s = self.slots[slot]
        limit = chess.engine.Limit(depth=depth, time=time_seconds, nodes=nodes)
        async with s.lock:
            await s.configure({"UCI_LimitStrength": False, "Skill Level": 20})
            infos = await s.engine.analyse(board, limit, multipv=multipv)
        return infos if isinstance(infos, list) else [infos]

    async def play_move(
        self,
        board: chess.Board,
        *,
        options: dict[str, Any],
        depth: int | None = None,
        time_seconds: float | None = None,
        nodes: int | None = None,
        multipv: int = 1,
    ) -> list[chess.engine.InfoDict]:
        """Analysis under bot settings (Skill Level / UCI_Elo). Returns multipv lines the bot
        selector chooses from; the caller decides the move, not the engine's bestmove."""
        _require_legal(board)
        s = self.slots["play"]
        limit = chess.engine.Limit(depth=depth, time=time_seconds, nodes=nodes)
        async with s.lock:
            await s.configure(options)
            infos = await s.engine.analyse(board, limit, multipv=multipv)
        return infos if isinstance(infos, list) else [infos]


pool = EnginePool()
