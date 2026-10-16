"""The opening book: the lichess chess-openings tables (data/openings/*.tsv, CC0). Loaded once
into a map from position key (EPD without move counters) to the deepest named line reaching
it, so a game's opening is the last named position it passed through."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess
import chess.pgn

from ..settings import REPO_ROOT

LOGGER = logging.getLogger("chess.openings")
OPENINGS_DIR = REPO_ROOT / "data" / "openings"


@dataclass(frozen=True)
class Opening:
    eco: str
    name: str
    pgn: str
    ply: int

    @property
    def family(self) -> str:
        return self.name.split(":")[0].strip()

    @property
    def variation(self) -> str:
        return self.name.split(":", 1)[1].strip() if ":" in self.name else ""


def _position_key(board: chess.Board) -> str:
    return " ".join(board.fen().split(" ")[:4])


class OpeningBook:
    def __init__(self, by_key: dict[str, Opening], all_openings: list[Opening]):
        self.by_key = by_key
        self.all = all_openings
        self.book_keys = set(by_key)

    def lookup(self, board: chess.Board) -> Opening | None:
        return self.by_key.get(_position_key(board))

    def is_book_position(self, board: chess.Board) -> bool:
        return _position_key(board) in self.book_keys

    def classify_game(self, moves: list[chess.Move]) -> tuple[Opening | None, int]:
        """Deepest named opening along the game and the ply at which the game left the book."""
        board = chess.Board()
        best: Opening | None = None
        last_book_ply = 0
        for ply, mv in enumerate(moves, start=1):
            board.push(mv)
            op = self.by_key.get(_position_key(board))
            if op is not None:
                best = op
                last_book_ply = ply
            elif ply - last_book_ply > 6:
                break
        return best, last_book_ply

    def search(self, query: str, limit: int = 30) -> list[Opening]:
        q = query.lower().strip()
        if not q:
            return []
        hits = [o for o in self.all if q in o.name.lower() or q == o.eco.lower()]
        hits.sort(key=lambda o: (o.ply, o.name))
        return hits[:limit]

    def continuations(self, board: chess.Board) -> list[tuple[chess.Move, Opening]]:
        """Named openings one move away from this position."""
        out: list[tuple[chess.Move, Opening]] = []
        for mv in board.legal_moves:
            board.push(mv)
            op = self.by_key.get(_position_key(board))
            board.pop()
            if op is not None:
                out.append((mv, op))
        out.sort(key=lambda t: t[1].name)
        return out


def _parse_pgn_moves(pgn: str) -> list[chess.Move] | None:
    board = chess.Board()
    moves: list[chess.Move] = []
    for token in pgn.split():
        if token[0].isdigit():
            continue
        try:
            mv = board.parse_san(token)
        except ValueError:
            return None
        board.push(mv)
        moves.append(mv)
    return moves


@lru_cache(maxsize=1)
def load_book() -> OpeningBook:
    by_key: dict[str, Opening] = {}
    all_openings: list[Opening] = []
    files = sorted(Path(OPENINGS_DIR).glob("*.tsv"))
    bad = 0
    for path in files:
        with path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                moves = _parse_pgn_moves(row["pgn"])
                if moves is None:
                    bad += 1
                    continue
                board = chess.Board()
                for mv in moves:
                    board.push(mv)
                op = Opening(eco=row["eco"], name=row["name"], pgn=row["pgn"], ply=len(moves))
                all_openings.append(op)
                by_key[_position_key(board)] = op
    LOGGER.info("opening book: %d lines from %d files (%d unparsable)", len(all_openings), len(files), bad)
    return OpeningBook(by_key, all_openings)
