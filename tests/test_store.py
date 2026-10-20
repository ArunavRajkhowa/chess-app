"""The store's one retry: Turso drops a stream left idle, and the next call reconnects and runs once more."""
from __future__ import annotations

import pytest

from backend.storage import db as D


class Conn:
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def run(self) -> str:
        if self.error:
            raise ValueError(self.error)
        return "ran"


def test_an_expired_stream_reconnects_once_and_runs_again(monkeypatch):
    store = D.Database()
    store._conn = Conn('Hrana: `api error: status=400, body={"code":"STREAM_EXPIRED"}`')
    monkeypatch.setattr(store, "_connect", lambda: Conn())
    assert store._run(lambda conn: conn.run()) == "ran"


def test_any_other_error_is_raised_without_a_retry(monkeypatch):
    store = D.Database()
    store._conn = Conn("UNIQUE constraint failed: players.google_sub")
    monkeypatch.setattr(store, "_connect", lambda: pytest.fail("must not reconnect"))
    with pytest.raises(ValueError, match="UNIQUE"):
        store._run(lambda conn: conn.run())
