"""The catalog a plan is built from: the book's families and variation groups, the courses, the
lessons, the puzzle sets, the master games and the endgame positions, each with the keys a goal
can match. Built once from the content loaders; nothing here is invented."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from ..content.endgames import load_endgames
from ..content.games import CuratedGame, load_games
from ..content.lessons import Lesson, load_curriculum
from ..openings.book import Opening, load_book
from ..openings.courses import Course, load_courses
from ..puzzles.store import Puzzle, PuzzleLibrary, load_library

# Trailing words a player drops when naming an opening: "the Sicilian", "the Italian".
_GENERIC_TAIL = ("defense", "opening", "game")
_SPACES = re.compile(r"\s+")


def norm(text: str) -> str:
    """Lowercase, apostrophes gone, hyphens and underscores as spaces, British spelling folded."""
    text = text.lower().replace("'", "").replace("’", "").replace("-", " ").replace("_", " ").replace(":", " ").replace(",", " ")
    text = text.replace("defence", "defense").replace("centre", "center").replace("colour", "color")
    return _SPACES.sub(" ", text).strip()


def family_key(family: str) -> str:
    """The name a player says: "Sicilian Defense" -> "sicilian", "King's Indian Defense" -> "kings indian"."""
    words = norm(family).split()
    while len(words) > 1 and words[-1] in _GENERIC_TAIL:
        words.pop()
    return " ".join(words)


def opening_tag(family: str) -> str:
    """A lichess opening tag prefix for a family: "Sicilian Defense" -> "Sicilian_Defense"."""
    return "_".join(norm(family).title().split())


@lru_cache(maxsize=1)
def _normed_tags(lib: PuzzleLibrary) -> dict[str, tuple[str, ...]]:
    """Puzzle id -> its opening tags normalised, once per loaded library."""
    return {p.id: tuple(norm(t) for t in p.opening_tags) for p in lib.all}


def opening_tag_matches(puzzle: Puzzle, tag_prefix: str) -> bool:
    prefix = norm(tag_prefix)
    return any(t.startswith(prefix) for t in _normed_tags(load_library())[puzzle.id])


def opening_puzzles(tag_prefix: str) -> list[Puzzle]:
    prefix, lib = norm(tag_prefix), load_library()
    tags = _normed_tags(lib)
    return [p for p in lib.all if any(t.startswith(prefix) for t in tags[p.id])]


@dataclass
class Family:
    name: str
    lines: list[Opening]

    @property
    def ecos(self) -> list[str]:
        return sorted({o.eco for o in self.lines})

    @property
    def root(self) -> Opening:
        return min(self.lines, key=lambda o: (o.ply, o.name))

    def groups(self) -> list[Family]:
        """The family's variations as the book names them: "Sicilian Defense: Najdorf Variation" is one group."""
        by_name: dict[str, list[Opening]] = {}
        for o in self.lines:
            head = o.variation.split(",")[0].strip() or self.name
            by_name.setdefault(head, []).append(o)
        return sorted((Family(name, lines) for name, lines in by_name.items()), key=lambda f: (f.root.ply, f.name))


@lru_cache(maxsize=1)
def families() -> dict[str, Family]:
    by_name: dict[str, list[Opening]] = {}
    for o in load_book().all:
        by_name.setdefault(o.family, []).append(o)
    return {name: Family(name, lines) for name, lines in by_name.items()}


@lru_cache(maxsize=None)
def groups_of(family: str) -> list[Family]:
    return families()[family].groups()


def courses_for(name: str, sides: list[str] | tuple[str, ...] = ()) -> list[Course]:
    """Courses on `name` or on a line inside it; when none, the most specific course that contains it.
    Only courses for `sides` when sides are given."""
    cs = [c for c in load_courses().values() if not sides or c.side in sides]
    inside = [c for c in cs if any(p.startswith(name) for p in c.openings)]
    if inside:
        return inside
    above = {c.id: max(len(p) for p in c.openings if name.startswith(p)) for c in cs if any(name.startswith(p) for p in c.openings)}
    return [c for c in cs if c.id in above and above[c.id] == max(above.values())]


def lessons() -> list[Lesson]:
    return [lsn for m in load_curriculum() for lsn in m.lessons]


def lesson_text(lsn: Lesson) -> str:
    """What a lesson is about, in matchable form: its module's title, its title and its objective."""
    module = next(m for m in load_curriculum() if m.id == lsn.module_id)
    return norm(f"{module.title} {lsn.title} {lsn.objective}")


def games_in(ecos: set[str], family_keys: list[str]) -> list[CuratedGame]:
    return [g for g in load_games() if g.eco in ecos or any(k and k in norm(g.opening) for k in family_keys)]


def opening_puzzle_count(family: str) -> int:
    return len(opening_puzzles(opening_tag(family)))


def endgame_theme(key: str) -> dict | None:
    data = load_endgames()
    theme = next((t for t in data["themes"] if t["key"] == key), None)
    if theme is None:
        return None
    return {**theme, "positions": [p for p in data["positions"] if p["theme"] == key]}
