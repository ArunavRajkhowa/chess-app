"""Opening courses: data/openings/courses/*.json, one course per file. Every line and trap is replayed
with python-chess and named by the lichess book at load; a line that is illegal, or that the book
names as another opening, is dropped with a warning naming the file and the line id."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess

from ..content.games import CuratedGame, load_games
from .book import OPENINGS_DIR, Opening, _parse_pgn_moves, load_book

LOGGER = logging.getLogger("chess.courses")
COURSES_DIR = OPENINGS_DIR / "courses"
SIDES = ("white", "black")
_LABEL = re.compile(r"^(\d+)\.(\.\.)?\s*(\S+)$")  # "4.c3" is White's 4th move, "4...Nf6" Black's


@dataclass
class CourseLine:
    """A main line or a trap: its moves replayed, with the book's name for its last named position."""
    id: str
    name: str
    pgn: str
    opening: Opening
    plies: list[dict]  # {ply, san, uci, fen, comment}
    mistake_ply: int | None = None  # traps only: the ply of the move that loses
    punishment: str = ""  # traps only

    def public(self) -> dict:
        out = {"id": self.id, "name": self.name, "pgn": self.pgn, "opening": {"eco": self.opening.eco, "name": self.opening.name}, "moves": self.plies}
        if self.mistake_ply is not None:
            out["mistake_ply"] = self.mistake_ply
            out["mistake_by"] = "white" if self.mistake_ply % 2 else "black"
            out["punishment"] = self.punishment
        return out


@dataclass
class Course:
    id: str
    name: str
    side: str
    openings: list[str]  # lichess name prefixes the lines must reach
    summary: str
    ideas: dict[str, list[str]]
    structures: list[dict]
    pieces: dict[str, list[str]]
    lines: list[CourseLine]
    traps: list[CourseLine]
    model_games: list[CuratedGame]

    @property
    def ecos(self) -> list[str]:
        return sorted({x.opening.eco for x in self.lines + self.traps})

    def summary_dict(self) -> dict:
        ecos = self.ecos
        return {"id": self.id, "name": self.name, "side": self.side, "eco_from": ecos[0] if ecos else None, "eco_to": ecos[-1] if ecos else None,
                "summary": self.summary, "lines": len(self.lines), "traps": len(self.traps), "model_games": len(self.model_games)}

    def detail(self) -> dict:
        return {**self.summary_dict(), "openings": self.openings, "ideas": self.ideas, "structures": self.structures, "pieces": self.pieces,
                "lines": [x.public() for x in self.lines], "traps": [x.public() for x in self.traps],
                "model_games": [g.summary() for g in self.model_games]}

    def line(self, line_id: str) -> CourseLine | None:
        return next((x for x in self.lines if x.id == line_id), None)


def _label_ply(label: str) -> tuple[int, str]:
    m = _LABEL.match(label.strip())
    if not m:
        raise ValueError(f"move label {label!r}: expected '4.c3' or '4...Nf6'")
    return 2 * int(m.group(1)) - (0 if m.group(2) else 1), m.group(3)


def _ply_of(label: str, plies: list[dict]) -> int:
    """The ply a label names; raises when the line has another move there."""
    ply, san = _label_ply(label)
    if not 1 <= ply <= len(plies):
        raise ValueError(f"move label {label!r}: the line has {len(plies)} plies")
    if plies[ply - 1]["san"].rstrip("+#") != san.rstrip("+#!?"):
        raise ValueError(f"move label {label!r}: the line plays {plies[ply - 1]['san']} there")
    return ply


def _text(raw: dict, key: str) -> str:
    v = raw.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{key!r} must be non-empty text, got {v!r}")
    return v.strip()


def _texts_by_side(raw: dict, key: str) -> dict[str, list[str]]:
    v = raw.get(key)
    if not isinstance(v, dict) or set(v) != set(SIDES) or not all(isinstance(v[s], list) and v[s] and all(isinstance(t, str) and t.strip() for t in v[s]) for s in SIDES):
        raise ValueError(f"{key!r} must map 'white' and 'black' to lists of text, got {v!r}")
    return {s: [t.strip() for t in v[s]] for s in SIDES}


