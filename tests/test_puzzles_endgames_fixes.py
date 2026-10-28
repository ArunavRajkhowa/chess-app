"""Puzzle Rush and endgame records accept only declared values; a puzzle is rated once."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from tests.test_puzzles import client  # noqa: F401  (the fixture library)


def test_rush_finish_takes_only_declared_modes_and_possible_scores(client):  # noqa: F811
    ok = {"mode": "3m", "score": 7, "wrong": 1, "seconds": 180}
    assert client.post("/api/puzzles/rush/finish", json=ok).status_code == 200
    for bad in ({"mode": "x" * 100}, {"score": 1_000_000_000}, {"score": -5}, {"wrong": -1}, {"seconds": -3}):
        assert client.post("/api/puzzles/rush/finish", json={**ok, **bad}).status_code == 422, bad
    assert client.get("/api/puzzles/stats/me").json()["rush_best"]["3m"] == 7


def test_a_rated_puzzle_changes_the_rating_only_once(client):  # noqa: F811
    p = client.get("/api/puzzles/p3").json()["puzzle"]
    first = client.post("/api/puzzles/p3/attempt", json={"moves": p["moves"][1::2]}).json()
    again = client.post("/api/puzzles/p3/attempt", json={"moves": p["moves"][1::2]}).json()
    assert first["delta"] > 0 and again["solved"] and again["delta"] == 0
    assert client.get("/api/puzzles/next").json()["player_rating"] == first["rating_after"]


@pytest.fixture()
def eg_client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_endgame_attempt_mode_is_practice_or_challenge(eg_client):
    body = {"key": "mate-two-rooks", "line": [], "seconds": 1}
    assert eg_client.post("/api/endgames/attempt", json={**body, "mode": "challenge"}).status_code == 200
    assert eg_client.post("/api/endgames/attempt", json={**body, "mode": "x" * 1000}).status_code == 422
