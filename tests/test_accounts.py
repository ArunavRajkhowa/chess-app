"""Players and accounts: each browser is its own player, sign-in with Google brings a guest's data to
the account, delete-my-data leaves nothing behind, and analytics events refuse free text."""
from __future__ import annotations

import sqlite3
import time

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routers import account as A

ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36"


@pytest.fixture()
def db_file(tmp_path, monkeypatch):
    from backend import settings as s
    path = tmp_path / "t.sqlite3"
    monkeypatch.setattr(s.settings, "DB_PATH", str(path))
    return path


@pytest.fixture()
def client(db_file):
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def google(monkeypatch):
    """Google sign-in on, with a stand-in for Google's token check: the credential is the account's subject."""
    from backend import settings as s
    monkeypatch.setattr(s.settings, "GOOGLE_CLIENT_ID", "app.apps.googleusercontent.com")

    async def verify(credential: str) -> dict:
        return {"sub": credential, "email": f"{credential}@example.com"}

    monkeypatch.setattr(A, "verify_google", verify)


def new_game(client) -> str:
    r = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def reviewed_import(client) -> tuple[str, str]:
    r = client.post("/api/review/import", json={"pgn": "1. e4 e5 2. Nf3 *", "mode": "quick"})
    assert r.status_code == 200, r.text
    game_id, job_id = r.json()["game_id"], r.json()["job"]["id"]
    for _ in range(200):
        if client.get(f"/api/review/jobs/{job_id}").json()["status"] == "done":
            return game_id, job_id
        time.sleep(0.1)
    raise AssertionError("review did not finish")


def rows_of(db_file, player_id: str) -> dict[str, int]:
    conn = sqlite3.connect(db_file)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE player_id = ?", (player_id,)).fetchone()[0]
              for t in A.PLAYER_TABLES + A.PLAYER_KEYED_TABLES}
    counts["players"] = conn.execute("SELECT COUNT(*) FROM players WHERE id = ?", (player_id,)).fetchone()[0]
    conn.close()
    return counts


def test_the_first_call_makes_a_guest_with_an_httponly_cookie(client):
    r = client.get("/api/account")
    assert r.json() == {"email": None, "google_client_id": None}
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=34560000" in cookie
    assert "set-cookie" not in client.get("/api/account").headers  # the same player from now on


def test_a_player_never_sees_another_players_games_or_reviews(client):
    game_id = new_game(client)
    imported, job_id = reviewed_import(client)
    client.cookies.clear()  # another browser
    assert client.get(f"/api/play/games/{game_id}").status_code == 404
    assert client.post(f"/api/play/games/{game_id}/resign").status_code == 404
    assert client.get(f"/api/review/jobs/{job_id}").status_code == 404
    assert client.get(f"/api/review/games/{imported}").status_code == 404
    assert client.post(f"/api/review/games/{game_id}", json={"mode": "quick"}).status_code == 404
    assert client.get("/api/play/games").json()["games"] == []
    assert client.get("/api/insights/me").json()["games"] == 0


def test_no_response_body_carries_the_player_id(client):
    game_id = new_game(client)
    imported, job_id = reviewed_import(client)
    player_id = client.cookies["player"]
    for path in ("/api/account", "/api/play/games", f"/api/play/games/{game_id}", f"/api/review/jobs/{job_id}",
                 f"/api/review/games/{imported}", "/api/awards", "/api/insights/me", "/api/puzzles/stats/me"):
        r = client.get(path)
        assert r.status_code == 200 and player_id not in r.text, path


def test_signing_in_on_a_second_device_brings_the_guests_games_to_the_account(client, google):
    first = new_game(client)
    client.post("/api/vision/score", json={"mode": "find", "score": 5})
    assert client.post("/api/account/google", json={"credential": "sub-1"}).json() == {"email": "sub-1@example.com"}
    account_id = client.cookies["player"]

    client.cookies.clear()  # a phone: a new guest
    second = new_game(client)
    client.post("/api/vision/score", json={"mode": "find", "score": 9})
    guest_id = client.cookies["player"]
    assert client.post("/api/account/google", json={"credential": "sub-1"}).status_code == 200

    assert client.cookies["player"] == account_id
    assert {g["id"] for g in client.get("/api/play/games").json()["games"]} == {first, second}
    assert client.get("/api/vision").json()["best"]["find"] == 5  # a clash on one key: the account's value wins
    assert client.get("/api/account").json()["email"] == "sub-1@example.com"
    client.cookies.set("player", guest_id)
    assert client.get("/api/play/games").json()["games"] == []  # the guest is gone


def test_sign_out_starts_a_new_guest_and_signing_in_again_finds_the_account(client, google):
    game_id = new_game(client)
    client.post("/api/account/google", json={"credential": "sub-1"})
    client.post("/api/account/signout")
    assert "player" not in client.cookies
    assert client.get("/api/account").json()["email"] is None
    client.post("/api/account/google", json={"credential": "sub-1"})
    assert [g["id"] for g in client.get("/api/play/games").json()["games"]] == [game_id]


