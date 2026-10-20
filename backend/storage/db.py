"""The store: players, their games, reviews, puzzle attempts, lesson progress, values and analytics
events. A local SQLite file, or a Turso database when TURSO_DATABASE_URL is set; libsql speaks to
both. One connection, one writer; every call runs on a thread so the event loop never blocks."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import libsql

from ..settings import settings

LOGGER = logging.getLogger("chess.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    email TEXT,
    google_sub TEXT UNIQUE,
    signed_in_at TEXT
);
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    player_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    player_color TEXT NOT NULL,
    bot_id TEXT,
    time_control TEXT,
    status TEXT NOT NULL,
    result TEXT,
    termination TEXT,
    pgn TEXT NOT NULL DEFAULT '',
    moves_json TEXT NOT NULL DEFAULT '[]',
    opening_eco TEXT,
    opening_name TEXT,
    white_name TEXT,
    black_name TEXT,
    source TEXT NOT NULL DEFAULT 'bot',
    coach_mode INTEGER NOT NULL DEFAULT 0,
    start_fen TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
    game_id TEXT PRIMARY KEY REFERENCES games(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS puzzle_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    puzzle_id TEXT NOT NULL,
    solved INTEGER NOT NULL,
    seconds REAL,
    rating_before REAL,
    rating_after REAL,
    mode TEXT NOT NULL DEFAULT 'rated'
);
CREATE TABLE IF NOT EXISTS player_lessons (
    player_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    completed_at TEXT,
    score REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (player_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS player_reviews (
    player_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    section_index INTEGER NOT NULL,
    due_at TEXT NOT NULL,
    interval_days INTEGER NOT NULL DEFAULT 1,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, lesson_id, section_index)
);
CREATE TABLE IF NOT EXISTS player_values (
    player_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    PRIMARY KEY (player_id, key)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    player_id TEXT NOT NULL,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    props_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS coach_cost (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0
);
"""

# Created after the migration: an older file gets player_id from _ADDED_COLUMNS first.
_INDEXES = """
CREATE INDEX IF NOT EXISTS games_by_player ON games(player_id, updated_at);
CREATE INDEX IF NOT EXISTS attempts_by_player ON puzzle_attempts(player_id, id);
CREATE INDEX IF NOT EXISTS events_by_player ON events(player_id, created_at);
"""


# (table, column, declaration) for columns added after the first release.
_ADDED_COLUMNS = (
    ("games", "white_name", "TEXT"),
    ("games", "black_name", "TEXT"),
    ("games", "source", "TEXT NOT NULL DEFAULT 'bot'"),
    ("games", "coach_mode", "INTEGER NOT NULL DEFAULT 0"),
    ("games", "start_fen", "TEXT"),
    # 0 when the model server sent no token counts: the zeros then mean "not reported", not "free".
    ("coach_cost", "usage_reported", "INTEGER NOT NULL DEFAULT 1"),
    # Rows from the single-player version keep NULL here: no player owns them.
    ("games", "player_id", "TEXT"),
    ("puzzle_attempts", "player_id", "TEXT"),
)


class Database:
    def __init__(self) -> None:
        self.where = ""
        self._conn: Any = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._conn = self._connect()  # settings read at start, not import, so tests can point at a temp file
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.executescript(_INDEXES)
        self._conn.commit()
        LOGGER.info("store open at %s", self.where)

    def _connect(self) -> Any:
        if settings.TURSO_DATABASE_URL:
            self.where = settings.TURSO_DATABASE_URL
            return libsql.connect(settings.TURSO_DATABASE_URL, auth_token=settings.TURSO_AUTH_TOKEN)
        path = Path(settings.DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.where = str(path)
        conn = libsql.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")  # a local file only: Turso refuses the statement
        return conn

    def _migrate(self) -> None:
        """Additive migrations only: a column missing from an older file is added with its default."""
        for table, column, decl in _ADDED_COLUMNS:
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in have:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
                LOGGER.warning("migrated %s: added column %s", table, column)
        self.conn.commit()

    async def stop(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> Any:
        if self._conn is None:
            raise RuntimeError("database not started")
        return self._conn

    def _run(self, work: Callable[[Any], Any]) -> Any:
        """Runs work(conn); reconnects and runs it once more when Turso has dropped an idle stream."""
        try:
            return work(self.conn)
        except ValueError as exc:
            if "STREAM_EXPIRED" not in str(exc):
                raise
            # Turso closes a stream left idle for some seconds; nothing ran on it, so the retry is safe.
            LOGGER.info("turso stream expired; reconnecting")
            self._conn = self._connect()
            return work(self._conn)

    async def transaction(self, statements: list[tuple[str, tuple]]) -> None:
        """Runs the statements and commits once: all of them land or none."""
        def work(conn: Any) -> None:
            try:
                for sql, params in statements:
                    conn.execute(sql, params)
            except Exception:
                conn.rollback()
                raise
            conn.commit()

        async with self._lock:
            await asyncio.to_thread(self._run, work)

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self.transaction([(sql, params)])

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        def work(conn: Any) -> list[dict[str, Any]]:
            cur = conn.execute(sql, params)
            columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

        async with self._lock:
            return await asyncio.to_thread(self._run, work)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    async def get_player_value(self, player_id: str, key: str, default: Any) -> Any:
        row = await self.fetch_one("SELECT value_json FROM player_values WHERE player_id = ? AND key = ?", (player_id, key))
        return json.loads(row["value_json"]) if row else default

    async def set_player_value(self, player_id: str, key: str, value: Any) -> None:
        await self.execute(
            "INSERT INTO player_values(player_id, key, value_json) VALUES(?, ?, ?) "
            "ON CONFLICT(player_id, key) DO UPDATE SET value_json = excluded.value_json",
            (player_id, key, json.dumps(value)),
        )


database = Database()
