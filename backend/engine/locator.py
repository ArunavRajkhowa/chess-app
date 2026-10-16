"""Finds a UCI engine command on this machine. Order: STOCKFISH_PATH, a native `stockfish`
binary on PATH or in the usual install folders, then the WASM Stockfish from the frontend's
node_modules run under `node`. Raises EngineNotFound naming every path tried."""
from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path

from ..settings import REPO_ROOT, settings

_NATIVE_CANDIDATES = (
    "/usr/games/stockfish",
    "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
    "C:/Program Files/Stockfish/stockfish.exe",
)
_WASM_GLOB = str(REPO_ROOT / "frontend" / "node_modules" / "stockfish" / "src" / "stockfish-*-lite-single-*.js")


class EngineNotFound(RuntimeError):
    pass


def find_engine_command() -> list[str]:
    """Returns the argv to start a UCI engine. The first element is the executable."""
    tried: list[str] = []

    if settings.STOCKFISH_PATH:
        p = settings.STOCKFISH_PATH
        if os.path.isfile(p) or shutil.which(p):
            return [p]
        tried.append(f"STOCKFISH_PATH={p}")

    on_path = shutil.which("stockfish")
    if on_path:
        return [on_path]
    tried.append("stockfish on PATH")

    for c in _NATIVE_CANDIDATES:
        if os.path.isfile(c):
            return [c]
        tried.append(c)

    node = shutil.which("node")
    wasm = sorted(glob.glob(_WASM_GLOB))
    if node and wasm:
        return [node, wasm[-1]]
    tried.append(f"node + {_WASM_GLOB} (node={'found' if node else 'missing'}, wasm={len(wasm)} file(s))")

    raise EngineNotFound(
        "No chess engine found. Install Stockfish (https://stockfishchess.org) and set "
        "STOCKFISH_PATH, or run `npm install` in frontend/ so the WASM engine exists. Tried: "
        + "; ".join(tried)
    )


def engine_kind(command: list[str]) -> str:
    return "wasm-node" if Path(command[0]).stem == "node" else "native"