def _line(raw: dict, openings: list[str], *, trap: bool) -> CourseLine:
    lid, name, pgn = _text(raw, "id"), _text(raw, "name"), _text(raw, "moves")
    moves = _parse_pgn_moves(pgn)
    if not moves:
        raise ValueError(f"moves {pgn!r} do not replay from the start position")
    board = chess.Board()
    plies: list[dict] = []
    for mv in moves:
        san = board.san(mv)
        board.push(mv)
        plies.append({"ply": board.ply(), "san": san, "uci": mv.uci(), "fen": board.fen(), "comment": None})
    notes = raw.get("notes", {})
    if not isinstance(notes, dict):
        raise ValueError(f"notes must map move labels to text, got {notes!r}")
    for label, note in notes.items():
        if not isinstance(note, str) or not note.strip():
            raise ValueError(f"note {label!r} is empty")
        plies[_ply_of(label, plies) - 1]["comment"] = note.strip()
    op, _ = load_book().classify_game(moves)
    if op is None or not any(op.name.startswith(p) for p in openings):
        raise ValueError(f"the book names the line {op.name if op else None!r}, not one of {openings}")
    if not trap:
        return CourseLine(lid, name, pgn, op, plies)
    return CourseLine(lid, name, pgn, op, plies, mistake_ply=_ply_of(_text(raw, "mistake"), plies), punishment=_text(raw, "punishment"))


def _named_lines(raws: list, openings: list[str], path: Path, *, trap: bool) -> list[CourseLine]:
    out: list[CourseLine] = []
    for raw in raws:
        try:
            x = _line(raw, openings, trap=trap)
        except ValueError as exc:
            LOGGER.warning("dropped %s %s in %s: %s", "trap" if trap else "line", raw.get("id"), path.name, exc)
            continue
        if any(y.id == x.id for y in out):
            LOGGER.warning("dropped %s %s in %s: duplicate id", "trap" if trap else "line", x.id, path.name)
            continue
        out.append(x)
    return out


def _game_openings() -> list[tuple[CuratedGame, Opening | None]]:
    book = load_book()
    return [(g, book.classify_game([chess.Move.from_uci(p["uci"]) for p in g.plies])[0]) for g in load_games()]


def parse_course(path: Path, games: list[tuple[CuratedGame, Opening | None]]) -> Course:
    """One course file, its lines and traps checked; raises ValueError on a broken course."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    cid = _text(raw, "id")
    if cid != path.stem:
        raise ValueError(f"id {cid!r} must equal the file name {path.stem!r}")
    side = _text(raw, "side")
    if side not in SIDES:
        raise ValueError(f"side {side!r}: expected one of {SIDES}")
    openings = raw.get("openings")
    if not isinstance(openings, list) or not openings or not all(isinstance(p, str) and p for p in openings):
        raise ValueError(f"openings must be a list of lichess name prefixes, got {openings!r}")
    structures = raw.get("structures")
    if not isinstance(structures, list) or not structures or not all(isinstance(s, dict) and _text(s, "name") and _text(s, "text") for s in structures):
        raise ValueError(f"structures must be a list of {{name, text}}, got {structures!r}")
    for key in ("lines", "traps"):
        if not isinstance(raw.get(key), list):
            raise ValueError(f"{key!r} must be a list")
    return Course(
        id=cid, name=_text(raw, "name"), side=side, openings=openings, summary=_text(raw, "summary"),
        ideas=_texts_by_side(raw, "ideas"), structures=[{"name": s["name"].strip(), "text": s["text"].strip()} for s in structures],
        pieces=_texts_by_side(raw, "pieces"),
        lines=_named_lines(raw["lines"], openings, path, trap=False), traps=_named_lines(raw["traps"], openings, path, trap=True),
        model_games=[g for g, op in games if op is not None and any(op.name.startswith(p) for p in openings)],
    )


@lru_cache(maxsize=1)
def load_courses() -> dict[str, Course]:
    games = _game_openings()
    out: dict[str, Course] = {}
    for path in sorted(COURSES_DIR.glob("*.json")):
        try:
            c = parse_course(path, games)
        except (ValueError, json.JSONDecodeError) as exc:
            LOGGER.warning("dropped course %s: %s", path.name, exc)
            continue
        out[c.id] = c
    LOGGER.info("opening courses: %d from %s", len(out), COURSES_DIR)
    return out
