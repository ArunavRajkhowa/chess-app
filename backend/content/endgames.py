"""The endgame trainer's positions: data/endgames.json, themed drills played against the engine
with a goal. Validated for legality at load; the engine checks of goals live in the tests."""
from __future__ import annotations

import json
import logging
from functools import lru_cache

import chess

from ..settings import REPO_ROOT

LOGGER = logging.getLogger("chess.endgames")
ENDGAMES_FILE = REPO_ROOT / "data" / "endgames.json"
GOALS = ("mate", "promote", "draw", "survive", "win_material")


@lru_cache(maxsize=1)
def load_endgames() -> dict:
    data = json.loads(ENDGAMES_FILE.read_text(encoding="utf-8"))
    positions = []
    for p in data["positions"]:
        try:
            board = chess.Board(p["fen"])
            if not board.is_valid():
                raise ValueError(f"illegal position: {board.status()!r}")
            if p["goal"] not in GOALS:
                raise ValueError(f"bad goal {p['goal']!r}")
        except (ValueError, KeyError) as exc:
            LOGGER.warning("dropped endgame %s: %s", p.get("key"), exc)
            continue
        p["learner_color"] = "white" if board.turn == chess.WHITE else "black"
        positions.append(p)
    LOGGER.info("endgames: %d positions in %d themes", len(positions), len(data["themes"]))
    return {"themes": data["themes"], "positions": positions}
