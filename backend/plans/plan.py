"""Goal -> plan. Rules read the goal (opening names from the book, variation names, themes,
colours) and the plan is assembled from catalog items only; every step points at a real id and
says why it is there. A goal that matches nothing gets no plan, only the closest families."""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field

import chess

from ..bots.roster import SPECIALTY_ENDGAME, SPECIALTY_MIDDLEGAME, SPECIALTY_OPENING
from ..bots.specialists import RATINGS, specialist_for
from ..content.games import THEME_NAMES
from ..content.lessons import BANDS
from ..puzzles.store import CONTEXT_THEMES, THEME_INFO, load_library
from ..study.assess import imbalances
from . import catalog
from .catalog import Family, norm

LOGGER = logging.getLogger("chess.plans")

# Step kinds are wire names; frontend/src/lib/planApi.ts mirrors them.
STEP_COURSE = "course"
STEP_LESSON = "lesson"
STEP_LINE = "course_line"
STEP_TRAP = "course_trap"
STEP_BOOK = "book_line"
STEP_GAME = "master_game"
STEP_PUZZLES = "puzzles"
STEP_ENDGAME = "endgame"
STEP_PLAY = "play"
TRACKED_KINDS = frozenset({STEP_LESSON, STEP_PUZZLES, STEP_ENDGAME, STEP_PLAY})  # the rest are ticked by hand

MAX_GAMES = 8  # master games per plan: the ones nearest the player's band
PUZZLE_STEP_SOLVES = 5  # solved puzzles that complete a puzzle step
TABIYA_POINTS_PER_LINE = 2
DEFAULT_ELO = 1400  # the specialist's rating when the player has no settled puzzle rating
SIDES = ("white", "black")
ALL_VARIATIONS = re.compile(r"\b(variations|all (of )?its lines|every line|repertoire)\b")
BOTH_SIDES = re.compile(r"\b(both (sides|colou?rs)|(as|for|with|from) (white and black|black and white)|white and black|black and white)\b")
AS_WHITE = re.compile(r"\b(as|for|with|from|playing) (the )?white\b")
AS_BLACK = re.compile(r"\b(as|for|with|from|playing) (the )?black\b")
SYNONYMS = {"spanish": "ruy lopez", "qgd": "queens gambit declined", "qga": "queens gambit accepted", "kid": "kings indian", "caro": "caro kann"}

