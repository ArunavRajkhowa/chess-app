"""The app starts with a real engine and answers /api/health."""
from __future__ import annotations

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
        assert body["openings"] > 3500


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
