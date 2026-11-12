"""Notes: a player leaves one, sees only their own, and only the owner key lists and resolves them."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.settings import settings

NOTE = {"page": "/learn/b0m1l1", "anchor": "Learn · The rook", "quote": "a rook moves diagonally", "kind": "wrong", "note": "rooks move straight"}
OWNER = {"x-owner-key": "owner-secret"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr(settings, "NOTES_OWNER_KEY", "owner-secret")
    auth._attempts.clear()
    with TestClient(create_app()) as c:
        yield c


def test_a_note_is_stored_and_its_author_sees_the_resolution(client):
    assert client.post("/api/notes", json=NOTE).json() == {"ok": True}
    [mine] = client.get("/api/notes/mine").json()["notes"]
    assert (mine["kind"], mine["note"], mine["status"], mine["resolution"]) == ("wrong", "rooks move straight", "open", None)

    [listed] = client.get("/api/notes", headers=OWNER).json()["notes"]
    assert listed["quote"] == NOTE["quote"] and "player_id" not in listed
    assert client.post(f"/api/notes/{listed['id']}/resolve", json={"status": "done", "resolution": "fixed"}, headers=OWNER).json() == {"ok": True}

    [mine] = client.get("/api/notes/mine").json()["notes"]
    assert (mine["status"], mine["resolution"]) == ("done", "fixed") and mine["resolved"]
    assert client.get("/api/notes", headers=OWNER).json()["notes"] == []
    assert len(client.get("/api/notes?status=done", headers=OWNER).json()["notes"]) == 1


@pytest.mark.parametrize("change", [{"kind": "rant"}, {"note": "x"}, {"note": "   a  "}, {"note": "x" * 2001}, {"page": ""}, {"quote": "q" * 601}])
def test_a_bad_note_is_refused(client, change):
    assert client.post("/api/notes", json={**NOTE, **change}).status_code == 422


def test_another_player_never_sees_my_notes(client):
    client.post("/api/notes", json=NOTE)
    client.cookies.clear()  # another browser
    assert client.get("/api/notes/mine").json() == {"notes": []}


def test_the_owner_routes_need_the_key(client, monkeypatch):
    client.post("/api/notes", json=NOTE)
    assert client.get("/api/notes").status_code == 403
    assert client.get("/api/notes", headers={"x-owner-key": "guess"}).status_code == 403
    assert client.post("/api/notes/1/resolve", json={"status": "done"}).status_code == 403
    assert client.post("/api/notes/99/resolve", json={"status": "done"}, headers=OWNER).status_code == 404
    monkeypatch.setattr(settings, "NOTES_OWNER_KEY", "")
    assert client.get("/api/notes", headers={"x-owner-key": ""}).status_code == 404


def test_notes_are_rate_limited_per_player(client):
    for _ in range(10):
        assert client.post("/api/notes", json=NOTE).status_code == 200
    assert client.post("/api/notes", json=NOTE).status_code == 429
