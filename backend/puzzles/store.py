"""The puzzle library: data/puzzles/*.jsonl loaded once, indexed by theme and rating. A puzzle
follows the lichess shape: `fen` is the position before the opponent's move, `moves[0]` is that
move (played for the solver), the rest alternate solver / opponent and end on the solver, all UCI.
Every puzzle is replayed with python-chess at load; a broken one is dropped with a warning."""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import chess

from ..settings import REPO_ROOT

LOGGER = logging.getLogger("chess.puzzles")
PUZZLES_DIR = REPO_ROOT / "data" / "puzzles"

THEME_INFO: dict[str, tuple[str, str]] = {
    "mateIn1": ("Mate in 1", "Deliver checkmate in one move."),
    "mateIn2": ("Mate in 2", "Deliver checkmate in two moves against any defence."),
    "mateIn3": ("Mate in 3", "Deliver checkmate in three moves against any defence."),
    "mateIn4": ("Mate in 4+", "A longer forced mate."),
    "mate": ("Checkmate", "The solution ends in checkmate."),
    "fork": ("Fork", "One piece attacks two or more enemy pieces at once."),
    "pin": ("Pin", "A piece cannot move because a more valuable piece sits behind it."),
    "skewer": ("Skewer", "Attack a valuable piece so that the piece behind it falls."),
    "discoveredAttack": ("Discovered attack", "Moving one piece unmasks an attack from another."),
    "doubleCheck": ("Double check", "Two pieces give check at once; only a king move helps."),
    "backRankMate": ("Back-rank mate", "The king is trapped on its first rank by its own pawns."),
    "smotheredMate": ("Smothered mate", "A knight mates a king boxed in by its own pieces."),
    "hangingPiece": ("Hanging piece", "Win a piece that is attacked and not defended."),
    "sacrifice": ("Sacrifice", "Give up material for a greater gain."),
    "deflection": ("Deflection", "Drag a defender away from its duty."),
    "attraction": ("Attraction", "Lure a piece to a bad square."),
    "clearance": ("Clearance", "Move a piece out of the way to open a line or square."),
    "interference": ("Interference", "Put a piece between two enemy pieces that protect each other."),
    "zugzwang": ("Zugzwang", "Any move worsens the position."),
    "promotion": ("Promotion", "A pawn reaches the last rank."),
    "advancedPawn": ("Advanced pawn", "A pawn deep in enemy territory decides the game."),
    "trappedPiece": ("Trapped piece", "A piece has no safe square."),
    "capturingDefender": ("Capturing the defender", "Remove the piece that holds everything together."),
    "quietMove": ("Quiet move", "A move that is not a check or capture but wins."),
    "defensiveMove": ("Defensive move", "Find the move that saves the position."),
    "exposedKing": ("Exposed king", "Exploit a king with few defenders."),
    "kingsideAttack": ("Kingside attack", "An attack against a king castled short."),
    "queensideAttack": ("Queenside attack", "An attack against a king castled long."),
    "endgame": ("Endgame", "Few pieces remain; precision decides."),
    "middlegame": ("Middlegame", "A full-board fight."),
    "opening": ("Opening", "Punish an early mistake."),
    "pawnEndgame": ("Pawn endgame", "Kings and pawns only."),
    "rookEndgame": ("Rook endgame", "Rooks and pawns."),
    "queenEndgame": ("Queen endgame", "Queens and pawns."),
    "bishopEndgame": ("Bishop endgame", "Bishops and pawns."),
    "knightEndgame": ("Knight endgame", "Knights and pawns."),
    "short": ("Short", "Two moves to solve."),
    "myMistake": ("Your mistake", "A position from your own reviewed game: find the move you missed."),
    "long": ("Long", "A longer combination."),
    "crushing": ("Crushing", "Win a decisive amount of material."),
    "advantage": ("Advantage", "Win a clear advantage."),
    "equality": ("Equality", "Hold a worse position."),
}


@dataclass
class Puzzle:
    id: str
    fen: str
    moves: list[str]
    rating: int
    rd: int
    themes: list[str]
    source: dict = field(default_factory=dict)
    popularity: int = 0

    @property
    def solver_color(self) -> str:
        side = self.fen.split(" ")[1]
        return "black" if side == "w" else "white"

    def public(self) -> dict:
        return {
            "id": self.id, "fen": self.fen, "moves": self.moves, "rating": self.rating, "themes": self.themes,
            "source": self.source, "solver_color": self.solver_color,
        }


class PuzzleLibrary:
    def __init__(self, puzzles: list[Puzzle]):
        self.all = puzzles
        self.by_id = {p.id: p for p in puzzles}
        self.by_theme: dict[str, list[Puzzle]] = {}
        for p in puzzles:
            for t in p.themes:
                self.by_theme.setdefault(t, []).append(p)

    def themes(self) -> list[dict]:
        out = []
        for key, (name, desc) in THEME_INFO.items():
            n = len(self.by_theme.get(key, []))
            if n:
                out.append({"key": key, "name": name, "description": desc, "count": n})
        return out

    def pick(self, *, rating: float, themes: list[str] | None, exclude: set[str], spread: int = 150,
             min_rating: int | None = None, max_rating: int | None = None, rng: random.Random | None = None) -> Puzzle | None:
        rng = rng or random.Random()
        pool = self.all
        if themes:
            pool = [p for p in pool if any(t in p.themes for t in themes)]
        if min_rating is not None or max_rating is not None:
            lo = min_rating if min_rating is not None else 0
            hi = max_rating if max_rating is not None else 9999
            pool = [p for p in pool if lo <= p.rating <= hi]
        else:
            lo, hi = rating - spread, rating + spread
            near = [p for p in pool if lo <= p.rating <= hi]
            pool = near or sorted(pool, key=lambda p: abs(p.rating - rating))[:50]
        fresh = [p for p in pool if p.id not in exclude]
        pool = fresh or pool
        return rng.choice(pool) if pool else None


def _checked(d: dict) -> Puzzle:
    """Builds a puzzle after replaying its line: the opponent's move, then solver / opponent pairs
    that end on the solver's move, every move legal."""
    moves = d["moves"]
    if len(moves) < 2 or len(moves) % 2:
        raise ValueError(f"{len(moves)} moves; expected the opponent's move then pairs ending on the solver's move")
    board = chess.Board(d["fen"])
    for uci in moves:
        mv = chess.Move.from_uci(uci)
        if mv not in board.legal_moves:
            raise ValueError(f"illegal move {uci} in {board.fen()}")
        board.push(mv)
    return Puzzle(
        id=d["id"], fen=d["fen"], moves=moves, rating=int(d.get("rating", 1200)), rd=int(d.get("rd", 80)),
        themes=list(d.get("themes", [])), source=d.get("source", {}), popularity=int(d.get("popularity", 0)),
    )


@lru_cache(maxsize=1)
def load_library() -> PuzzleLibrary:
    puzzles: list[Puzzle] = []
    for path in sorted(Path(PUZZLES_DIR).glob("*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for n, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                pid = "?"
                try:
                    d = json.loads(line)
                    pid = d.get("id", "?")
                    puzzles.append(_checked(d))
                except (ValueError, KeyError, TypeError) as exc:
                    LOGGER.warning("dropped puzzle %s in %s line %d: %s", pid, path.name, n, exc)
    LOGGER.info("puzzle library: %d puzzles from %s", len(puzzles), PUZZLES_DIR)
    return PuzzleLibrary(puzzles)
