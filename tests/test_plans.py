"""Study plans: a goal becomes steps that all point at real content, an unknown goal gets no plan,
and progress is read from the player's own records."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.bots.roster import find_bot
from backend.content.endgames import load_endgames
from backend.content.games import find_game
from backend.content.lessons import find_lesson
from backend.openings.book import load_book
from backend.openings.courses import load_courses
from backend.plans import plan as P
from backend.plans.plan import build_plan, resolve_goal
from backend.puzzles.store import THEME_INFO


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def _resolves(step: dict) -> bool:
    kind, sid = step["kind"], step["id"]
    if kind == P.STEP_LESSON:
        return find_lesson(sid) is not None
    if kind == P.STEP_COURSE:
        return sid in load_courses()
    if kind in (P.STEP_LINE, P.STEP_TRAP):
        course_id, _, line_id = sid.partition("/")
        c = load_courses().get(course_id)
        return c is not None and any(x.id == line_id for x in (c.lines if kind == P.STEP_LINE else c.traps))
    if kind == P.STEP_BOOK:
        pgns = {o.pgn for o in load_book().all}
        return sid in pgns and all(grp["url"] == f"/openings?line={grp['pgn']}" and grp["pgn"] in pgns for grp in step.get("groups", []))
    if kind == P.STEP_GAME:
        return find_game(sid) is not None
    if kind == P.STEP_PUZZLES:
        source, _, key = sid.partition(":")
        return source == "opening" or key in THEME_INFO
    if kind == P.STEP_ENDGAME:
        return any(t["key"] == sid for t in load_endgames()["themes"])
    if kind == P.STEP_PLAY:
        return find_bot(sid) is not None
    return False


def test_sicilian_goal_resolves_to_real_content_for_both_sides():
    goal = "I want to learn the Sicilian Defense and all its variations, its key points, how to play on both sides and how to form strong strategies within it"
    g = resolve_goal(goal)
    assert [f.name for f in g.families] == ["Sicilian Defense"] and g.all_variations and g.sides == ["white", "black"]
    started = time.monotonic()
    plan = build_plan(goal, None)
    seconds = time.monotonic() - started
    assert plan is not None and plan["sides"] == ["white", "black"]
    kinds = {s["kind"] for s in plan["steps"]}
    assert {P.STEP_COURSE, P.STEP_LINE, P.STEP_TRAP, P.STEP_BOOK, P.STEP_GAME, P.STEP_PLAY} <= kinds
    assert all(_resolves(s) for s in plan["steps"]), [s for s in plan["steps"] if not _resolves(s)]
    assert [s["n"] for s in plan["steps"]] == list(range(1, len(plan["steps"]) + 1))
    assert all(s["reason"] and s["url"].startswith("/") for s in plan["steps"])
    # every variation group of the family is listed inside one step, and the key points come from the course and its tabiyas
    books = [s for s in plan["steps"] if s["kind"] == P.STEP_BOOK]
    assert len(books) == 1 and len(books[0]["groups"]) > 20 and books[0]["title"] == f"Know the Sicilian Defense variations: {len(books[0]['groups'])} groups"
    assert any(p["source"]["kind"] == P.STEP_COURSE for p in plan["key_points"])
    assert any(p["source"]["kind"] == P.STEP_LINE for p in plan["key_points"])
    # every Sicilian course is in the plan, and both colours get a game against each course's specialist, with Guide me on
    assert [s["id"] for s in plan["steps"] if s["kind"] == P.STEP_COURSE] == ["sicilian-dragon", "sicilian-najdorf"]
    plays = [s for s in plan["steps"] if s["kind"] == P.STEP_PLAY and s["id"].startswith("opening-")]
    assert sorted(s["side"] for s in plays) == ["black", "black", "white", "white"] and all("guide=1" in s["url"] for s in plays)
    print(f"sicilian plan: {len(plan['steps'])} steps from {plan['sources']} in {seconds:.2f}s")


def test_variation_named_alone_brings_its_family_and_colour():
    g = resolve_goal("Najdorf as black")
    assert [f.name for f in g.families] == ["Sicilian Defense"] and g.variations == ["najdorf variation"] and g.sides == ["black"]
    plan = build_plan("Najdorf as black", {"puzzle_rating": 1750, "band": 5})
    books = [s for s in plan["steps"] if s["kind"] == P.STEP_BOOK]
    assert [b["title"] for b in books] == ["Najdorf Variation"]
    plays = [s for s in plan["steps"] if s["kind"] == P.STEP_PLAY]
    assert all(s["side"] == "black" for s in plays) and all(s["id"].endswith("-1800") for s in plays)
    assert "No course covers" not in books[0]["reason"]
    assert [s["id"] for s in plan["steps"] if s["kind"] == P.STEP_COURSE] == ["sicilian-najdorf"]


def test_a_course_that_misses_the_named_variation_is_dropped():
    # both Sicilian courses match the family: a Najdorf plan keeps only the Najdorf course, a Dragon plan only the Dragon
    plan = build_plan("Najdorf as white", None)
    course_kinds = (P.STEP_COURSE, P.STEP_LINE, P.STEP_TRAP)
    assert {s["id"].split("/")[0] for s in plan["steps"] if s["kind"] in course_kinds} == {"sicilian-najdorf"}
    assert not [s for s in plan["steps"] if "dragon" in s["id"]]
    assert {p["source"]["id"].split("/")[0] for p in plan["key_points"] if p["source"]["kind"] in course_kinds} == {"sicilian-najdorf"}
    assert [s["title"] for s in plan["steps"] if s["kind"] == P.STEP_BOOK] == ["Najdorf Variation"]
    assert {P.STEP_GAME, P.STEP_PUZZLES} <= {s["kind"] for s in plan["steps"]}
    dragon = build_plan("Sicilian Dragon", None)
    assert [s["id"] for s in dragon["steps"] if s["kind"] == P.STEP_COURSE] == ["sicilian-dragon"]
    assert {P.STEP_LINE, P.STEP_TRAP} <= {s["kind"] for s in dragon["steps"]}
    assert not any("No course covers" in s["reason"] for s in dragon["steps"])


def test_one_named_variation_does_not_expand_every_group():
    assert not resolve_goal("the main variation of the Italian").all_variations
    assert resolve_goal("the Italian and its variations").all_variations


def test_theme_goals_reach_lessons_puzzles_endgames_and_a_specialist():
    plan = build_plan("Rook endgames", None)
    kinds = plan["sources"]
    assert kinds[P.STEP_ENDGAME] == 1 and kinds[P.STEP_LESSON] >= 5 and kinds[P.STEP_PUZZLES] >= 1
    assert next(s for s in plan["steps"] if s["kind"] == P.STEP_ENDGAME)["id"] == "rook"
    assert next(s for s in plan["steps"] if s["kind"] == P.STEP_PLAY)["id"].startswith("endgame-rook-")
    lessons = [s["title"].lower() for s in plan["steps"] if s["kind"] == P.STEP_LESSON]
    assert any("lucena" in t or "philidor" in t for t in lessons)
    attack = build_plan("Attacking a castled king", None)
    assert next(s for s in attack["steps"] if s["kind"] == P.STEP_PLAY)["id"].startswith("middlegame-attack-")
    assert any(s["id"] == "b4m2l2" for s in attack["steps"])  # the Greek gift lesson


def test_unknown_goal_gets_no_plan_and_the_closest_families(client):
    r = client.post("/api/plans", json={"goal": "learn chess properly"})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] is None and body["message"] and len(body["closest"]) >= 3
    assert all({"name", "eco_from", "eco_to", "lines"} <= set(c) for c in body["closest"])
    typo = client.post("/api/plans", json={"goal": "the Sicillian"}).json()
    assert typo["plan"] is None and typo["closest"][0]["name"] == "Sicilian Defense"
    assert client.get("/api/plans").json()["plans"] == []


def test_plan_is_stored_per_player_with_live_progress(client):
    r = client.post("/api/plans", json={"goal": "Rook endgames"})
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    assert plan["done"] == 0 and plan["total"] == len(plan["steps"])
    lesson = next(s for s in plan["steps"] if s["kind"] == P.STEP_LESSON)
    assert lesson["tracked"] and not lesson["done"]
    client.post("/api/learn/progress", json={"lesson_id": lesson["id"], "completed": True, "score": 100})
    again = client.get(f"/api/plans/{plan['id']}").json()["plan"]
    assert next(s for s in again["steps"] if s["id"] == lesson["id"])["done"] and again["done"] == 1
    endgame = next(s for s in again["steps"] if s["kind"] == P.STEP_ENDGAME)
    assert endgame["progress"].endswith("positions") and not endgame["done"]
    # a step the store cannot see is ticked by hand; a tracked one refuses the tick
    game = next(s for s in again["steps"] if s["kind"] == P.STEP_GAME)
    ticked = client.post(f"/api/plans/{plan['id']}/steps/{game['n']}", json={"done": True}).json()["plan"]
    assert next(s for s in ticked["steps"] if s["n"] == game["n"])["done"] and ticked["done"] == 2
    assert client.post(f"/api/plans/{plan['id']}/steps/{lesson['n']}", json={"done": True}).status_code == 409
    listed = client.get("/api/plans").json()["plans"]
    assert [p["id"] for p in listed] == [plan["id"]] and listed[0]["done"] == 2
    assert "player_id" not in r.text
    assert client.delete(f"/api/plans/{plan['id']}").json() == {"deleted": True}
    assert client.get(f"/api/plans/{plan['id']}").status_code == 404


def test_two_quick_ticks_both_stay(client):
    import asyncio

    from backend.routers.plans import StepTick, tick_step
    from backend.storage.db import database

    plan = client.post("/api/plans", json={"goal": "Rook endgames"}).json()["plan"]
    games = [s["n"] for s in plan["steps"] if s["kind"] == P.STEP_GAME][:2]
    assert len(games) == 2

    async def both():
        row = await database.fetch_one("SELECT player_id FROM player_plans WHERE id = ?", (plan["id"],))
        await asyncio.gather(*(tick_step(plan["id"], n, StepTick(done=True), row["player_id"]) for n in games))

    client.portal.call(both)
    again = client.get(f"/api/plans/{plan['id']}").json()["plan"]
    assert all(next(s for s in again["steps"] if s["n"] == n)["done"] for n in games)


@pytest.mark.parametrize(("goal", "courses"), [
    ("Queen's Gambit as white", ["queens-gambit"]),
    ("Queen's Gambit Declined as black", ["queens-gambit-declined"]),
    ("Najdorf as black", ["sicilian-najdorf"]),
    ("Sicilian Dragon", ["sicilian-dragon"]),
    ("Sicilian for both sides", ["sicilian-dragon", "sicilian-najdorf"]),  # no white Sicilian course: both black ones
    ("London", ["london"]),
    ("French", ["french"]),
])
def test_a_goal_gets_the_courses_for_its_opening_and_side(goal, courses):
    plan = build_plan(goal, None)
    course_kinds = (P.STEP_COURSE, P.STEP_LINE, P.STEP_TRAP)
    assert [s["id"] for s in plan["steps"] if s["kind"] == P.STEP_COURSE] == courses
    assert {s["id"].split("/")[0] for s in plan["steps"] if s["kind"] in course_kinds} == set(courses)
