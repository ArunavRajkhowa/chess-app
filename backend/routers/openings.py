"""Opening explorer API over the lichess chess-openings book: the deepest named position a line
of moves reached, the moves that stay on a named line from there, search by name, and the ECO
families for browsing."""
from __future__ import annotations

import chess
from fastapi import APIRouter, HTTPException, Query

from ..openings.book import load_book

router = APIRouter(prefix="/api/openings", tags=["openings"])


@router.get("/explore")
async def explore(moves: str = "") -> dict:
    """The position after `moves` (UCI from the start, space-separated), the deepest named
    position the moves reached, and the moves that stay on a named line from here."""
    book = load_book()
    board = chess.Board()
    here = None
    for tok in moves.split():
        try:
            mv = chess.Move.from_uci(tok)
        except ValueError:
            raise HTTPException(400, f"bad move {tok!r} at ply {board.ply() + 1}: expected UCI")
        if mv not in board.legal_moves:
            raise HTTPException(400, f"illegal move {tok!r} at ply {board.ply() + 1} in {board.fen()}")
        board.push(mv)
        here = book.lookup(board) or here
    conts = []
    for mv, op, lines in book.book_moves(board):
        conts.append({"san": board.san(mv), "uci": mv.uci(), "eco": op.eco if op else None, "name": op.name if op else None, "lines_below": lines})
    # how many named lines pass through each move's position: a proxy for how main the line is
    conts.sort(key=lambda c: (-c["lines_below"], c["name"] or ""))
    return {
        "fen": board.fen(),
        "opening": {"eco": here.eco, "name": here.name, "pgn": here.pgn, "ply": here.ply} if here else None,
        "continuations": conts,
    }


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
