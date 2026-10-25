"""Where a finding sends the player: every action resolves to an id the loaders know (a lesson, a
puzzle theme, a course line, an endgame drill, a bot, a master game) or it is not offered."""
from __future__ import annotations

from ..bots.roster import BOTS_BY_ID, SPECIALTY_ENDGAME, SPECIALTY_MIDDLEGAME, SPECIALTY_OPENING, Bot
from ..bots.specialists import RATINGS, specialist_for
from ..content.endgames import load_endgames
from ..content.games import THEME_NAMES, load_games
from ..content.lessons import find_lesson, lesson_for_theme, load_curriculum
from ..openings.courses import load_courses
from ..puzzles.store import THEME_INFO
from ..review.phases import ENDGAME, MIDDLEGAME, OPENING

PUZZLE_SPREAD = 150  # the rating window the puzzle picker uses around the player (store.pick's spread)
# Each endgame type: the drill theme in data/endgames.json and the puzzle theme whose lesson teaches it.
ENDGAME_TYPES = {"pawn": ("pawn", "pawnEndgame"), "rook": ("rook", "rookEndgame"), "minor": ("minor", "bishopEndgame"), "queen": ("queen", "queenEndgame")}
# Classic bots whose play trains an area when no specialist covers it, in their own words (roster taglines).
_BOT_FOR = {SPECIALTY_ENDGAME: "grinder", "tactics": "trickster", SPECIALTY_MIDDLEGAME: "ivy", SPECIALTY_OPENING: "luna", "defence": "wall"}
_LESSON_STRAND = {OPENING: "openings", MIDDLEGAME: "strategy", ENDGAME: "endgames", "tactics": "tactics", "thinking": "thinking", "calculation": "calculation"}


def lesson(lesson_id: str) -> dict | None:
    lsn = find_lesson(lesson_id)
    return {"kind": "lesson", "id": lsn.id, "title": lsn.title, "href": f"/learn/{lsn.id}"} if lsn else None


def lesson_for(theme: str) -> dict | None:
    lsn = lesson_for_theme(theme)
    return lesson(lsn.id) if lsn else None


def lesson_in(strand: str, band: int | None) -> dict | None:
    """The highest lesson of a strand at or below the player's band (band unknown: the first one)."""
    fitting = [lsn for m in load_curriculum() for lsn in m.lessons if m.strand == _LESSON_STRAND.get(strand, strand) and (band is None or m.band <= band)]
    if not fitting:
        return None
    pick = fitting[0] if band is None else max(fitting, key=lambda lsn: lsn.band)
    return lesson(pick.id)


def puzzles(theme: str, rating: int | None) -> dict | None:
    if theme not in THEME_INFO:
        return None
    out = {"kind": "puzzles", "id": theme, "title": f"{THEME_INFO[theme][0]} puzzles", "href": f"/puzzles?theme={theme}"}
    if rating is not None:
        out["rating_min"], out["rating_max"] = rating - PUZZLE_SPREAD, rating + PUZZLE_SPREAD
    return out


def course_for(opening_name: str | None, color: str) -> dict | None:
    """The course that covers an opening for the player's colour, and its line when one names it."""
    if not opening_name:
        return None
    for c in load_courses().values():
        if c.side == color and any(opening_name.startswith(p) for p in c.openings):
            line = next((x for x in c.lines if opening_name.startswith(x.opening.name) or x.opening.name.startswith(opening_name)), None)
            out = {"kind": "course", "id": c.id, "title": c.name, "href": f"/openings/courses/{c.id}"}
            if line:
                out["line_id"], out["line"] = line.id, line.name
            return out
    return None


def endgame_drill(kind: str, goal: str | None = None) -> dict | None:
    """A drill of the endgame type, preferring one with the goal (promote, draw, mate, win_material)."""
    theme = ENDGAME_TYPES[kind][0]
    positions = [p for p in load_endgames()["positions"] if p["theme"] == theme]
    if not positions:
        return None
    p = next((x for x in positions if x["goal"] == goal), positions[0])
    return {"kind": "endgame", "id": p["key"], "title": p["title"], "href": f"/endgames?theme={theme}"}


def bot(kind: str, key: str | None, rating: int | None) -> dict | None:
    """The specialist of this kind and key nearest the player's rating, else the classic bot for the area."""
    b: Bot | None = specialist_for(kind, key, rating or RATINGS[1]) if key else None
    b = b or BOTS_BY_ID.get(_BOT_FOR.get(kind, ""))
    return {"kind": "bot", "id": b.id, "title": f"Play {b.name} ({b.elo})", "href": f"/play?bot={b.id}", "reason": b.tagline} if b else None


def band_of(level: dict | None) -> int | None:
    return level["band"] if level else None


def rating_of(level: dict | None) -> int | None:
    return level["rating"] if level else None


def master_game(theme: str, band: int | None) -> dict | None:
    """The master game on a theme closest to the player's band, lower first (it must be readable)."""
    games = [g for g in load_games() if theme in g.themes]
    if not games:
        return None
    g = min(games, key=lambda x: (x.level > (band or 3), abs(x.level - (band or 3)))) if band is not None else games[0]
    return {"kind": "game", "id": g.id, "title": f"{g.white} – {g.black}, {g.year}", "theme": THEME_NAMES.get(theme, theme), "href": f"/games/{g.id}"}
