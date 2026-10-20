"""Opening courses: every course file loads whole, and the API serves the index, one course and a 404."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.openings.courses import COURSES_DIR, load_courses


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def test_every_course_file_loads_without_drops(caplog):
    load_courses.cache_clear()
    with caplog.at_level(logging.WARNING, logger="chess.courses"):
        courses = load_courses()
    assert not caplog.records, [r.getMessage() for r in caplog.records]
    files = sorted(COURSES_DIR.glob("*.json"))
    assert len(files) == len(courses) >= 6
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        c = courses[raw["id"]]
        assert (len(c.lines), len(c.traps)) == (len(raw["lines"]), len(raw["traps"])), path.name
        assert c.lines and c.traps, path.name
    assert {c.side for c in courses.values()} == {"white", "black"}


def test_course_api(client):
    index = client.get("/api/openings/courses").json()["courses"]
    assert {"italian-game", "caro-kann"} <= {c["id"] for c in index}
    italian = client.get("/api/openings/courses/italian-game").json()
    assert italian["side"] == "white" and italian["ideas"]["white"] and italian["structures"]
    first = italian["lines"][0]
    assert [m["san"] for m in first["moves"][:3]] == ["e4", "e5", "Nf3"]
    assert all(m["fen"] for m in first["moves"]) and any(m["comment"] for m in first["moves"])
    legal = next(t for t in italian["traps"] if t["id"] == "legal-mate")
    assert legal["mistake_by"] == "black" and legal["moves"][legal["mistake_ply"] - 1]["san"] == "Bxd1" and legal["punishment"]
    missing = client.get("/api/openings/courses/no-such-course")
    assert missing.status_code == 404 and "no-such-course" in missing.json()["detail"]
