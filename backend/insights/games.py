"""Reviewed bot games as the findings read them: the player's judged moves with the motif of the
engine's move, computed once per review and kept in memory, so a page of findings is one small query."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import chess

from ..bots.roster import find_bot
from ..review import classify as C
from ..storage.db import database
from .motifs import motif_of

PROBLEM = (C.INACCURACY, C.MISTAKE, C.MISS, C.BLUNDER)
ERRORS = (C.MISTAKE, C.MISS, C.BLUNDER)  # "a mistake or worse"
MAX_GAMES = 200
_FACTS: dict[str, Game] = {}
_FACTS_CAP = 2000


@dataclass
class Move:
    """One of the player's judged moves and what the engine wanted instead."""
    ply: int
    move_number: int
    san: str
    uci: str
    fen: str  # before the move
    classification: str
    win_before: float
    win_after: float
    drop: float
    cp_loss: int
    best_san: str
    best_uci: str
    best_line: list[str]
    phase: str
    motif: str | None  # the puzzle theme the engine's move belongs to, when a rule can name it


@dataclass
class Game:
    id: str
    color: str
    outcome: str  # win | draw | loss
    opponent: str
    created_at: str
    termination: str | None
    time_control: str | None
    opening: dict | None  # {eco, name, last_book_ply}
    accuracy: float | None
    acpl: float | None
    estimated_rating: int | None
    counts: dict[str, int]
    phase_accuracy: dict[str, float | None]
    moves: list[Move]  # the player's moves only
    plies: int
    positions: list[str]  # FEN of every position, index = ply
    win_graph: list[float]  # the player's win chance per position
    boundaries: dict[str, int | None]

    def move_at(self, ply: int) -> Move | None:
        return next((m for m in self.moves if m.ply == ply), None)

    @property
    def score(self) -> float:
        return {"win": 1.0, "draw": 0.5, "loss": 0.0}[self.outcome]


def mean(xs: list[float], digits: int = 1) -> float | None:
    """None for an empty list: a stat with no data is absent, never a zero."""
    return round(sum(xs) / len(xs), digits) if xs else None


def fen_key(fen: str) -> str:
    return " ".join(fen.split(" ")[:4])


def record(games: list[Game]) -> dict:
    wins = sum(1 for g in games if g.outcome == "win")
    draws = sum(1 for g in games if g.outcome == "draw")
    return {"games": len(games), "wins": wins, "draws": draws, "losses": len(games) - wins - draws,
            "score": round(100 * sum(g.score for g in games) / len(games)) if games else None}


def example(game: Game, move: Move) -> dict:
    """The evidence for a finding: the player's own position, what was played and what was better."""
    return {
        "game_id": game.id, "ply": move.ply, "move_number": move.move_number, "color": game.color, "opponent": game.opponent,
        "fen": move.fen, "played_san": move.san, "played_uci": move.uci, "best_san": move.best_san, "best_uci": move.best_uci,
        "best_line": move.best_line, "drop": move.drop, "classification": move.classification, "phase": move.phase,
    }


def _mate_for_mover(best_eval_text: str, color: str) -> bool:
    return best_eval_text.startswith("M") if color == "white" else best_eval_text.startswith("-M")


def _move(m: dict, color: str, prev: dict | None) -> Move:
    motif = None
    if m["classification"] not in (C.BOOK, C.FORCED):
        if _mate_for_mover(m["best_eval_text"], color):
            motif = "mate"
        else:
            recapture = chess.Move.from_uci(prev["uci"]).to_square if prev and "x" in prev["san"] else None
            motif = motif_of(chess.Board(m["fen_before"]), chess.Move.from_uci(m["best_move_uci"]), recapture)
    return Move(
        ply=m["ply"], move_number=m["move_number"], san=m["san"], uci=m["uci"], fen=m["fen_before"],
        classification=m["classification"], win_before=m["win_before"], win_after=m["win_after"],
        drop=round(max(0.0, m["win_before"] - m["win_after"]), 1), cp_loss=m["cp_loss"], best_san=m["best_move_san"],
        best_uci=m["best_move_uci"], best_line=m["best_line_san"], phase=m["phase"], motif=motif,
    )


def game_from_row(row: dict) -> Game:
    rep = json.loads(row["report_json"])
    color = row["player_color"]
    side = rep[color]
    won = row["result"] in ("1-0", "0-1") and (row["result"] == "1-0") == (color == "white")
    outcome = "draw" if row["result"] == "1/2-1/2" else ("win" if won else "loss")
    bot = find_bot(row["bot_id"] or "")
    positions = [m["fen_before"] for m in rep["moves"]] + ([rep["moves"][-1]["fen_after"]] if rep["moves"] else [])
    graph = rep["eval_graph"] if color == "white" else [round(100.0 - w, 1) for w in rep["eval_graph"]]
    return Game(
        id=row["game_id"], color=color, outcome=outcome, opponent=bot.name if bot else "an opponent", created_at=row["created_at"],
        termination=row["termination"], time_control=row["time_control"], opening=rep["opening"], accuracy=side["accuracy"], acpl=side["acpl"],
        estimated_rating=side["estimated_rating"], counts=side["counts"], phase_accuracy=side["phase_accuracy"],
        moves=[_move(m, color, rep["moves"][i - 1] if i else None) for i, m in enumerate(rep["moves"]) if m["color"] == color], plies=len(rep["moves"]),
        positions=positions, win_graph=graph, boundaries=rep["phase_boundaries"],
    )


async def load_games(player: str) -> list[Game]:
    """The player's reviewed bot games, oldest first; a game's facts are computed once per review."""
    heads = await database.fetch_all(
        "SELECT r.game_id, r.created_at AS reviewed_at FROM reviews r JOIN games g ON g.id = r.game_id "
        "WHERE g.player_id = ? AND g.source = 'bot' ORDER BY g.created_at DESC, r.created_at DESC LIMIT ?",
        (player, MAX_GAMES),
    )
    keys = {h["game_id"]: f"{h['game_id']}:{h['reviewed_at']}" for h in heads}
    got = {gid: _FACTS[key] for gid, key in keys.items() if key in _FACTS}  # local: another request may clear _FACTS mid-build
    missing = [gid for gid in keys if gid not in got]
    for i in range(0, len(missing), 50):
        chunk = missing[i : i + 50]
        rows = await database.fetch_all(
            "SELECT r.game_id, r.report_json, g.player_color, g.result, g.termination, g.bot_id, g.created_at, g.time_control "
            f"FROM reviews r JOIN games g ON g.id = r.game_id WHERE r.game_id IN ({','.join('?' * len(chunk))})",
            tuple(chunk),
        )
        built = await asyncio.to_thread(list, map(game_from_row, rows))
        if len(_FACTS) + len(built) > _FACTS_CAP:
            _FACTS.clear()
        for g in built:
            got[g.id] = _FACTS[keys[g.id]] = g
    games = [got[h["game_id"]] for h in heads]
    games.reverse()
    return games
