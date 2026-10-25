"""The weekly plan: five items ordered by the win chance each weakness costs per game, each with its
measured reason and the content that trains it. Computed on request, nothing stored."""
from __future__ import annotations

from ..review.phases import ENDGAME, MIDDLEGAME
from . import resources
from .endgames import TYPE_NAMES

ITEMS = 5


def _family(name: str) -> str:
    """The opening family of a book name: "Italian Game: Two Knights Defense" -> "Italian Game"."""
    return name.split(":")[0]


def plan(sections: dict, band: int | None) -> list[dict]:
    # Every gain is the summed win-chance drop of the moves the item names, per game, so items compare
    # like for like. A move can sit in two items (a blunder that missed a fork); gains are never added.
    items: list[dict] = []
    t = sections["tactics"]
    most = next((r for r in t["motifs"] if r["theme"] == t["most_missed"]), None)
    if most:
        items.append({"area": "tactics", "gain_per_game": most["drop_per_game"], "goal": f"Find {most['name'].lower()}s before you move", "plan_goal": f"tactics: {most['name'].lower()}s",
                      "why": f"You missed {most['missed']} of {most['seen']} {most['name'].lower()} chances, {most['drop_per_game']}% win chance per game.",
                      "action": t["action"], "also": [x for x in (t["lesson"], t["bot"]) if x], "example": most["example"]})
    o = sections["openings"]
    if o["repeated"]:
        r = o["repeated"][0]
        gain = round(r["drop_total"] / max(1, sections["games"]), 1)
        row = next((x for x in o["rows"] if x["name"] == r["opening"]), None)
        items.append({"area": "openings", "gain_per_game": gain, "goal": f"Stop playing {r['played_san']} here: {r['best_san']} is the move",
                      "plan_goal": f"the {_family(r['opening'])} as {r['example']['color']}" if r["opening"] else "openings",
                      "why": f"The same position went wrong {r['times']} times, {gain}% win chance per game.",
                      "action": (row and row["course"]) or o["action"], "also": [], "example": r["example"]})
    elif o["rows"]:
        worst = min(o["rows"], key=lambda x: x["score"])
        leave = worst["leave_book"]
        if leave and leave["costly"]:
            gain = round(leave["drop_total"] / max(1, sections["games"]), 1)
            items.append({"area": "openings", "gain_per_game": gain, "goal": f"Learn the {worst['name']} past move {round(leave['move_number'])}", "plan_goal": f"the {_family(worst['name'])} as {worst['color']}",
                          "why": f"You leave the book around move {round(leave['move_number'])} and {leave['costly']} of {leave['games']} departures cost you.",
                          "action": worst["course"] or o["action"], "also": [], "example": leave["example"]})
    e = sections["endgames"]
    conv = e["conversion"]
    if conv and conv["won"] < conv["games"]:
        items.append({"area": ENDGAME, "gain_per_game": conv["drop_per_game"], "goal": "Convert a winning endgame",
                      "plan_goal": f"{TYPE_NAMES[e['lose_most']]}s" if e["lose_most"] else "endgames",
                      "why": f"{conv['games'] - conv['won']} of {conv['games']} winning endgames were not won, {conv['drop_per_game']}% win chance per game.",
                      "action": e["action"], "also": [x for x in (e["lesson"], e["bot"]) if x], "example": conv["example"]})
    m = sections["middlegame"]
    pl = m["errors"]["plan"]
    if pl["count"]:
        items.append({"area": MIDDLEGAME, "gain_per_game": pl["drop_per_game"], "goal": "Choose a plan before a quiet move", "plan_goal": "middlegame strategy and plans",
                      "why": f"{pl['count']} middlegame mistakes were quiet moves with the wrong plan, {pl['drop_per_game']}% win chance per game.",
                      "action": resources.lesson_in("middlegame", band), "also": [x for x in (m["watch"],) if x], "example": pl["example"]})
    q = sections["quality"]
    peak = q["clusters"]["peak"]
    if peak:
        gain = round(peak["drop_total"] / max(1, sections["games"]), 1)
        items.append({"area": "blunders", "gain_per_game": gain, "goal": f"Check the opponent's threats at moves {peak['from_move']}–{peak['to_move']}", "plan_goal": "calculation and defending",
                      "why": f"{peak['blunders']} blunders fell there, {gain}% win chance per game.",
                      "action": q["action"], "also": [x for x in (q["bot"],) if x], "example": peak["example"]})
    items = [i for i in items if i["action"] and i["gain_per_game"] > 0]
    items.sort(key=lambda i: -i["gain_per_game"])
    for k, item in enumerate(items[:ITEMS], start=1):
        item["rank"] = k
    return items[:ITEMS]
