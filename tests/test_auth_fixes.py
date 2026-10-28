"""Account hardening: no scrypt without a limit, sign-in counts an attempt before it hashes,
passwords have a ceiling, and the server ends a session when its cookie would."""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.routers import account as A

ME = {"email": "me@example.com", "password": "correct horse"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    auth._attempts.clear()
    A._sessions.clear()
    with TestClient(create_app()) as c:
        yield c


def test_a_guest_password_change_runs_no_scrypt_and_is_rate_limited(client, monkeypatch):
    calls = []
    monkeypatch.setattr(auth, "verify_password", lambda *a: calls.append(a) or False)
    for _ in range(auth.ATTEMPT_LIMIT):
        assert client.post("/api/account/password", json={"current": "x", "new": "xxxxxxxx"}).status_code == 401
    assert client.post("/api/account/password", json={"current": "x", "new": "xxxxxxxx"}).status_code == 429
    assert calls == []


def test_a_sign_in_is_counted_before_the_hash_runs_and_a_success_is_not(client, monkeypatch):
    client.post("/api/account/signup", json=ME)
    client.post("/api/account/signout")
    real = auth.verify_password
    seen = []

    def verify(password, stored):  # a concurrent request would check the limit while this one hashes
        seen.append(len(auth._attempts.get(("signin", "testclient"), [])))
        return real(password, stored)

    monkeypatch.setattr(auth, "verify_password", verify)
    assert client.post("/api/account/signin", json=ME).status_code == 200
    assert seen == [1]
    assert not auth._attempts.get(("signin", "testclient"))
    assert not auth._attempts.get(("signin-account", ME["email"]))


def test_a_successful_sign_in_leaves_no_empty_entry_for_the_sweep(client, monkeypatch):
    client.post("/api/account/signup", json=ME)
    client.post("/api/account/signout")
    assert client.post("/api/account/signin", json=ME).status_code == 200
    assert ("signin", "testclient") not in auth._attempts
    assert ("signin-account", ME["email"]) not in auth._attempts
    monkeypatch.setattr(auth, "SWEEP_AT", len(auth._attempts))  # the next attempt sweeps
    auth.record_attempt("signin", "1.2.3.4")  # an empty list here raised IndexError


def test_a_password_longer_than_the_ceiling_is_refused_before_hashing(client):
    long = "x" * (A.MAX_PASSWORD + 1)
    assert client.post("/api/account/signup", json={**ME, "password": long}).status_code == 422
    assert client.post("/api/account/signin", json={**ME, "password": long}).status_code == 422
    assert client.post("/api/account/password", json={"current": long, "new": "xxxxxxxx"}).status_code == 422


def test_a_session_older_than_the_cookie_lifetime_is_refused(client):
    client.post("/api/account/signup", json=ME)
    import sqlite3
    from backend import settings as s
    with sqlite3.connect(s.settings.DB_PATH) as db:
        db.execute("UPDATE sessions SET created_at = datetime('now', ?)", (f"-{A.COOKIE_DAYS + 1} days",))
    A._sessions.clear()  # a process restart
    assert client.get("/api/account").json()["email"] is None


def test_a_cached_session_expires_while_the_server_runs(client, monkeypatch):
    client.post("/api/account/signup", json=ME)
    assert client.get("/api/account").json()["email"] == ME["email"]  # cached now
    later = time.time() + (A.COOKIE_DAYS + 1) * 86400
    monkeypatch.setattr(A.time, "time", lambda: later)
    assert client.get("/api/account").json()["email"] is None


def test_waiting_hashes_do_not_hold_the_threads_the_store_uses(event_loop):
    async def burst():
        hashes = [asyncio.ensure_future(auth.hashing(auth.verify_password, "x", None)) for _ in range(20)]
        await asyncio.to_thread(lambda: None)  # a database call, as backend/storage/db.py makes one
        pending = sum(not h.done() for h in hashes)
        await asyncio.gather(*hashes)
        return pending

    assert event_loop.run_until_complete(burst()) >= 10  # the store's call did not queue behind the burst