# What a phrase means, in the catalog's own keys. "generic" entries apply only when no narrower
# phrase of the same family matched; "without_family" ones only when no opening was named.
PHRASES: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"\brook (endings?|endgames?)\b"), {"label": "Rook endgames", "endgame": ["rook"], "puzzle": ["rookEndgame"], "game": ["rook-endgame"],
                                                   "strands": ["endgames"], "words": ["rook"]}),
    (re.compile(r"\bpawn (endings?|endgames?)\b"), {"label": "Pawn endgames", "endgame": ["pawn"], "puzzle": ["pawnEndgame"], "strands": ["endgames"],
                                                   "words": ["pawn", "opposition", "key squares", "breakthrough"]}),
    (re.compile(r"\b(minor piece|bishop|knight) (endings?|endgames?)\b"), {"label": "Minor-piece endgames", "endgame": ["minor"], "puzzle": ["bishopEndgame", "knightEndgame"],
                                                                        "game": ["knight-vs-bishop", "opposite-bishops"], "strands": ["endgames"], "words": ["bishop", "knight"]}),
    (re.compile(r"\bqueen (endings?|endgames?)\b"), {"label": "Queen endgames", "endgame": ["queen"], "puzzle": ["queenEndgame"], "strands": ["endgames"], "words": ["queen"]}),
    (re.compile(r"\b(checkmates?|mates?|mating)\b"), {"label": "Checkmates", "endgame": ["checkmates"], "puzzle": ["mate", "mateIn1", "mateIn2"], "strands": ["checkmates"]}),
    (re.compile(r"\b(endings?|endgames?)\b"), {"label": "Endgames", "generic": "endgame", "puzzle": ["endgame"], "game": ["endgame"], "strands": ["endgames"]}),
    (re.compile(r"(?<!discovered )(?<!double )(?<!twofold )\b(attack|attacking|castled king|pawn storms?|opposite side castling)\b"),
     {"label": "Attacking the king", "puzzle": ["kingsideAttack", "queensideAttack", "exposedKing"], "game": ["attack", "pawn-storm", "opposite-castling"],
      "strands": ["checkmates", "model games", "tactics", "strategy"], "middlegame": ["attack"],
      "words": ["attack the king", "attacking the king", "castled king", "king attack", "initiative", "pawn storm", "king hunt", "greek gift", "access to the king"]}),
    (re.compile(r"\b(strategy|strategies|strategic|plans?|planning|imbalances?|positional)\b"), {"label": "Strategy", "game": ["positional", "prophylaxis", "pawn-structure", "blockade"],
                                                                                              "strands": ["strategy"], "middlegame": ["positional"]}),
    (re.compile(r"\bmiddlegames?\b"), {"label": "Middlegames", "game": ["positional", "attack"], "strands": ["strategy"], "middlegame": ["attack", "positional"]}),
    (re.compile(r"\b(tactics?|tactical|combinations?)\b"), {"label": "Tactics", "puzzle": ["fork", "pin", "skewer", "discoveredAttack", "doubleCheck", "deflection", "attraction"], "strands": ["tactics"]}),
    (re.compile(r"\bcalculat\w*"), {"label": "Calculation", "strands": ["calculation"], "game": ["calculation"]}),
    (re.compile(r"\b(sacrifices?|sacs?)\b"), {"label": "Sacrifices", "puzzle": ["sacrifice"], "game": ["sacrifice", "exchange-sacrifice", "queen-sacrifice"]}),
    (re.compile(r"\bopenings?\b"), {"label": "Openings", "strands": ["openings"], "without_family": True}),
    (re.compile(r"\b(defense|defending|defensive)\b"), {"label": "Defence", "puzzle": ["defensiveMove"], "game": ["defence", "fortress"], "strands": ["thinking", "strategy"],
                                                      "words": ["defense", "defending", "fortress"], "without_family": True}),
]


@dataclass
class Goal:
    text: str
    families: list[Family] = field(default_factory=list)
    variations: list[str] = field(default_factory=list)  # normalised variation names the goal spelt out
    all_variations: bool = False
    sides: list[str] = field(default_factory=list)
    side_named: bool = False
    labels: list[str] = field(default_factory=list)
    puzzle_themes: list[str] = field(default_factory=list)
    game_themes: list[str] = field(default_factory=list)
    endgame_themes: list[str] = field(default_factory=list)
    strands: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)
    middlegame_keys: list[str] = field(default_factory=list)
    said: str = ""  # the goal normalised, synonyms spelt out

    @property
    def family_keys(self) -> list[str]:
        return [catalog.family_key(f.name) for f in self.families]

    @property
    def ecos(self) -> set[str]:
        return {eco for f in self.families for eco in f.ecos}

    @property
    def empty(self) -> bool:
        return not (self.families or self.puzzle_themes or self.game_themes or self.endgame_themes or self.strands or self.middlegame_keys)


def _add(target: list, items: list) -> None:
    for x in items:
        if x not in target:
            target.append(x)


