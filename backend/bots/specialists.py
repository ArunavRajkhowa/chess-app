"""Specialist bots built from the content: one per opening course, middlegame theme and endgame
theme, at four ratings. Depth and temperature come from STRENGTH_OVERRIDES at that rating, else from
the classic bot nearest it."""
from __future__ import annotations

import logging
from dataclasses import replace
from functools import lru_cache

import chess

from .roster import (BOTS, SPECIALTY_ENDGAME, SPECIALTY_MIDDLEGAME, SPECIALTY_OPENING, TIER_SPECIAL, TIER_SPECIALIST, Bot,
                     Personality, Specialty, _bot)

LOGGER = logging.getLogger("chess.bots")
RATINGS = (1000, 1400, 1800, 2200)
# rating -> (depth, temperature_cp) replacing the nearest classic bot's; measured in data/bot_calibration.json:
# with Mei's depth 4 / 55 cp the 1400 middlegame specialists scored 12/12 against Stockfish at UCI_Elo 1400;
# with Nova's depth 2 / 100 cp opening-london-1000 scored 6/10 against UCI_Elo 1320, level with the 1400s
STRENGTH_OVERRIDES = {1000: (2, 150), 1400: (3, 70)}
OPENING_BOOK_PLIES = 20  # an opening specialist follows the book twice as long as a classic bot
OPENING_FAVOURITE_MAX_LOSS_CP = 100  # and accepts a book move that costs this much against its own best line
MIDDLEGAME_START_PLIES = range(24, 31)  # move 12 to 15: the opening is over, the fight is not decided
MIDDLEGAME_MIN_POSITIONS = 3  # below this the theme's filter is too strict and every themed game's position is used
# Middlegame themes from the master games' Themes headers: key -> (name, game themes, avatar).
MIDDLEGAME_THEMES = {
    "attack": ("King attack", ("attack", "pawn-storm", "opposite-castling", "kingsideAttack"), "⚔️"),
    "positional": ("Positional play", ("positional", "prophylaxis", "pawn-structure", "blockade", "minority-attack", "iqp"), "🏰"),
}
AVATARS = {SPECIALTY_OPENING: "📖", SPECIALTY_MIDDLEGAME: "🧭", SPECIALTY_ENDGAME: "♜"}
GREETINGS = {
    SPECIALTY_OPENING: "I know this opening's book lines. Turn on Guide me and I will say where you leave them.",
    SPECIALTY_MIDDLEGAME: "We start in the middlegame. Turn on Guide me and I will name the imbalance that matters.",
    SPECIALTY_ENDGAME: "We start from a known endgame position. Turn on Guide me for the verdict and the rule.",
}


def _strength(elo: int) -> Bot:
    """The classic bot nearest this rating: its depth, temperature and candidate count are reused."""
    return min((b for b in BOTS if b.tier != TIER_SPECIAL), key=lambda b: abs(b.elo - elo))


def _specialist(spec: Specialty, elo: int, *, tagline: str, description: str, personality: Personality | None = None,
                book_plies: int | None = None, avatar: str | None = None) -> Bot:
    base = _strength(elo)
    depth, temp = STRENGTH_OVERRIDES.get(elo, (base.search.depth, base.selection.temperature_cp))
    bot = _bot(f"{spec.kind}-{spec.key}-{elo}", spec.name, elo, TIER_SPECIALIST, tagline, avatar or AVATARS[spec.kind],
               depth, temp, multipv=base.search.multipv,
               random_move=base.selection.random_move_prob, personality=personality, description=description,
               greeting=GREETINGS[spec.kind])
    if book_plies is not None:
        bot = replace(bot, selection=replace(bot.selection, book_plies=book_plies))
    return replace(bot, specialty=spec)


def _opposite_wings(board: chess.Board) -> bool:
    wk, bk = board.king(chess.WHITE), board.king(chess.BLACK)
    if wk is None or bk is None:
        return False
    files = sorted((chess.square_file(wk), chess.square_file(bk)))
    return files[0] <= 2 and files[1] >= 5