def test_one_browser_cannot_hold_two_google_accounts(client, google):
    client.post("/api/account/google", json={"credential": "sub-1"})
    r = client.post("/api/account/google", json={"credential": "sub-2"})
    assert r.status_code == 409 and "sign out first" in r.json()["detail"]


def test_sign_in_is_refused_when_the_server_has_no_google_client_id(client):
    r = client.post("/api/account/google", json={"credential": "x"})
    assert r.status_code == 503 and "GOOGLE_CLIENT_ID" in r.json()["detail"]


def test_a_google_token_must_be_verified_and_issued_for_this_app(monkeypatch, event_loop):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "GOOGLE_CLIENT_ID", "ours.apps.googleusercontent.com")
    claims = {"aud": "theirs.apps.googleusercontent.com", "iss": "https://accounts.google.com", "email_verified": "true",
              "sub": "1", "email": "a@example.com"}
    real = httpx.AsyncClient
    monkeypatch.setattr(A.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=claims)), **kw))

    def verdict():
        try:
            return event_loop.run_until_complete(A.verify_google("token"))
        except HTTPException as exc:
            return exc.status_code

    assert verdict() == 401  # another app's token
    claims["aud"] = "ours.apps.googleusercontent.com"
    assert verdict()["email"] == "a@example.com"
    claims["email_verified"] = "false"
    assert verdict() == 401


def test_delete_my_data_leaves_no_row_of_the_player_and_spares_others(client, db_file):
    new_game(client)
    other = client.cookies["player"]
    client.cookies.clear()

    new_game(client)
    imported, _ = reviewed_import(client)
    puzzle = client.get("/api/puzzles/next").json()["puzzle"]["id"]
    client.post(f"/api/puzzles/{puzzle}/attempt", json={"moves": []})
    lesson = client.get("/api/learn/lessons/b0m1l1").json()
    quiz = next(i for i, s in enumerate(lesson["sections"]) if s["type"] == "quiz")
    client.post("/api/learn/progress", json={"lesson_id": lesson["id"], "completed": True, "results": {str(quiz): False}})  # a missed quiz: a review row
    client.post("/api/vision/score", json={"mode": "find", "score": 3})
    client.post("/api/events", json={"name": "app.opened", "props": {"display": "browser"}})
    me = client.cookies["player"]
    assert all(rows_of(db_file, me).values())  # something in every table

    assert client.delete("/api/account").json() == {"deleted": True}
    assert not any(rows_of(db_file, me).values())
    assert sqlite3.connect(db_file).execute("SELECT COUNT(*) FROM reviews WHERE game_id = ?", (imported,)).fetchone()[0] == 0
    assert rows_of(db_file, other)["games"] == 1
    assert "player" not in client.cookies


def test_every_table_with_a_player_id_is_merged_and_deleted(client, db_file):
    conn = sqlite3.connect(db_file)
    tables = [t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
              if "player_id" in {c[1] for c in conn.execute(f"PRAGMA table_info({t})")}]
    assert sorted(tables) == sorted(A.PLAYER_TABLES + A.PLAYER_KEYED_TABLES)


def test_an_event_is_stored_with_its_platform_and_without_the_user_agent(client, db_file):
    r = client.post("/api/events", json={"name": "page.viewed", "props": {"page": "puzzles"}}, headers={"user-agent": ANDROID_UA})
    assert r.json() == {"ok": True}
    row = sqlite3.connect(db_file).execute("SELECT name, platform, props_json FROM events").fetchone()
    assert row == ("page.viewed", "android", '{"page": "puzzles"}')


@pytest.mark.parametrize("body", [
    {"name": "page.typed"},
    {"name": "page.viewed", "props": {"email": "x"}},
    {"name": "page.viewed", "props": {"page": "me@example.com"}},
    {"name": "page.viewed", "props": {"page": "John Smith"}},
    {"name": "page.viewed", "props": {"page": "x" * 65}},
    {"name": "page.viewed", "props": {"page": {"nested": 1}}},
])
def test_an_event_with_an_unknown_name_key_or_free_text_is_refused(client, body):
    assert client.post("/api/events", json=body).status_code == 422


def test_a_single_player_file_gains_player_ids_and_its_old_rows_belong_to_nobody(db_file):
    old = sqlite3.connect(db_file)
    old.executescript("""
        CREATE TABLE games (id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')), player_color TEXT NOT NULL, bot_id TEXT, time_control TEXT,
            status TEXT NOT NULL, result TEXT, termination TEXT, pgn TEXT NOT NULL DEFAULT '', moves_json TEXT NOT NULL DEFAULT '[]',
            opening_eco TEXT, opening_name TEXT);
        CREATE TABLE puzzle_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
            puzzle_id TEXT NOT NULL, solved INTEGER NOT NULL, seconds REAL, rating_before REAL, rating_after REAL, mode TEXT NOT NULL DEFAULT 'rated');
        CREATE TABLE player (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
        INSERT INTO games(id, player_color, bot_id, status) VALUES ('legacy', 'white', 'pip', 'active');
    """)
    old.commit()
    old.close()
    with TestClient(create_app()) as client:
        assert client.get("/api/play/games").json()["games"] == []
        new_game(client)
        assert len(client.get("/api/play/games").json()["games"]) == 1