def resolve_goal(text: str) -> Goal:
    g = Goal(text=text)
    t = norm(text)
    for word, full in SYNONYMS.items():
        if re.search(rf"\b{word}\b", t):
            t += " " + full
    g.said = t
    # Openings: a family whose spoken name is in the goal, then every family that extends a matched name
    # ("queens gambit" also brings "Queen's Gambit Declined"); a variation named after it narrows the lines.
    fams = catalog.families()
    matched = [f for f in fams.values() if re.search(rf"\b{re.escape(catalog.family_key(f.name))}\b", t)]
    keys = [catalog.family_key(f.name) for f in matched]
    for f in fams.values():
        if f not in matched and any(catalog.family_key(f.name).startswith(k + " ") for k in keys):
            matched.append(f)
    # A variation named on its own ("the Najdorf") brings its family along; a variation that carries
    # another family's name ("Pterodactyl Defense: Sicilian Variation") does not.
    family_keys = {catalog.family_key(f.name) for f in fams.values()}
    for f in fams.values():
        for group in catalog.groups_of(f.name):
            key = catalog.family_key(group.name.replace(" Variation", "").replace(" Attack", "").replace(" System", ""))
            if group.name != f.name and len(key) > 2 and key not in family_keys and re.search(rf"\b{re.escape(key)}\b", t):
                _add(g.variations, [norm(group.name)])
                if f not in matched:
                    matched.append(f)
    g.families = sorted(matched, key=lambda f: -len(f.lines))
    g.all_variations = bool(ALL_VARIATIONS.search(t))
    if BOTH_SIDES.search(t):
        g.sides, g.side_named = list(SIDES), True
    elif AS_WHITE.search(t) or AS_BLACK.search(t):
        g.sides = [s for s, rx in (("white", AS_WHITE), ("black", AS_BLACK)) if rx.search(t)]
        g.side_named = True
    for rx, meaning in PHRASES:
        if not rx.search(t):
            continue
        if meaning.get("without_family") and g.families:
            continue
        if meaning.get("generic") == "endgame" and g.endgame_themes:
            continue
        if meaning.get("generic") == "endgame":
            meaning = {**meaning, "endgame": [th["key"] for th in catalog.load_endgames()["themes"]]}
        _add(g.labels, [meaning["label"]])
        _add(g.puzzle_themes, meaning.get("puzzle", []))
        _add(g.game_themes, meaning.get("game", []))
        _add(g.endgame_themes, meaning.get("endgame", []))
        _add(g.strands, meaning.get("strands", []))
        _add(g.words, meaning.get("words", []))
        _add(g.middlegame_keys, meaning.get("middlegame", []))
    phrase_labels = list(g.labels)
    for key, (name, _) in THEME_INFO.items():  # a puzzle theme named outright: "forks", "the pin", "zugzwang"
        if key not in CONTEXT_THEMES and re.search(rf"\b{re.escape(norm(name))}s?\b", t):
            _add(g.puzzle_themes, [key])
            if not phrase_labels:
                _add(g.labels, [name])
    for key, name in THEME_NAMES.items():  # a master-game theme named outright: "prophylaxis", "minority attack"
        if key not in ("classic", "world-championship", "immortal") and re.search(rf"\b{re.escape(norm(name))}\b", t):
            _add(g.game_themes, [key])
            if not phrase_labels:
                _add(g.labels, [name])
    return g


def closest_families(text: str, limit: int = 5) -> list[dict]:
    """Families whose spoken name is close to a word of the goal; the largest families when none is."""
    fams = catalog.families()
    by_key = {catalog.family_key(f.name): f for f in fams.values()}
    words = set(norm(text).split())
    hits: list[str] = []
    for w in words:
        if len(w) >= 4:
            hits += difflib.get_close_matches(w, list(by_key), n=limit, cutoff=0.75)
    if not hits:
        hits = [catalog.family_key(f.name) for f in sorted(fams.values(), key=lambda f: -len(f.lines))[:limit]]
    out = []
    for k in dict.fromkeys(hits):
        f = by_key[k]
        out.append({"name": f.name, "eco_from": f.ecos[0], "eco_to": f.ecos[-1], "lines": len(f.lines)})
    return out[:limit]


def _step(kind: str, id: str, title: str, url: str, reason: str, **extra) -> dict:
    return {"kind": kind, "id": id, "title": title, "url": url, "reason": reason, "tracked": kind in TRACKED_KINDS, **extra}


def _play_step(bot, side: str, title: str, reason: str) -> dict:
    return _step(STEP_PLAY, bot.id, title, f"/play?bot={bot.id}&color={side}&guide=1", reason, side=side)


def _band_name(band: int) -> str:
    return next(b["name"] for b in BANDS if b["band"] == band)


def _nearest_rating(puzzle_rating: float | None) -> int:
    return min(RATINGS, key=lambda r: abs(r - (puzzle_rating or DEFAULT_ELO)))


def _eco_range(grp: Family) -> str:
    return grp.ecos[0] if len(grp.ecos) == 1 else f"{grp.ecos[0]}–{grp.ecos[-1]}"


