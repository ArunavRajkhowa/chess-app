"""Review jobs: a PGN size and ply cap, one pending review per player, finished jobs leave memory."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.review import jobs
from backend.routers import review


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend import settings as s
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def _cycle(plies: int) -> str:
    sans = ["Nf3", "Nf6", "Ng1", "Ng8"]
    out = []
    for i in range(plies):
        if i % 2 == 0:
            out.append(f"{i // 2 + 1}.")
        out.append(sans[i % 4])
    return " ".join(out) + " *"


def test_a_pgn_over_the_ply_cap_is_refused_and_not_stored(client):
    r = client.post("/api/review/import", json={"pgn": _cycle(review.MAX_PLIES + 1), "mode": "quick"})
    assert r.status_code == 400
    assert str(review.MAX_PLIES + 1) in r.json()["detail"] and str(review.MAX_PLIES) in r.json()["detail"]
    assert client.get("/api/play/games").json()["games"] == []


def test_an_oversized_pgn_body_is_refused(client):
    r = client.post("/api/review/import", json={"pgn": "1. e4 e5 " + " " * review.MAX_PGN_CHARS, "mode": "quick"})
    assert r.status_code == 422


def test_one_pending_review_per_player(client):
    first = client.post("/api/review/import", json={"pgn": _cycle(40), "mode": "deep"}).json()
    assert first["job"]["status"] in ("queued", "running")
    second = client.post("/api/review/import", json={"pgn": _cycle(8), "mode": "quick"})
    assert second.status_code == 429
    assert len(client.get("/api/play/games").json()["games"]) == 1  # the refused import stored nothing
    again = client.post(f"/api/review/games/{first['game_id']}", json={"mode": "deep"}).json()
    assert again["id"] == first["job"]["id"]  # the same game still returns its own running job


def test_a_finished_job_leaves_memory_and_the_report_stays_stored(client, monkeypatch):
    monkeypatch.setattr(jobs, "FINISHED_JOB_TTL_S", 0)
    r = client.post("/api/review/import", json={"pgn": "1. f3 e5 2. g4 Qh4# 0-1", "mode": "quick"}).json()
    job_id, t0 = r["job"]["id"], time.time()
    while client.get(f"/api/review/jobs/{job_id}").status_code == 200:
        assert time.time() - t0 < 120, "job was never dropped"
        time.sleep(0.3)
    assert job_id not in jobs._jobs and r["game_id"] not in jobs._by_game
    assert client.get(f"/api/review/games/{r['game_id']}").json()["report"]["moves"]


def test_an_import_that_loses_the_race_gets_429_and_stores_nothing(client, monkeypatch):
    seen: list[str] = []
    check, parse = jobs.check_free, review._parse_pgn

    def record(player_id: str) -> None:
        seen.append(player_id)
        check(player_id)

    def parse_while_another_import_starts(pgn: str):
        # another import by the same player passes its check and starts a review during this parse
        jobs._jobs["rival"] = jobs.ReviewJob(id="rival", game_id="rivalgame", player_id=seen[0])
        return parse(pgn)

    monkeypatch.setattr(jobs, "check_free", record)
    monkeypatch.setattr(review, "_parse_pgn", parse_while_another_import_starts)
    try:
        r = client.post("/api/review/import", json={"pgn": _cycle(8), "mode": "quick"})
    finally:
        jobs._jobs.pop("rival", None)
    assert r.status_code == 429
    assert client.get("/api/play/games").json()["games"] == []
