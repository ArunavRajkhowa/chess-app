"""Players and accounts: each browser is its own player, signing in (email and password, or Google)
brings a guest's data to the account, delete-my-data leaves nothing behind, and analytics events
refuse free text."""
from __future__ import annotations

import base64
import re
import sqlite3
import time

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import auth, mail
from backend.app import create_app
from backend.routers import account as A

ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36"


@pytest.fixture()
def db_file(tmp_path, monkeypatch):
    from backend import settings as s
    path = tmp_path / "t.sqlite3"
    monkeypatch.setattr(s.settings, "DB_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def fresh_limits():
    auth._attempts.clear()
    A._sessions.clear()


@pytest.fixture()
def client(db_file):
    with TestClient(create_app()) as c:
        yield c


ME = {"email": "me@example.com", "password": "correct horse"}


def sign_up(client, **override) -> None:
    r = client.post("/api/account/signup", json={**ME, **override})
    assert r.status_code == 200, r.text


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
    assert r.json() == {"email": None, "has_password": False, "google_client_id": None}
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=34560000" in cookie and "Secure" not in cookie
    assert "set-cookie" not in client.get("/api/account").headers  # the same player from now on


def test_cookies_are_secure_behind_https(db_file):
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert "Secure" in client.get("/api/account").headers["set-cookie"]
        r = client.post("/api/account/signup", json=ME)
        session = next(c for c in r.headers.get_list("set-cookie") if c.startswith("session="))
        assert "Secure" in session and "HttpOnly" in session and "SameSite=lax" in session


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
    assert "session" in client.cookies and "player" not in client.cookies

    client.cookies.clear()  # a phone: a new guest
    second = new_game(client)
    client.post("/api/vision/score", json={"mode": "find", "score": 9})
    guest_id = client.cookies["player"]
    assert client.post("/api/account/google", json={"credential": "sub-1"}).status_code == 200

    assert {g["id"] for g in client.get("/api/play/games").json()["games"]} == {first, second}
    assert client.get("/api/vision").json()["best"]["find"] == 5  # a clash on one key: the account's value wins
    assert client.get("/api/account").json() == {"email": "sub-1@example.com", "has_password": False, "google_client_id": "app.apps.googleusercontent.com"}
    client.cookies.clear()
    client.cookies.set("player", guest_id)
    assert client.get("/api/play/games").json()["games"] == []  # the guest is gone


def test_sign_out_starts_a_new_guest_and_signing_in_again_finds_the_account(client, google):
    game_id = new_game(client)
    client.post("/api/account/google", json={"credential": "sub-1"})
    client.post("/api/account/signout")
    assert "player" not in client.cookies and "session" not in client.cookies
    assert client.get("/api/account").json()["email"] is None
    client.post("/api/account/google", json={"credential": "sub-1"})
    assert [g["id"] for g in client.get("/api/play/games").json()["games"]] == [game_id]


def test_sign_up_makes_an_account_that_signs_in_from_a_second_device_and_brings_its_games(client):
    first = new_game(client)
    sign_up(client)
    assert client.get("/api/account").json() == {"email": "me@example.com", "has_password": True, "google_client_id": None}
    assert "session" in client.cookies and "player" not in client.cookies

    client.cookies.clear()
    second = new_game(client)
    r = client.post("/api/account/signin", json={"email": "ME@example.com ", "password": ME["password"]})  # case and spaces do not matter
    assert r.json() == {"email": "me@example.com"}
    assert {g["id"] for g in client.get("/api/play/games").json()["games"]} == {first, second}


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(client):
    sign_up(client)
    client.post("/api/account/signout")
    wrong = client.post("/api/account/signin", json={"email": ME["email"], "password": "not it, sorry"})
    unknown = client.post("/api/account/signin", json={"email": "nobody@example.com", "password": ME["password"]})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json() == {"detail": A.WRONG_SIGN_IN}


def test_a_short_password_a_taken_email_and_a_bad_address_are_refused(client):
    assert client.post("/api/account/signup", json={**ME, "password": "seven77"}).status_code == 422
    assert client.post("/api/account/signup", json={**ME, "email": "not-an-address"}).status_code == 422
    sign_up(client)
    client.post("/api/account/signout")
    assert client.post("/api/account/signup", json={**ME, "email": "Me@Example.com"}).status_code == 409


def test_ten_failed_sign_ins_from_one_address_lock_it_out(client):
    sign_up(client)
    client.post("/api/account/signout")
    for _ in range(auth.ATTEMPT_LIMIT):
        assert client.post("/api/account/signin", json={**ME, "password": "wrong wrong"}).status_code == 401
    r = client.post("/api/account/signin", json=ME)  # the right password no longer helps
    assert r.status_code == 429 and "15 minutes" in r.json()["detail"]


def test_sign_out_everywhere_ends_the_other_devices_session(client):
    sign_up(client)
    laptop = client.cookies["session"]
    client.cookies.clear()
    client.post("/api/account/signin", json=ME)
    client.post("/api/account/signout", json={"everywhere": True})
    client.cookies.set("session", laptop)
    assert client.get("/api/account").json()["email"] is None  # the laptop is a guest again


def test_changing_the_password_needs_the_current_one_and_keeps_only_this_session(client):
    sign_up(client)
    phone = client.cookies["session"]
    client.cookies.clear()
    client.post("/api/account/signin", json=ME)
    assert client.post("/api/account/password", json={"current": "wrong wrong", "new": "new password"}).status_code == 401
    assert client.post("/api/account/password", json={"current": ME["password"], "new": "new password"}).json() == {"ok": True}
    assert client.get("/api/account").json()["email"] == ME["email"]
    client.cookies.clear()
    client.cookies.set("session", phone)
    assert client.get("/api/account").json()["email"] is None
    assert client.post("/api/account/signin", json={**ME, "password": "new password"}).status_code == 200


def test_a_reset_link_is_logged_without_a_mail_server_and_works_once(client, caplog, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "PUBLIC_URL", "http://testserver")
    sign_up(client)
    client.post("/api/account/signout")
    with caplog.at_level("WARNING", logger="chess.mail"):
        assert client.post("/api/account/reset", json={"email": "Nobody@example.com"}).json() == {"ok": True}  # same answer
        assert client.post("/api/account/reset", json={"email": ME["email"]}).json() == {"ok": True}
    links = re.findall(r"http://testserver/settings\?reset=(\S+)", caplog.text)
    assert len(links) == 1 and ME["email"] not in caplog.text
    token = links[0]
    assert client.post("/api/account/reset/confirm", json={"token": token, "password": "after reset"}).json() == {"email": ME["email"]}
    assert client.get("/api/account").json()["email"] == ME["email"]
    assert client.post("/api/account/reset/confirm", json={"token": token, "password": "once more"}).status_code == 401  # used
    assert client.post("/api/account/reset/confirm", json={"token": "nonsense", "password": "once more"}).status_code == 401
    client.post("/api/account/signout")
    assert client.post("/api/account/signin", json={**ME, "password": "after reset"}).status_code == 200


def test_an_accounts_old_guest_cookie_is_not_a_credential(client):
    client.get("/api/account")
    guest_id = client.cookies["player"]
    sign_up(client)
    client.post("/api/account/password", json={"current": ME["password"], "new": "new password"})
    client.cookies.clear()
    client.cookies.set("player", guest_id)
    r = client.get("/api/account")
    assert r.json()["email"] is None and r.cookies["player"] != guest_id  # only the session reaches the account


def test_a_reset_link_carries_no_player_id_and_a_bad_expiry_is_refused(client, caplog, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "PUBLIC_URL", "https://chess.example.com/")
    client.get("/api/account")
    player_id = client.cookies["player"]
    sign_up(client)
    with caplog.at_level("WARNING", logger="chess.mail"):
        client.post("/api/account/reset", json={"email": ME["email"]})
    token = re.findall(r"https://chess\.example\.com/settings\?reset=(\S+)", caplog.text)[0]
    assert player_id not in base64.urlsafe_b64decode(token.split(".")[0]).decode()
    bad = base64.urlsafe_b64encode(b"me@example.com:soon").decode() + ".sig"
    assert client.post("/api/account/reset/confirm", json={"token": bad, "password": "12345678"}).status_code == 401


def test_a_reset_link_is_never_built_from_a_foreign_host_header(client, caplog):
    sign_up(client)
    with caplog.at_level("WARNING"):
        assert client.post("/api/account/reset", json=ME, headers={"host": "evil.example"}).json() == {"ok": True}
        assert "evil.example/settings" not in caplog.text and "PUBLIC_URL" in caplog.text
        client.post("/api/account/reset", json=ME, headers={"host": "localhost:8765"})
    assert "http://localhost:8765/settings?reset=" in caplog.text


def test_the_rate_limit_keys_on_the_address_the_platform_appended(client):
    sign_up(client)
    client.post("/api/account/signout")
    for i in range(auth.ATTEMPT_LIMIT):  # the client forges the leftmost entry; the proxy appends the real one
        r = client.post("/api/account/signin", json={**ME, "password": "wrong wrong"}, headers={"x-forwarded-for": f"10.0.0.{i}, 203.0.113.7"})
        assert r.status_code == 401
    assert client.post("/api/account/signin", json=ME, headers={"x-forwarded-for": "10.9.9.9, 203.0.113.7"}).status_code == 429
    assert client.post("/api/account/signin", json=ME, headers={"x-forwarded-for": "198.51.100.1"}).status_code == 200
    auth.over_limit("signin", "192.0.2.99")
    assert ("signin", "192.0.2.99") not in auth._attempts  # an address with no failures keeps no entry


def test_sign_up_is_rate_limited_per_address(client):
    sign_up(client)
    for _ in range(auth.ATTEMPT_LIMIT - 1):
        assert client.post("/api/account/signup", json=ME).status_code == 409
    assert client.post("/api/account/signup", json=ME).status_code == 429


def test_google_sign_in_is_refused_while_signed_in_to_a_password_account(client, db_file, google):
    sign_up(client)
    r = client.post("/api/account/google", json={"credential": "sub-9"})
    assert r.status_code == 409 and r.json()["detail"] == "this browser is already signed in: sign out first"
    assert sqlite3.connect(db_file).execute("SELECT COUNT(*) FROM players WHERE email = ?", (ME["email"],)).fetchone()[0] == 1


def test_a_google_sign_in_cannot_take_over_an_unverified_password_account(client, google):
    sign_up(client, email="sub-1@example.com")
    client.post("/api/account/signout")
    r = client.post("/api/account/google", json={"credential": "sub-1"})
    assert r.status_code == 409 and "reset the password" in r.json()["detail"]


def test_mail_goes_over_smtp_with_starttls_when_a_host_is_set(monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(s.settings, "SMTP_USER", "login")
    monkeypatch.setattr(s.settings, "SMTP_PASSWORD", "key")
    monkeypatch.setattr(s.settings, "MAIL_FROM", "coach@example.com")
    calls = []

    class SMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            calls.append(("quit",))
        def starttls(self):
            calls.append(("starttls",))
        def login(self, user, password):
            calls.append(("login", user, password))
        def send_message(self, msg):
            calls.append(("send", msg["From"], msg["To"], msg["Subject"]))

    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    mail.send("you@example.com", "Hello", "body")
    assert calls == [("connect", "smtp.example.com", 587), ("starttls",), ("login", "login", "key"),
                     ("send", "coach@example.com", "you@example.com", "Hello"), ("quit",)]


def test_password_hashes_verify_and_a_missing_hash_never_matches():
    stored = auth.hash_password("correct horse")
    assert stored.startswith("scrypt$32768$8$1$") and auth.verify_password("correct horse", stored)
    assert not auth.verify_password("wrong", stored) and not auth.verify_password("", None)


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
    assert client.post("/api/plans", json={"goal": "rook endgames"}).json()["plan"], "a plan row"
    me = client.cookies["player"]
    sign_up(client)  # a session row and an email
    assert all(rows_of(db_file, me).values())  # something in every table

    assert client.delete("/api/account").json() == {"deleted": True}
    assert not any(rows_of(db_file, me).values())
    assert sqlite3.connect(db_file).execute("SELECT COUNT(*) FROM reviews WHERE game_id = ?", (imported,)).fetchone()[0] == 0
    assert sqlite3.connect(db_file).execute("SELECT COUNT(*) FROM players WHERE email = ?", (ME["email"],)).fetchone()[0] == 0
    assert rows_of(db_file, other)["games"] == 1
    assert "player" not in client.cookies and "session" not in client.cookies


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
