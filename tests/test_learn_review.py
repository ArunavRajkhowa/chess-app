"""Narrated lectures validate at load; missed tasks come back on the spaced ladder; the puzzle rating places the player."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.content import lessons as L
from backend.routers.learn import REVIEW_LADDER_DAYS, band_for_rating, next_interval
from backend.storage.db import database

FORK = "2q3k1/8/8/5N2/6P1/7K/8/8 w - - 0 1"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    L.load_curriculum.cache_clear()
    with TestClient(create_app()) as c:
        yield c


def _curriculum(tmp_path, monkeypatch, sections: list[dict]) -> list[dict]:
    data = {"modules": [{"id": "x", "band": 1, "title": "t", "lessons": [{"id": "l1", "title": "a", "sections": sections}]}]}
    (tmp_path / "t.json").write_text(json.dumps(data))
    monkeypatch.setattr(L, "LESSONS_DIR", tmp_path)
    L.load_curriculum.cache_clear()
    try:
        return L.load_curriculum()[0].lessons[0].sections
    finally:
        L.load_curriculum.cache_clear()


def test_a_lecture_plays_its_moves_and_fills_in_every_frame_position(tmp_path, monkeypatch):
    sections = _curriculum(tmp_path, monkeypatch, [
        {"type": "lecture", "frames": [
            {"fen": FORK, "say": "The knight is one jump from a fork.", "arrows": [{"from": "f5", "to": "e7", "brush": "green"}]},
            {"move": "Ne7+", "say": "Check, and the queen on c8 is attacked too."},
            {"move": "g8f8", "say": "The king must move."},
            {"move": "Nxc8", "say": "And the queen falls."},
        ]},
        {"type": "lecture", "frames": [{"fen": FORK, "say": "fine"}, {"move": "Nd7", "say": "illegal: the knight cannot reach d7"}]},
        {"type": "lecture", "frames": [{"move": "Ne7+", "say": "no starting position"}]},
        {"type": "lecture", "frames": [{"fen": FORK, "say": ""}]},
    ])
    assert len(sections) == 1, "the three broken lectures are dropped, each alone"
    frames = sections[0]["frames"]
    assert [f.get("san") for f in frames] == [None, "Ne7+", "Kf8", "Nxc8"]
    assert frames[1]["uci"] == "f5e7" and frames[1]["fen"].startswith("2q3k1/4N3/")
    assert frames[3]["fen"].split(" ")[0] == "2N2k2/8/8/8/6P1/7K/8/8"
    assert frames[0]["fen"] == FORK


def test_the_real_curriculum_has_narrated_openers_in_the_first_bands(client):
    cur = client.get("/api/learn/curriculum").json()
    for band in cur["bands"][:4]:
        for module in band["modules"]:
            assert module["lessons"][0]["watch"], f"module {module['id']} has no narrated walkthrough"


def test_a_missed_task_comes_back_tomorrow_and_climbs_the_ladder_when_solved(client):
    lesson = client.get("/api/learn/lessons/b0m1l1").json()
    quiz = next(i for i, s in enumerate(lesson["sections"]) if s["type"] == "quiz")
    text = next(i for i, s in enumerate(lesson["sections"]) if s["type"] == "text")
    r = client.post("/api/learn/progress", json={"lesson_id": "b0m1l1", "completed": True, "score": 50, "results": {str(quiz): False, str(text): False}})
    assert r.status_code == 400 and "no challenge or quiz" in r.json()["detail"]
    r = client.post("/api/learn/progress", json={"lesson_id": "b0m1l1", "completed": True, "score": 50, "results": {str(quiz): False}})
    assert r.status_code == 200
    assert client.get("/api/learn/curriculum").json()["review_due"] == 0  # due tomorrow, not now
    q = client.get("/api/learn/review").json()
    assert q["items"] == [] and q["later"] == 1 and q["next_due_at"] is not None

    # the clock moves on a day: the quiz is due, with its section so the browser can run it
    import asyncio
    asyncio.get_event_loop().run_until_complete(database.execute("UPDATE player_reviews SET due_at = datetime('now', '-1 minute')"))
    q = client.get("/api/learn/review").json()
    assert [(i["lesson_id"], i["section_index"]) for i in q["items"]] == [("b0m1l1", quiz)]
    assert q["items"][0]["section"]["type"] == "quiz" and q["items"][0]["interval_days"] == 1
    assert client.get("/api/learn/curriculum").json()["review_due"] == 1

    assert client.post(f"/api/learn/review/b0m1l1/{quiz}", json={"solved": True}).json() == {"interval_days": 3}
    assert client.get("/api/learn/review").json()["items"] == []
    asyncio.get_event_loop().run_until_complete(database.execute("UPDATE player_reviews SET due_at = datetime('now', '-1 minute')"))
    assert client.post(f"/api/learn/review/b0m1l1/{quiz}", json={"solved": False}).json() == {"interval_days": 1}  # a miss restarts the ladder
    assert client.post("/api/learn/review/b0m1l1/0", json={"solved": True}).status_code == 404


def test_the_review_ladder():
    assert [next_interval(d, True) for d in (0, 1, 3, 90)] == [1, 3, 7, 90]
    assert next_interval(35, False) == REVIEW_LADDER_DAYS[0]


def test_the_puzzle_rating_places_the_player_once_it_has_settled(client):
    assert client.get("/api/learn/curriculum").json()["level"] is None  # no rated puzzles yet: nothing to say
    import asyncio
    player = client.cookies["player"]
    asyncio.get_event_loop().run_until_complete(database.set_player_value(player, "puzzle_rating", {"rating": 1180.0, "rd": 120.0, "volatility": 0.06}))
    assert client.get("/api/learn/curriculum").json()["level"] == {"puzzle_rating": 1180, "band": 3}
    assert [band_for_rating(r) for r in (300, 799, 800, 1399, 2399, 3000)] == [1, 1, 2, 3, 7, 8]
