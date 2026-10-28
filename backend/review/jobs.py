"""Review jobs: one review runs at a time on the analysis engine; the browser polls for progress.
Jobs live in memory (a review takes seconds to a minute); the finished report is stored in SQLite."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field

import chess

from ..engine.pool import pool
from ..storage.db import database
from .report import review_moves

LOGGER = logging.getLogger("chess.review.jobs")

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
FINISHED_JOB_TTL_S = 300  # guess: long enough for the browser's 0.6 s poll to read the end; the report stays in SQLite


class ReviewBusy(Exception):
    """The player already has a review queued or running for another game."""


@dataclass
class ReviewJob:
    id: str
    game_id: str
    player_id: str = field(repr=False)
    status: str = STATUS_QUEUED
    done_positions: int = 0
    total_positions: int = 0
    error: str | None = None
    report: dict | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def public(self) -> dict:
        return {
            "id": self.id, "game_id": self.game_id, "status": self.status,
            "progress": {"done": self.done_positions, "total": self.total_positions},
            "error": self.error, "report": self.report,
        }


_jobs: dict[str, ReviewJob] = {}
_by_game: dict[str, str] = {}


def get_job(player_id: str, job_id: str) -> ReviewJob | None:
    job = _jobs.get(job_id)
    return job if job and job.player_id == player_id else None


async def stored_report(player_id: str, game_id: str) -> dict | None:
    row = await database.fetch_one(
        "SELECT r.report_json FROM reviews r JOIN games g ON g.id = r.game_id WHERE r.game_id = ? AND g.player_id = ?",
        (game_id, player_id),
    )
    return json.loads(row["report_json"]) if row else None


def check_free(player_id: str) -> None:
    """Raise ReviewBusy when the player already has a review queued or running."""
    busy = next((j for j in _jobs.values() if j.player_id == player_id and j.status in (STATUS_QUEUED, STATUS_RUNNING)), None)
    if busy:
        raise ReviewBusy(f"a review of game {busy.game_id} is still {busy.status}; wait for it to finish")


def start_review(player_id: str, game_id: str, moves: list[chess.Move], *, depth: int, result: str | None, start_fen: str | None = None) -> ReviewJob:
    existing = _by_game.get(game_id)
    if existing and _jobs[existing].status in (STATUS_QUEUED, STATUS_RUNNING):
        return _jobs[existing]
    check_free(player_id)
    job = ReviewJob(id=uuid.uuid4().hex[:10], game_id=game_id, player_id=player_id, total_positions=len(moves) + 1)
    _jobs[job.id] = job
    _by_game[game_id] = job.id
    job.task = asyncio.create_task(_run(job, moves, depth, result, start_fen))
    return job


async def _run(job: ReviewJob, moves: list[chess.Move], depth: int, result: str | None, start_fen: str | None) -> None:
    job.status = STATUS_RUNNING

    async def progress(done: int, total: int) -> None:
        job.done_positions, job.total_positions = done, total

    try:
        report = await review_moves(moves, pool, depth=depth, result=result, progress=progress, start_fen=start_fen)
        job.report = report.to_dict()
        await database.execute(
            "INSERT INTO reviews(game_id, report_json) VALUES(?, ?) "
            "ON CONFLICT(game_id) DO UPDATE SET report_json = excluded.report_json, created_at = datetime('now')",
            (job.game_id, json.dumps(job.report)),
        )
        job.status = STATUS_DONE
        LOGGER.info("review done game=%s plies=%d depth=%d white=%s black=%s", job.game_id, len(moves), depth,
                    report.white.accuracy, report.black.accuracy)
    except Exception as exc:  # boundary: the job must report, not vanish
        job.status = STATUS_FAILED
        job.error = f"{type(exc).__name__}: {exc}"
        LOGGER.error("review failed game=%s", job.game_id, exc_info=True)
    asyncio.get_running_loop().call_later(FINISHED_JOB_TTL_S, _forget, job)


def _forget(job: ReviewJob) -> None:
    _jobs.pop(job.id, None)
    if _by_game.get(job.game_id) == job.id:
        _by_game.pop(job.game_id)
