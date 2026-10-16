"""The curriculum: bands → modules → lessons → sections, loaded from data/lessons/*.json. Every
FEN, solution and PGN is checked with python-chess at load; a bad section is dropped with a
warning naming the file and lesson, never served broken."""
from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import chess
import chess.pgn

from ..settings import REPO_ROOT

LOGGER = logging.getLogger("chess.lessons")
LESSONS_DIR = REPO_ROOT / "data" / "lessons"

BANDS = [
    {"band": 0, "name": "Pawn", "subtitle": "First moves", "rating": "learning the rules"},
    {"band": 1, "name": "Knight", "subtitle": "Novice", "rating": "under 800"},
    {"band": 2, "name": "Bishop", "subtitle": "Beginner", "rating": "800–1100"},
    {"band": 3, "name": "Rook", "subtitle": "Improver", "rating": "1100–1400"},
    {"band": 4, "name": "Queen", "subtitle": "Intermediate", "rating": "1400–1700"},
    {"band": 5, "name": "King", "subtitle": "Club player", "rating": "1700–2000"},
    {"band": 6, "name": "Super King", "subtitle": "Expert", "rating": "2000–2200"},
    {"band": 7, "name": "Candidate", "subtitle": "CM / FM", "rating": "2200–2400"},
    {"band": 8, "name": "Master", "subtitle": "IM / GM track", "rating": "2400+"},
]
STRANDS = ("tactics", "checkmates", "endgames", "openings", "strategy", "calculation", "thinking", "rules", "model games")
SECTION_TYPES = ("text", "position", "challenge", "quiz", "drill", "game")


@dataclass
class Lesson:
    id: str
    module_id: str
    title: str
    objective: str
    minutes: int
    sections: list[dict]
    band: int
    strand: str

    def summary(self) -> dict:
        kinds = [s["type"] for s in self.sections]
        return {
            "id": self.id, "title": self.title, "objective": self.objective, "minutes": self.minutes,
            "challenges": kinds.count("challenge") + kinds.count("drill") + kinds.count("quiz"), "strand": self.strand, "band": self.band,
        }


@dataclass
class Module:
    id: str
    band: int
    title: str
    strand: str
    summary: str
    lessons: list[Lesson] = field(default_factory=list)
    source: str = ""


def _check_fen(fen: str) -> chess.Board:
    board = chess.Board(fen)
    if not board.is_valid():
        raise ValueError(f"illegal position {fen!r}: {board.status()!r}")
    return board


def _validate_section(sec: dict) -> dict:
    t = sec.get("type")
    if t not in SECTION_TYPES:
        raise ValueError(f"unknown section type {t!r}")
    if t == "text":
        if not sec.get("md"):
            raise ValueError("text section without md")
    elif t == "position":
        _check_fen(sec["fen"])
    elif t == "challenge":
        board = _check_fen(sec["fen"])
        sol = sec.get("solution") or []
        if not sol:
            raise ValueError("challenge without solution")
        b = board.copy()
        for uci in sol:
            mv = chess.Move.from_uci(uci)
            if mv not in b.legal_moves:
                raise ValueError(f"solution move {uci} illegal in {b.fen()}")
            b.push(mv)
        sec["solution_san"] = _sans(board, sol)
        if sec.get("accept_any_check") and not any(board.gives_check(m) for m in board.legal_moves):
            raise ValueError("accept_any_check challenge with no checking move")
    elif t == "quiz":
        opts = sec.get("options") or []
        if len(opts) < 2 or not (0 <= int(sec.get("answer", -1)) < len(opts)):
            raise ValueError("quiz needs options and a valid answer index")
        if sec.get("fen"):
            _check_fen(sec["fen"])
    elif t == "drill":
        _check_fen(sec["fen"])
        if sec.get("goal") not in ("mate", "promote", "draw", "survive", "win_material"):
            raise ValueError(f"bad drill goal {sec.get('goal')!r}")
    elif t == "game":
        game = chess.pgn.read_game(io.StringIO(sec["pgn"]))
        if game is None or game.errors or not list(game.mainline_moves()):
            raise ValueError("game section with unreadable PGN")
        board = game.board()
        plies = []
        for mv in game.mainline_moves():
            san = board.san(mv)
            board.push(mv)
            plies.append({"ply": board.ply(), "san": san, "uci": mv.uci(), "fen": board.fen()})
        sec["plies"] = plies
        sec["headers"] = {k: game.headers[k] for k in ("White", "Black", "Event", "Date", "Result") if k in game.headers}
    return sec


def _sans(board: chess.Board, ucis: list[str]) -> list[str]:
    b = board.copy()
    out = []
    for u in ucis:
        mv = chess.Move.from_uci(u)
        out.append(b.san(mv))
        b.push(mv)
    return out


@lru_cache(maxsize=1)
def load_curriculum() -> list[Module]:
    modules: list[Module] = []
    dropped = 0
    for path in sorted(Path(LESSONS_DIR).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for m in data.get("modules", [data] if "lessons" in data else []):
            module = Module(id=m["id"], band=int(m["band"]), title=m["title"], strand=m.get("strand", "tactics"),
                            summary=m.get("summary", ""), source=m.get("source", ""))
            for lsn in m.get("lessons", []):
                sections = []
                for i, sec in enumerate(lsn.get("sections", [])):
                    try:
                        sections.append(_validate_section(dict(sec)))
                    except (ValueError, KeyError) as exc:
                        dropped += 1
                        LOGGER.warning("dropped %s lesson %s section %d: %s", path.name, lsn.get("id"), i, exc)
                if sections:
                    module.lessons.append(Lesson(
                        id=lsn["id"], module_id=module.id, title=lsn["title"], objective=lsn.get("objective", ""),
                        minutes=int(lsn.get("minutes", 10)), sections=sections, band=module.band, strand=module.strand,
                    ))
            if module.lessons:
                modules.append(module)
    modules.sort(key=lambda m: (m.band, m.id))
    LOGGER.info("curriculum: %d modules, %d lessons, %d sections dropped", len(modules), sum(len(m.lessons) for m in modules), dropped)
    return modules


def find_lesson(lesson_id: str) -> Lesson | None:
    for m in load_curriculum():
        for lsn in m.lessons:
            if lsn.id == lesson_id:
                return lsn
    return None
