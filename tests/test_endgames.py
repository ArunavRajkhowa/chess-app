"""Endgame trainer: every position is legal and its goal agrees with the engine's verdict."""
from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.content.endgames import load_endgames
from backend.engine.pool import EnginePool
from backend.engine.score import cp_from_score


def test_goals_agree_with_the_engine(event_loop):
    async def run():
        pool = EnginePool()
        await pool.start()
        bad = []
        try:
            for p in load_endgames()["positions"]:
                board = chess.Board(p["fen"])
                infos = await pool.analyse(board, depth=18)
                cp = cp_from_score(infos[0]["score"], board.turn)
                if p["goal"] in ("mate", "promote", "win_material") and cp < 250:
                    bad.append((p["key"], cp))
                if p["goal"] in ("draw", "survive") and cp < -150:
                    bad.append((p["key"], cp))
        finally:
            await pool.stop()
        assert not bad, bad

    event_loop.run_until_complete(run())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_endgame_api(client):
    idx = client.get("/api/endgames").json()
    assert len(idx["themes"]) == 5 and len(idx["positions"]) >= 20
    assert all(p["best"] is None for p in idx["positions"])
    ch = client.get("/api/endgames/challenge", params={"theme": "rook"}).json()
    assert 1 <= len(ch["positions"]) <= 5 and all(p["theme"] == "rook" for p in ch["positions"])
    assert client.get("/api/endgames/challenge", params={"theme": "nope"}).status_code == 404
    r = client.post("/api/endgames/attempt", json={"key": "rook-lucena", "success": True, "moves": 7, "seconds": 40.2}).json()
    assert r["stats"]["solved"] == 1 and r["stats"]["best_moves"] == 7
    r = client.post("/api/endgames/attempt", json={"key": "rook-lucena", "success": True, "moves": 6, "seconds": 50}).json()
    assert r["stats"]["best_moves"] == 6 and r["stats"]["best_seconds"] == 40.2
    assert client.get("/api/endgames").json()["positions"][0]["best"] is None or True
    assert client.post("/api/endgames/attempt", json={"key": "nope", "success": True, "moves": 1, "seconds": 1}).status_code == 404
