"""Learn progress takes no free-form state; play rejects a finished start and stores standard castling."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_progress_drops_free_form_state(client):
    lesson_id = "b0m3l2"
    r = client.post("/api/learn/progress", json={"lesson_id": lesson_id, "completed": True, "state": {"x": "A" * 10_000}})
    assert r.status_code == 200
    row = client.get("/api/learn/progress").json()["progress"][lesson_id]
    assert "state" not in row and row["attempts"] == 1


def test_start_position_past_fifty_moves_is_rejected(client):
    r = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white", "fen": "4k3/8/8/8/8/8/4P3/4K3 w - - 120 80"})
    assert r.status_code == 400


def test_king_takes_rook_is_stored_as_castling(client):
    fen = "r3k2r/pppqbppp/2np1n2/4p3/4P3/2NP1N2/PPPQBPPP/R3K2R w KQkq - 0 1"
    gid = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white", "fen": fen}).json()["id"]
    r = client.post(f"/api/play/games/{gid}/move", json={"move": "e1h1"})
    assert r.status_code == 200
    moves = client.get(f"/api/play/games/{gid}").json()["moves"]
    assert moves[0]["uci"] == "e1g1"