def _lesson_matches(lsn, g: Goal) -> bool:
    text = catalog.lesson_text(lsn)
    if any(k in text for k in g.family_keys if len(k) > 3):
        return True
    if set(lsn.practice) & set(g.puzzle_themes):
        return True
    if lsn.strand in g.strands:
        return not g.words or any(w in text for w in g.words)
    return False


def _tabiya_points(course, sides: list[str]) -> list[dict]:
    """What a grandmaster's assessment says about the end of each main line, for the chosen sides."""
    out = []
    for line in course.lines:
        n = 0
        for item in imbalances(chess.Board(line.plies[-1]["fen"])):
            side = item["side"].lower()
            if side != "both" and side not in sides:
                continue
            plan_side = side if side != "both" else sides[0]
            out.append({"text": f"{line.name}: {item['text']}; the plan for {plan_side}: {item['plan_for']}.",
                        "source": {"kind": STEP_LINE, "id": f"{course.id}/{line.id}", "title": line.name}})
            n += 1
            if n >= TABIYA_POINTS_PER_LINE:
                break
    return out


def build_plan(goal_text: str, level: dict | None) -> dict | None:
    """The stored plan for a goal, or None when the catalog has nothing for it."""
    g = resolve_goal(goal_text)
    if g.empty:
        return None
    elo = _nearest_rating(level["puzzle_rating"] if level else None)
    band = level["band"] if level else None
    steps: list[dict] = []
    points: list[dict] = []
    sources: dict[str, int] = {}

    def add(step: dict) -> None:
        steps.append(step)
        sources[step["kind"]] = sources.get(step["kind"], 0) + 1

    course_of = {f.name: catalog.courses_for(f.name, g.sides) for f in g.families}
    if not any(course_of.values()):  # no course for the side asked: one for the other side still teaches both
        course_of = {f.name: catalog.courses_for(f.name) for f in g.families}
    courses = list({c.id: c for cs in course_of.values() for c in cs}.values())
    # a course whose lines reach none of the variations the goal names for its family teaches something else: drop it
    covered: set[str] = set()
    if g.variations:
        kept = []
        for c in courses:
            reached = {norm(line.opening.variation.split(",")[0].strip()) for line in c.lines}
            named = {norm(grp.name) for fam, cs in course_of.items() if c in cs for grp in catalog.groups_of(fam)} & set(g.variations)
            if not named or named & reached:
                kept.append(c)
                covered |= reached
        courses = kept
    if courses and not g.side_named:  # no side asked: the side of the course the goal names most closely
        def said(c) -> tuple[int, bool]:  # longest course opening the goal names; a tie goes to the course it heads
            keys = [catalog.family_key(p) for p in c.openings]
            hits = [k for k in keys if re.search(rf"\b{re.escape(k)}\b", g.said)]
            return max(map(len, hits), default=0), keys[0] in hits
        side = max(courses, key=said).side
        courses = [c for c in courses if c.side == side]
    sides = g.sides or ([courses[0].side] if courses else list(SIDES))
    side_reason = ("You asked for both sides" if g.side_named and len(sides) == 2 else f"You asked for {sides[0]}" if g.side_named
                   else f"The course is written for {sides[0]}; say 'both sides' to add the other colour" if courses else "")

    for c in courses:
        add(_step(STEP_COURSE, c.id, c.name, f"/openings/courses/{c.id}",
                  f"The {c.name} course: {len(c.lines)} main lines, {len(c.traps)} traps and {len(c.model_games)} model games. {side_reason}."))
        for side in sides:
            points += [{"text": idea, "source": {"kind": STEP_COURSE, "id": c.id, "title": f"{c.name}, ideas for {side}"}} for idea in c.ideas[side]]
        points += [{"text": f"{s['name']}: {s['text']}", "source": {"kind": STEP_COURSE, "id": c.id, "title": f"{c.name}, pawn structures"}} for s in c.structures]
        for side in sides:
            points += [{"text": f"{side.capitalize()}'s {p}", "source": {"kind": STEP_COURSE, "id": c.id, "title": f"{c.name}, the pieces"}} for p in c.pieces[side]]
        points += _tabiya_points(c, sides)

    for lsn in sorted((x for x in catalog.lessons() if _lesson_matches(x, g)), key=lambda x: (x.band, x.id)):
        kinds = [s["type"] for s in lsn.sections]
        narrated = "lecture" in kinds or "game" in kinds
        add(_step(STEP_LESSON, lsn.id, lsn.title, f"/learn/{lsn.id}",
                  f"{'Narrated lesson' if narrated else 'Lesson'} in band {lsn.band} ({_band_name(lsn.band)}), {lsn.strand}: {lsn.objective}", watch=narrated))

    for c in courses:
        for line in c.lines:
            add(_step(STEP_LINE, f"{c.id}/{line.id}", line.name, f"/openings/courses/{c.id}?line={line.id}",
                      f"Main line, {line.opening.eco} {line.opening.name}; every move has the course's note. Step through it, then practise it from memory."))
        for trap in c.traps:
            who = "avoid" if ("white" if trap.mistake_ply % 2 else "black") == c.side else "set"
            add(_step(STEP_TRAP, f"{c.id}/{trap.id}", trap.name, f"/openings/courses/{c.id}?line={trap.id}",
                      f"A trap to {who}: {trap.punishment}"))

    for f in g.families:
        groups = catalog.groups_of(f.name)
        if g.all_variations and not g.variations:  # every group, listed inside one step rather than one step each
            add(_step(STEP_BOOK, f.root.pgn, f"Know the {f.name} variations: {len(groups)} groups", f"/openings?line={f.root.pgn}",
                      f"You said variations: the book names {len(f.lines)} lines of the family in {len(groups)} groups. Open each group and step through its first line.",
                      groups=[{"name": grp.name, "pgn": grp.root.pgn, "url": f"/openings?line={grp.root.pgn}", "lines": len(grp.lines), "ecos": _eco_range(grp)}
                              for grp in groups]))
            continue
        chosen = [grp for grp in groups if norm(grp.name) in g.variations] if g.variations else [Family(f.name, [f.root])]
        why = "the variation you named" if g.variations else "the family's root line; say 'variations' for every named line"
        for grp in chosen:
            no_course = f" No course covers the {grp.name} yet." if g.variations and norm(grp.name) not in covered else ""
            add(_step(STEP_BOOK, grp.root.pgn, grp.name, f"/openings?line={grp.root.pgn}",
                      f"{len(grp.lines)} named line{'s' if len(grp.lines) != 1 else ''} in the book, ECO {_eco_range(grp)}: {why}.{no_course}"))

    games = {gm.id: gm for c in courses for gm in c.model_games}
    for gm in catalog.games_in(g.ecos, g.family_keys) + [gm for gm in catalog.load_games() if set(gm.themes) & set(g.game_themes)]:
        games.setdefault(gm.id, gm)
    ranked = sorted(games.values(), key=lambda gm: (abs(gm.level - band) if band is not None else gm.level, gm.year))
    for gm in ranked[:MAX_GAMES]:
        add(_step(STEP_GAME, gm.id, f"{gm.white} – {gm.black}, {gm.year}", f"/games/{gm.id}",
                  f"{gm.why} ({', '.join(THEME_NAMES.get(t, t) for t in gm.themes)}; band {gm.level}.)"))
    if len(ranked) > MAX_GAMES:
        LOGGER.info("plan %r: %d of %d master games kept, the nearest to band %s", goal_text, MAX_GAMES, len(ranked), band)

    lib = load_library()
    for f in g.families:
        n = catalog.opening_puzzle_count(f.name)
        if n:
            tag = catalog.opening_tag(f.name)
            add(_step(STEP_PUZZLES, f"opening:{tag}", f"Puzzles from the {f.name}", f"/puzzles?opening={tag}",
                      f"{n} puzzles taken from games in the {f.name}: the tactics this opening produces. Solve {PUZZLE_STEP_SOLVES} to complete the step."))
    for key in g.puzzle_themes:
        n = len(lib.by_theme.get(key, []))
        if n:
            name, desc = THEME_INFO[key]
            add(_step(STEP_PUZZLES, f"theme:{key}", f"{name} puzzles", f"/puzzles?theme={key}",
                      f"{n} puzzles tagged {name}: {desc} Solve {PUZZLE_STEP_SOLVES} to complete the step."))

    for key in g.endgame_themes:
        theme = catalog.endgame_theme(key)
        if theme and theme["positions"]:
            add(_step(STEP_ENDGAME, key, theme["name"], f"/endgames?theme={key}",
                      f"{len(theme['positions'])} engine-verified positions: {theme['blurb']} Solve every one to complete the step."))
            points += [{"text": f"{p['title']}: {p['tip']}", "source": {"kind": STEP_ENDGAME, "id": key, "title": theme["name"]}} for p in theme["positions"]]

    for c in courses:
        bot = specialist_for(SPECIALTY_OPENING, c.id, elo)
        for side in sides:
            if bot:
                add(_play_step(bot, side, f"Play the {bot.name} specialist as {side}",
                               f"About {bot.elo}: it follows the course's book lines on both sides. Guide me names the idea of each book move and the main line you left."))
        tabiya = specialist_for(SPECIALTY_MIDDLEGAME, c.id, elo)
        if tabiya:
            add(_play_step(tabiya, sides[0], f"Play the {c.name} middlegame",
                           f"About {tabiya.elo}: the game starts at the end of a main line, so the plans in the key points are the whole game."))
    for kind, keys in ((SPECIALTY_MIDDLEGAME, g.middlegame_keys), (SPECIALTY_ENDGAME, g.endgame_themes)):
        for key in keys:
            bot = specialist_for(kind, key, elo)
            if bot:
                add(_play_step(bot, sides[0], f"Play the {bot.name} specialist", f"About {bot.elo}: {bot.description}"))

    if not steps:
        return None
    for n, s in enumerate(steps, start=1):
        s["n"] = n
    title = ", ".join(f.name for f in g.families[:2]) or ", ".join(g.labels[:2])
    if g.families and g.side_named:
        title += " for both sides" if len(sides) == 2 else f" as {sides[0]}"
    return {"goal": goal_text, "title": title, "sides": sides, "elo": elo, "key_points": points, "steps": steps, "ticked": [], "sources": sources}


