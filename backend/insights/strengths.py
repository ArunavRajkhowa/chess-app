"""What the player does well, only where the numbers say so: a phase played better than the band
expects, a motif usually found, an opening or imbalance scored well, endgames converted, puzzle themes solved."""
from __future__ import annotations

from collections import defaultdict

from ..puzzles.store import THEME_INFO, load_library
from ..review.phases import ENDGAME, MIDDLEGAME, OPENING
from ..storage.db import database
from .quality import MIN_PHASE_MOVES
from .tactics import FOUND_RATE_STRENGTH, MIN_SEEN_FOR_STRENGTH

GOOD_SCORE = 67  # two wins in three
MIN_GAMES = 3
PUZZLE_MIN_TRIED = 5


async def puzzle_strengths(player: str) -> list[dict]:
    rows = await database.fetch_all("SELECT puzzle_id, solved FROM puzzle_attempts WHERE player_id = ? AND mode != 'rush' ORDER BY id DESC LIMIT 500", (player,))
    lib = load_library()
    by_theme: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        p = lib.by_id.get(r["puzzle_id"])
        for t in (p.themes if p else []):
            by_theme[t].append(int(r["solved"]))
    out = []
    for t, xs in by_theme.items():
        if len(xs) >= PUZZLE_MIN_TRIED and sum(xs) / len(xs) >= FOUND_RATE_STRENGTH and t in THEME_INFO:
            out.append({"area": "puzzles", "text": f"{THEME_INFO[t][0]} puzzles: {sum(xs)} of {len(xs)} solved.", "example": None})
    return out


def strengths(sections: dict, band_cmp: dict | None) -> list[dict]:
    out: list[dict] = []
    q = sections["quality"]
    for ph in (OPENING, MIDDLEGAME, ENDGAME):
        v = q["phases"].get(ph)
        if band_cmp and v and v["moves"] >= MIN_PHASE_MOVES and v["acpl"] < band_cmp["expected_low"]:
            out.append({"area": ph, "text": f"Your {ph} centipawn loss ({v['acpl']}) beats what your band plays at ({band_cmp['expected_low']}–{band_cmp['expected_high']}).", "example": None})
    for r in sections["tactics"]["motifs"]:
        if r["seen"] >= MIN_SEEN_FOR_STRENGTH and r["found"] / r["seen"] >= FOUND_RATE_STRENGTH:
            out.append({"area": "tactics", "text": f"You find {r['name'].lower()}s: {r['found']} of {r['seen']}.", "example": None})
    for r in sections["openings"]["rows"]:
        if r["games"] >= MIN_GAMES and r["score"] >= GOOD_SCORE:
            out.append({"area": "openings", "text": f"As {r['color'].capitalize()} in the {r['name']} you score {r['score']}% over {r['games']} games.", "example": None})
    for r in sections["middlegame"]["imbalances"]:
        if r["mine"] and r["games"] >= MIN_GAMES and r["score"] >= GOOD_SCORE:
            out.append({"area": "middlegame", "text": f"With {r['kind']} on your side you score {r['score']}% over {r['games']} games.", "example": r["example"]})
    conv = sections["endgames"]["conversion"]
    if conv and conv["games"] >= MIN_GAMES and conv["rate"] >= 100 * FOUND_RATE_STRENGTH:
        out.append({"area": "endgames", "text": f"You convert winning endgames: {conv['won']} of {conv['games']}.", "example": None})
    return out
