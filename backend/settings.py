"""Deployment settings read from the environment and `backend/.env` or a root `.env`.
Every field here is a property of the machine the app runs on (paths, keys, ports), never a
chess rule or a coaching hyperparameter; those live in code next to the thing they tune."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where the app listens. One process serves /api/* and the built frontend.
    HOST: str = "127.0.0.1"
    PORT: int = 8765
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Engine. Blank = auto-detect: native `stockfish` on PATH, the Debian path, Homebrew,
    # then the WASM build under frontend/node_modules run by `node`.
    STOCKFISH_PATH: str = ""
    ENGINE_THREADS: int = 1
    ENGINE_HASH_MB: int = 64

    # Coach. The key is optional: without it the coach falls back to rule-based explanations.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-fable-5-1"
    COACH_MAX_TOKENS: int = 2048
    COACH_EFFORT: str = "medium"

    # Storage. SQLite file for games, reviews, puzzle attempts and lesson progress.
    DB_PATH: str = str(REPO_ROOT / "data" / "chess.sqlite3")

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