def _specialty_prefix(bot_id: str) -> str:
    return bot_id.rsplit("-", 1)[0] + "-"


def with_progress(plan: dict, *, lessons_done: set[str], solved_puzzle_ids: set[str], finished_games: list[tuple[str, str]], endgame_stats: dict) -> dict:
    """The plan with every step's `done` and `progress` read from the player's existing records."""
    lib = load_library()
    ticked = set(plan.get("ticked", []))
    steps = []
    for s in plan["steps"]:
        done, progress = s["n"] in ticked, None
        if s["kind"] == STEP_LESSON:
            done = s["id"] in lessons_done
        elif s["kind"] == STEP_PUZZLES:
            kind, _, key = s["id"].partition(":")
            solved = [p for pid in solved_puzzle_ids if (p := lib.by_id.get(pid)) and (key in p.themes if kind == "theme" else catalog.opening_tag_matches(p, key))]
            done, progress = len(solved) >= PUZZLE_STEP_SOLVES, f"{min(len(solved), PUZZLE_STEP_SOLVES)}/{PUZZLE_STEP_SOLVES} solved"
        elif s["kind"] == STEP_ENDGAME:
            theme = catalog.endgame_theme(s["id"])
            keys = [p["key"] for p in theme["positions"]] if theme else []
            solved = sum(1 for k in keys if (endgame_stats.get(k) or {}).get("solved"))
            done, progress = bool(keys) and solved == len(keys), f"{solved}/{len(keys)} positions"
        elif s["kind"] == STEP_PLAY:
            n = sum(1 for bot_id, color in finished_games if bot_id.startswith(_specialty_prefix(s["id"])) and color == s["side"])
            done, progress = n >= 1, f"{n} game{'s' if n != 1 else ''} played"
        steps.append({**s, "done": done, "progress": progress})
    return {**plan, "steps": steps, "done": sum(1 for s in steps if s["done"]), "total": len(steps)}
