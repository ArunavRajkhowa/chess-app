"""Game Review API: start a review of a stored game or an imported PGN, poll its progress, read
the stored report."""
from __future__ import annotations

import io
import uuid

import chess
import chess.pgn
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..review import jobs
from ..storage import games as store
from ..storage.db import database

router = APIRouter(prefix="/api/review", tags=["review"])

QUICK_DEPTH = 12
FULL_DEPTH = 16
DEEP_DEPTH = 20
DEPTHS = {"quick": QUICK_DEPTH, "full": FULL_DEPTH, "deep": DEEP_DEPTH}


class StartReviewRequest(BaseModel):
    mode: str = Field("full", pattern="^(quick|full|deep)$")


class ImportPgnRequest(BaseModel):
    pgn: str
    mode: str = Field("full", pattern="^(quick|full|deep)$")


def _moves_of(row: dict) -> list[chess.Move]:
    return [chess.Move.from_uci(m["uci"]) for m in row["moves"]]


@router.post("/games/{game_id}")
async def start(game_id: str, req: StartReviewRequest) -> dict:
    row = await store.read_game(game_id)
    if not row:
        raise HTTPException(404, "no such game")
    if not row["moves"]:
        raise HTTPException(400, "the game has no moves")
    job = jobs.start_review(game_id, _moves_of(row), depth=DEPTHS[req.mode], result=row.get("result"), start_fen=row.get("start_fen"))
    return job.public()


@router.post("/import")
async def import_pgn(req: ImportPgnRequest) -> dict:
    game = chess.pgn.read_game(io.StringIO(req.pgn))
    if game is None or game.errors:
        raise HTTPException(400, "could not parse PGN" + (f": {game.errors[0]}" if game and game.errors else ""))
    moves = list(game.mainline_moves())
    if not moves:
        raise HTTPException(400, "the PGN has no moves")
    board = game.board()  # the FEN header's position when the game starts from one
    if type(board) is not chess.Board or not board.is_valid():
        raise HTTPException(400, f"only standard chess from a legal position can be reviewed (Variant {game.headers.get('Variant', 'standard')!r}, FEN {board.fen()!r})")
    start_fen = board.fen() if "FEN" in game.headers else None
    recs = []
    for mv in moves:
        san = board.san(mv)
        board.push(mv)
        recs.append({"ply": board.ply(), "san": san, "uci": mv.uci(), "fen": board.fen(), "by": "player", "source": "import", "eval_cp": None})
    game_id = uuid.uuid4().hex[:12]
    result = game.headers.get("Result") if game.headers.get("Result") in ("1-0", "0-1", "1/2-1/2") else None
    white = game.headers.get("White") if game.headers.get("White", "?") != "?" else "White"
    black = game.headers.get("Black") if game.headers.get("Black", "?") != "?" else "Black"
    await database.execute(
        "INSERT INTO games(id, player_color, bot_id, time_control, status, result, termination, pgn, moves_json, "
        "opening_eco, opening_name, white_name, black_name, source, start_fen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, "white", None, "import", "finished", result, "imported", str(game), __import__("json").dumps(recs),
         game.headers.get("ECO"), game.headers.get("Opening"), white, black, "import", start_fen),
    )
    job = jobs.start_review(game_id, moves, depth=DEPTHS[req.mode], result=result, start_fen=start_fen)
    return {"game_id": game_id, "job": job.public(), "white": white, "black": black}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job.public()


@router.get("/games/{game_id}")
async def get_report(game_id: str) -> dict:
    report = await jobs.stored_report(game_id)
    if report is None:
        raise HTTPException(404, "no review for this game yet")
    row = await store.read_game(game_id)
    return {"game_id": game_id, "report": report, "game": row}
