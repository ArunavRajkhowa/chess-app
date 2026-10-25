"""The app starts with a real engine and answers /api/health."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


def test_health_reports_engine_and_book(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "Stockfish" in body["engine"]["name"]
        assert body["openings"] is None or body["openings"] > 3500  # None while the book warms in the background
        for _ in range(240):
            if (openings := client.get("/api/health").json()["openings"]) is not None:
                break
            time.sleep(0.5)
        assert openings > 3500


def test_one_engine_process_serves_bot_moves_and_analysis(tmp_path, monkeypatch):
    from backend import settings as s
    from backend.engine.pool import pool
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr(s.settings, "ENGINE_PROCESSES", 1)
    with TestClient(create_app()) as client:
        assert pool.slots["play"] is pool.slots["analysis"]
        game = client.post("/api/play/games", json={"bot_id": "pip", "player_color": "white"}).json()
        assert client.post(f"/api/play/games/{game['id']}/move", json={"move": "e2e4"}).status_code == 200
        assert client.post("/api/coach/try", json={"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "move": "e2e4"}).status_code == 200


def test_static_fallback_stays_inside_the_build_and_api_misses_are_404(tmp_path, monkeypatch):
    from backend.app import _FRONTEND_DIST
    if not _FRONTEND_DIST.is_dir():
        pytest.skip("frontend not built")
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        r = c.get("/%2e%2e/%2e%2e/README.md")
        assert "## Credits" not in r.text  # never a file outside frontend/dist, such as the repo README
        assert c.get("/api/no-such-route").status_code == 404
        assert c.get("/learn").status_code == 200  # client-side routes still get index.html
        c.cookies.clear()  # a first visit
        assert "player=" in c.get("/").headers["set-cookie"]  # the page brings the guest cookie
        assert "set-cookie" not in c.get("/api/account").headers  # so the app's first calls reuse it
