"""Glicko-2 maths and the puzzle API on a tiny fixture library."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import datetime as dt

from backend.puzzles.glicko import Rating, expected_score, update
from backend.routers.puzzles import _streak


def test_streak_counts_consecutive_days():
    today = dt.date(2026, 10, 16)
    assert _streak([], today) == 0
    assert _streak(["2026-10-16"], today) == 1
    assert _streak(["2026-10-14", "2026-10-15"], today) == 2  # yesterday's streak still alive today
    assert _streak(["2026-10-12", "2026-10-13"], today) == 0
    assert _streak(["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"], today) == 4


def test_glicko_moves_in_the_right_direction():
    r = Rating()
    win = update(r, Rating(rating=1500, rd=80), 1.0)
    loss = update(r, Rating(rating=1500, rd=80), 0.0)
    assert win.rating > r.rating > loss.rating
    assert win.rd < r.rd
    # beating a much stronger puzzle is worth more than beating a weak one
    assert update(r, Rating(rating=2000, rd=80), 1.0).rating > update(r, Rating(rating=800, rd=80), 1.0).rating
    assert 0.49 < expected_score(Rating(1500, 50), Rating(1500, 50)) < 0.51


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    from backend.puzzles import store
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    pdir = tmp_path / "puzzles"
    pdir.mkdir()
    rows = [
        {"id": "p1", "fen": "6k1/p4ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1", "moves": ["a7a6", "d1d8"], "rating": 600, "rd": 80, "themes": ["mateIn1", "backRankMate", "short"]},
        {"id": "p2", "fen": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3", "moves": ["g8f6", "h5f7"], "rating": 700, "rd": 80, "themes": ["mateIn1", "opening"]},
        {"id": "p3", "fen": "8/8/8/8/8/3k4/8/4K2R b K - 0 1", "moves": ["d3e3", "h1h3"], "rating": 1900, "rd": 80, "themes": ["endgame", "rookEndgame"]},
    ]
    (pdir / "fixture.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(store, "PUZZLES_DIR", pdir)
    store.load_library.cache_clear()
    from backend.app import create_app
    with TestClient(create_app()) as c:
        yield c
    store.load_library.cache_clear()


def test_next_attempt_and_stats(client):
    t = client.get("/api/puzzles/themes").json()
    assert t["total"] == 3 and any(x["key"] == "mateIn1" for x in t["themes"])
    nxt = client.get("/api/puzzles/next").json()
    assert nxt["puzzle"]["id"] in {"p1", "p2", "p3"}
    assert nxt["player_rating"] == 1200
    a = client.post(f"/api/puzzles/{nxt['puzzle']['id']}/attempt", json={"moves": nxt["puzzle"]["moves"][1::2], "seconds": 4.2}).json()
    assert a["solved"] and a["delta"] > 0 and a["rating_after"] > 1200
    themed = client.get("/api/puzzles/next?themes=rookEndgame").json()
    assert themed["puzzle"]["id"] == "p3"
    custom = client.get("/api/puzzles/next?min_rating=500&max_rating=650").json()
    assert custom["puzzle"]["id"] == "p1"
    assert client.post("/api/puzzles/p1/attempt", json={"moves": ["d1d7"], "mode": "custom"}).json()["solved"] is False
    s = client.get("/api/puzzles/stats/me").json()
    assert s["attempts"] == 1 and s["solved"] == 1
    d = client.get("/api/puzzles/daily").json()
    assert d["puzzle"]["id"] and d["streak"] == 0 and d["solved_today"] is False
    solved = client.post(f"/api/puzzles/{d['puzzle']['id']}/attempt", json={"moves": d["puzzle"]["moves"][1::2], "mode": "daily"}).json()
    assert solved["solved"] and solved["streak"] == 1
    assert client.get("/api/puzzles/daily").json()["solved_today"] is True
    rush = client.get("/api/puzzles/rush/start?mode=3m").json()
    assert rush["strikes"] == 3 and 1 <= len(rush["puzzles"]) <= 3
    fin = client.post("/api/puzzles/rush/finish", json={"mode": "3m", "score": 7, "wrong": 3, "seconds": 180}).json()
    assert fin["new_best"] is True and fin["best"] == 7
    assert client.get("/api/puzzles/nope").status_code == 404


def test_attempts_are_judged_from_the_moves_not_the_client(client):
    before = client.get("/api/puzzles/stats/me").json()["rating"]
    for moves in ([], ["a1a2"], ["c4f7"]):  # nothing played, an illegal move, a legal wrong move
        assert client.post("/api/puzzles/p2/attempt", json={"moves": moves}).json()["solved"] is False
    assert client.get("/api/puzzles/stats/me").json()["rating"] < before
    assert client.post("/api/puzzles/p2/attempt", json={"moves": ["h5f7"], "hinted": True}).json()["solved"] is False
    assert client.post("/api/puzzles/p2/attempt", json={"moves": ["h5f7"]}).json()["solved"] is True
    assert client.post("/api/puzzles/mistake-nope-3/attempt", json={"moves": ["e2e4"], "mode": "mistakes"}).status_code == 404


def test_vision_scores(client):
    assert client.get("/api/vision").json()["best"] == {"find": 0, "name": 0}
    r = client.post("/api/vision/score", json={"mode": "find", "score": 21}).json()
    assert r["new_best"] and r["best"]["find"] == 21
    assert client.post("/api/vision/score", json={"mode": "find", "score": 10}).json()["new_best"] is False
    assert client.post("/api/vision/score", json={"mode": "x", "score": 1}).status_code == 422


def test_awards_are_queries(client):
    a = client.get("/api/awards").json()
    assert a["earned"] == 0 and a["total"] >= 20
    client.post("/api/puzzles/p1/attempt", json={"moves": ["d1d8"], "seconds": 3})
    a = client.get("/api/awards").json()
    assert any(x["key"] == "tactics-newbie" and x["earned"] for x in a["awards"])
    assert a["facts"]["puzzles_solved"] == 1


def test_loader_replays_puzzles_and_drops_broken_ones(tmp_path, monkeypatch, caplog):
    from backend.puzzles import store
    good = {"id": "ok", "fen": "6k1/p4ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1", "moves": ["a7a6", "d1d8"], "rating": 600, "themes": []}
    lines = [
        json.dumps(good),
        "{not json",
        json.dumps({**good, "id": "illegal", "moves": ["a7a6", "d1d9"]}),
        json.dumps({**good, "id": "ends-on-reply", "moves": ["a7a6", "d1d7", "g8h8"]}),
        json.dumps({"id": "no-fen", "moves": ["a7a6", "d1d8"]}),
    ]
    (tmp_path / "mixed.jsonl").write_text("\n".join(lines))
    monkeypatch.setattr(store, "PUZZLES_DIR", tmp_path)
    store.load_library.cache_clear()
    try:
        assert [p.id for p in store.load_library().all] == ["ok"]
    finally:
        store.load_library.cache_clear()
    dropped = [r.getMessage() for r in caplog.records if "dropped puzzle" in r.getMessage()]
    assert len(dropped) == 4 and all("mixed.jsonl" in m for m in dropped)
    assert any("illegal" in m for m in dropped) and any("ends-on-reply" in m for m in dropped)