def _middlegame_fens(theme_key: str) -> tuple[str, ...]:
    """Master-game positions after move 12 to 15 for a theme. The king-attack theme keeps only
    positions with the kings on opposite wings; a theme with too few such positions takes every one."""
    from ..content.games import load_games

    _, themes, _ = MIDDLEGAME_THEMES[theme_key]
    strict: list[str] = []
    loose: list[str] = []
    for g in load_games():
        if not set(g.themes) & set(themes):
            continue
        window = [p for p in g.plies if p["ply"] in MIDDLEGAME_START_PLIES]
        if not window:
            continue
        loose.append(window[0]["fen"])
        if theme_key == "attack":
            strict.extend(p["fen"] for p in window if _opposite_wings(chess.Board(p["fen"])))
    chosen = strict if len(strict) >= MIDDLEGAME_MIN_POSITIONS else loose
    return tuple(dict.fromkeys(chosen))


@lru_cache(maxsize=1)
def specialist_bots() -> dict[str, Bot]:
    """Every specialist by id, built once from the courses, the master games and the endgame file."""
    from ..content.endgames import load_endgames
    from ..openings.courses import load_courses

    out: list[Bot] = []
    for course in load_courses().values():
        spec = Specialty(SPECIALTY_OPENING, course.id, course.name)
        # the course's own main lines by their full book names: the family name alone also matches transpositions
        # (a "Sicilian Defense" line starting 1...e6), which the 1000 bot then played as 1.e4 e6
        lines = tuple(dict.fromkeys(x.opening.name for x in course.lines)) or tuple(course.openings)
        personality = Personality(favourite_openings=lines, favourite_max_loss_cp=OPENING_FAVOURITE_MAX_LOSS_CP)
        for elo in RATINGS:
            out.append(_specialist(
                spec, elo, personality=personality, book_plies=OPENING_BOOK_PLIES,
                tagline=f"Plays the {course.openings[0]} on both sides",
                description=f"Follows the book lines of the {course.name} course for {OPENING_BOOK_PLIES // 2} moves as White or Black. "
                            "With Guide me on, it names the idea of each book move and the main line you left.",
            ))
        tabiyas = tuple(line.plies[-1]["fen"] for line in course.lines)
        if tabiyas:
            spec = Specialty(SPECIALTY_MIDDLEGAME, course.id, f"{course.name} middlegame", tabiyas)
            for elo in RATINGS:
                out.append(_specialist(
                    spec, elo, tagline=f"Starts from a {course.openings[0]} tabiya",
                    description=f"The game opens at the end of one of the course's {len(tabiyas)} main lines. "
                                "With Guide me on, it names the imbalance that matters and the plan it gives.",
                ))
    for key, (name, _, avatar) in MIDDLEGAME_THEMES.items():
        fens = _middlegame_fens(key)
        if not fens:
            LOGGER.warning("no master-game positions for middlegame theme %s: no specialist", key)
            continue
        spec = Specialty(SPECIALTY_MIDDLEGAME, key, name, fens)
        for elo in RATINGS:
            out.append(_specialist(
                spec, elo, avatar=avatar, tagline=f"Starts from a {name.lower()} middlegame",
                description=f"The game opens from one of {len(fens)} master-game positions after move 12, engine-checked to be roughly level. "
                            "With Guide me on, it names the imbalance that matters and the plan it gives.",
            ))
    endgames = load_endgames()
    for theme in endgames["themes"]:
        fens = tuple(p["fen"] for p in endgames["positions"] if p["theme"] == theme["key"])
        if not fens:
            continue
        spec = Specialty(SPECIALTY_ENDGAME, theme["key"], theme["name"], fens)
        for elo in RATINGS:
            out.append(_specialist(
                spec, elo, tagline=theme["blurb"],
                description=f"The game opens from one of the trainer's {len(fens)} {theme['name'].lower()} positions, you on the side with the task. "
                            "With Guide me on, it gives the verdict after each move and the rule it rests on.",
            ))
    LOGGER.info("specialist bots: %d", len(out))
    return {b.id: b for b in out}


def all_bots() -> list[Bot]:
    return BOTS + list(specialist_bots().values())


def specialist_for(kind: str, key: str, elo: int) -> Bot | None:
    """The specialist of this kind and key nearest the rating, or None when the content has none."""
    pool = [b for b in specialist_bots().values() if b.specialty and b.specialty.kind == kind and b.specialty.key == key]
    return min(pool, key=lambda b: abs(b.elo - elo)) if pool else None
