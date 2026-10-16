"""Curated master games: data/games/*.pgn with a themes tag and move-by-move comments in the PGN
itself. Loaded once; every game is replayed with python-chess so a broken PGN is dropped, never served."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import chess
import chess.pgn

from ..settings import REPO_ROOT

LOGGER = logging.getLogger("chess.games")
GAMES_DIR = REPO_ROOT / "data" / "games"

THEME_NAMES = {
    "attack": "King attack", "sacrifice": "Sacrifice", "development": "Development and open lines", "defence": "Defence",
    "positional": "Positional play", "prophylaxis": "Prophylaxis", "endgame": "Endgame technique", "pawn-structure": "Pawn structure",
    "exchange-sacrifice": "Exchange sacrifice", "minority-attack": "Minority attack", "iqp": "Isolated queen's pawn",
    "bishop-pair": "Bishop pair", "opposite-bishops": "Opposite-coloured bishops", "queen-sacrifice": "Queen sacrifice",
    "zugzwang": "Zugzwang", "fortress": "Fortress", "opening-trap": "Opening trap", "blockade": "Blockade",
    "initiative": "Initiative", "calculation": "Calculation", "knight-vs-bishop": "Knight against bishop",
    "rook-endgame": "Rook endgame", "pawn-storm": "Pawn storm", "opposite-castling": "Opposite-side castling",
    "classic": "Classic", "world-championship": "World championship", "immortal": "Immortal games",
}


@dataclass
class CuratedGame:
    id: str
    white: str
    black: str
    event: str
    year: str
    result: str
    eco: str
    opening: str
    themes: list[str]
    why: str
    level: int  # recommended band
    plies: list[dict] = field(default_factory=list)  # {ply, san, uci, fen, comment}
    key_moments: list[dict] = field(default_factory=list)  # {ply, note}
    pgn: str = ""

    def summary(self) -> dict:
        return {"id": self.id, "white": self.white, "black": self.black, "event": self.event, "year": self.year, "result": self.result,
                "eco": self.eco, "opening": self.opening, "themes": self.themes, "why": self.why, "level": self.level, "plies": len(self.plies)}

    def detail(self) -> dict:
        return {**self.summary(), "moves": self.plies, "key_moments": self.key_moments, "pgn": self.pgn}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _parse(game: chess.pgn.Game, path: Path) -> CuratedGame:
    h = game.headers
    board = game.board()
    plies: list[dict] = []
    node = game
    while node.variations:
        nxt = node.variations[0]
        san = board.san(nxt.move)
        board.push(nxt.move)
        plies.append({"ply": board.ply(), "san": san, "uci": nxt.move.uci(), "fen": board.fen(), "comment": nxt.comment.strip() or None})
        node = nxt
    if not plies:
        raise ValueError("no moves")
    key = [{"ply": p["ply"], "note": p["comment"]} for p in plies if p["comment"] and (p["comment"].startswith("!") or "key:" in p["comment"].lower())]
    year = h.get("Date", "????")[:4]
    gid = _slug(f"{h.get('White', 'w')}-{h.get('Black', 'b')}-{year}")
    themes = [t.strip() for t in h.get("Themes", "").split(",") if t.strip()]
    return CuratedGame(
        id=gid, white=h.get("White", "?"), black=h.get("Black", "?"), event=h.get("Event", ""), year=year,
        result=h.get("Result", "*"), eco=h.get("ECO", ""), opening=h.get("Opening", ""), themes=themes,
        why=h.get("Why", game.comment.strip()), level=int(h.get("Level", "3")), plies=plies, key_moments=key, pgn=str(game),
    )


@lru_cache(maxsize=1)
def load_games() -> list[CuratedGame]:
    out: list[CuratedGame] = []
    seen: set[str] = set()
    for path in sorted(Path(GAMES_DIR).glob("*.pgn")):
        with path.open(encoding="utf-8", errors="replace") as fh:
            while True:
                try:
                    game = chess.pgn.read_game(fh)
                except Exception:  # boundary: one bad game must not sink the library
                    LOGGER.warning("unreadable game in %s", path.name, exc_info=True)
                    continue
                if game is None:
                    break
                if game.errors:
                    LOGGER.warning("dropped game in %s (%s vs %s): %s", path.name, game.headers.get("White"), game.headers.get("Black"), game.errors[0])
                    continue
                try:
                    g = _parse(game, path)
                except ValueError as exc:
                    LOGGER.warning("dropped game in %s: %s", path.name, exc)
                    continue
                if g.id in seen:
                    g.id = f"{g.id}-{len(seen)}"
                seen.add(g.id)
                out.append(g)
    LOGGER.info("curated games: %d from %s", len(out), GAMES_DIR)
    return out


def find_game(game_id: str) -> CuratedGame | None:
    return next((g for g in load_games() if g.id == game_id), None)
