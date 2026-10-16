"""Opening explorer API over the lichess chess-openings book: what this position is called, the
named continuations from it, search by name, and the ECO families for browsing."""
from __future__ import annotations

from collections import defaultdict

import chess
from fastapi import APIRouter, HTTPException, Query

from ..openings.book import load_book

router = APIRouter(prefix="/api/openings", tags=["openings"])


@router.get("/explore")
async def explore(fen: str = Query(chess.STARTING_FEN)) -> dict:
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(400, f"bad FEN {fen!r}")
    book = load_book()
    here = book.lookup(board)
    conts = []
    for mv, op in book.continuations(board):
        conts.append({"san": board.san(mv), "uci": mv.uci(), "eco": op.eco, "name": op.name, "ply": op.ply})
    # how many deeper named lines pass through each continuation: a proxy for how main the line is
    counts: dict[str, int] = defaultdict(int)
    for o in book.all:
        counts[o.pgn] = 0
    prefix = here.pgn if here else ""
    for c in conts:
        line_prefix = (prefix + " " if prefix else "") 
        n = sum(1 for o in book.all if o.pgn.startswith(line_prefix) and o.ply > (here.ply if here else 0) and _first_move_after(o.pgn, here.ply if here else 0) == c["san"])
        c["lines_below"] = n
    conts.sort(key=lambda c: (-c["lines_below"], c["name"]))
    return {
        "fen": board.fen(),
        "opening": {"eco": here.eco, "name": here.name, "pgn": here.pgn, "ply": here.ply} if here else None,
        "continuations": conts,
    }


def _first_move_after(pgn: str, ply: int) -> str | None:
    moves = [t for t in pgn.split() if not t[0].isdigit()]
    return moves[ply] if len(moves) > ply else None


@router.get("/search")
async def search(q: str = Query(min_length=1), limit: int = 40) -> dict:
    book = load_book()
    return {"results": [{"eco": o.eco, "name": o.name, "pgn": o.pgn, "ply": o.ply} for o in book.search(q, limit)]}


@router.get("/families")
async def families() -> dict:
    """Top-level opening names with their ECO range and line counts, for the browse page."""
    book = load_book()
    fam: dict[str, dict] = {}
    for o in book.all:
        f = fam.setdefault(o.family, {"name": o.family, "ecos": set(), "lines": 0, "first_pgn": o.pgn, "min_ply": o.ply})
        f["ecos"].add(o.eco)
        f["lines"] += 1
        if o.ply < f["min_ply"]:
            f["min_ply"], f["first_pgn"] = o.ply, o.pgn
    out = []
    for f in fam.values():
        ecos = sorted(f["ecos"])
        out.append({"name": f["name"], "eco_from": ecos[0], "eco_to": ecos[-1], "lines": f["lines"], "pgn": f["first_pgn"]})
    out.sort(key=lambda f: (-f["lines"], f["name"]))
    return {"families": out}


@router.get("/line")
async def line(pgn: str) -> dict:
    """Plays a book line and returns every position along it, for stepping through on the board."""
    board = chess.Board()
    steps = [{"ply": 0, "fen": board.fen(), "san": None}]
    for tok in pgn.split():
        if tok[0].isdigit():
            continue
        try:
            mv = board.parse_san(tok)
        except ValueError:
            raise HTTPException(400, f"bad move {tok!r} in line")
        board.push(mv)
        steps.append({"ply": board.ply(), "fen": board.fen(), "san": tok, "uci": mv.uci()})
    op = load_book().lookup(board)
    return {"steps": steps, "opening": {"eco": op.eco, "name": op.name} if op else None}
