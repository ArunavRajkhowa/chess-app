"""The SQLite store: games, reviews, puzzle attempts, lesson progress and the player's ratings.
One connection, one writer; every call runs on a thread so the event loop never blocks."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from ..settings import settings

LOGGER = logging.getLogger("chess.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    puzzle_id TEXT NOT NULL,
    solved INTEGER NOT NULL,
    seconds REAL,
    rating_before REAL,
    rating_after REAL,
    mode TEXT NOT NULL DEFAULT 'rated'
);
CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id TEXT PRIMARY KEY,
    completed_at TEXT,
    score REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS player (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
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


# (table, column, declaration) for columns added after the first release.
_ADDED_COLUMNS = (
    ("games", "white_name", "TEXT"),
    ("games", "black_name", "TEXT"),
    ("games", "source", "TEXT NOT NULL DEFAULT 'bot'"),
    ("games", "coach_mode", "INTEGER NOT NULL DEFAULT 0"),
    ("games", "start_fen", "TEXT"),
)


class Database:
    def __init__(self) -> None:
        self.path = Path(settings.DB_PATH)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self.path = Path(settings.DB_PATH)  # read at start so tests can point at a temp file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        LOGGER.info("sqlite store open at %s", self.path)

    def _migrate(self) -> None:
        """Additive migrations only: a column missing from an older file is added with its default."""
        for table, column, decl in _ADDED_COLUMNS:
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
                LOGGER.warning("migrated %s: added column %s", table, column)
        self.conn.commit()

    async def stop(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("database not started")
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> None:
        async with self._lock:
            await asyncio.to_thread(self._execute, sql, params)

    def _execute(self, sql: str, params: tuple) -> None:
        self.conn.execute(sql, params)
        self.conn.commit()

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        async with self._lock:
            row = await asyncio.to_thread(lambda: self.conn.execute(sql, params).fetchone())
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        async with self._lock:
            rows = await asyncio.to_thread(lambda: self.conn.execute(sql, params).fetchall())
        return [dict(r) for r in rows]

    async def get_player_value(self, key: str, default: Any) -> Any:
        row = await self.fetch_one("SELECT value_json FROM player WHERE key = ?", (key,))
        return json.loads(row["value_json"]) if row else default

    async def set_player_value(self, key: str, value: Any) -> None:
        await self.execute(
            "INSERT INTO player(key, value_json) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
            (key, json.dumps(value)),
        )


database = Database()
