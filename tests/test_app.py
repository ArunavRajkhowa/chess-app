"""The app starts with a real engine and answers /api/health."""
from __future__ import annotations

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
        assert body["openings"] > 3500
