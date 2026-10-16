from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.content.games import load_games


def test_seed_games_load_with_comments():
    games = load_games()
    g = next(x for x in games if x.white == "Paul Morphy")
    assert g.result == "1-0" and g.plies[-1]["san"] == "Rd8#"
    assert len(g.key_moments) >= 4 and "development" in g.themes


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_games_api_and_guess(client):
    idx = client.get("/api/games").json()
    assert idx["total"] >= 1 and any(t["key"] == "attack" for t in idx["themes"])
    gid = idx["games"][0]["id"]
    d = client.get(f"/api/games/{gid}").json()
    assert d["moves"][0]["san"] == "e4" and d["pgn"].startswith("[Event")
    r = client.post("/api/games/guess", json={"game_id": gid, "ply": 1, "move": "e2e4"}).json()
    assert r["verdict"] == "master" and r["points"] == 3
    r = client.post("/api/games/guess", json={"game_id": gid, "ply": 1, "move": "d2d4"}).json()
    assert r["verdict"] in ("excellent", "good") and r["master_san"] == "e4"
    r = client.post("/api/games/guess", json={"game_id": gid, "ply": 31, "move": "b3b8"}).json()
    assert r["verdict"] == "master"
    assert client.post("/api/games/guess", json={"game_id": gid, "ply": 1, "move": "e2e5"}).status_code == 400
    assert client.get("/api/games?theme=attack").json()["games"]
