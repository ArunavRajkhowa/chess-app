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
    # Behind a host's HTTPS proxy (Render, SnapDeploy): the proxy addresses whose
    # X-Forwarded-* headers uvicorn trusts, so cookies get Secure and sign-in rate limits see the
    # real client. "*" trusts every proxy; blank trusts none. uvicorn reads this variable itself.
    FORWARDED_ALLOW_IPS: str = ""

    # Engine. Blank = auto-detect: native `stockfish` on PATH, the Debian path, Homebrew,
    # then the WASM build under frontend/node_modules run by `node`.
    STOCKFISH_PATH: str = ""
    ENGINE_THREADS: int = 1
    ENGINE_HASH_MB: int = 64
    # 2: bot moves and analysis each get an engine. 1: they share one, which halves the memory
    # (each Stockfish holds about 270 MB with its network) for a 512 MB host.
    ENGINE_PROCESSES: int = 2

    # Coach. Every model is optional: with none set the coach answers from rules. Two ways to set one:
    # an OpenAI-compatible server (local Ollama / LM Studio / llama.cpp, or a free hosted API), which
    # needs COACH_BASE_URL and COACH_MODEL; or Anthropic, which needs ANTHROPIC_API_KEY. The
    # OpenAI-compatible server wins when both are set.
    COACH_BASE_URL: str = ""
    COACH_MODEL: str = ""
    COACH_API_KEY: str = ""  # blank for a local server
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-fable-5-1"
    COACH_MAX_TOKENS: int = 2048
    # Narration audio through Microsoft Edge's free neural voices (the edge-tts client); off, or
    # unreachable, the browser's own voices speak instead.
    NARRATION_TTS: bool = True
    NARRATION_VOICE: str = "en-GB-RyanNeural"
    COACH_EFFORT: str = "medium"  # Anthropic only

    # Storage. A local SQLite file, or a Turso database when TURSO_DATABASE_URL is set
    # (libsql://<db>-<org>.turso.io, with a token from `turso db tokens create <db>`).
    DB_PATH: str = str(REPO_ROOT / "data" / "chess.sqlite3")
    TURSO_DATABASE_URL: str = ""
    TURSO_AUTH_TOKEN: str = ""

    # Accounts. Everyone plays as a guest. With a Google OAuth client id, Settings offers
    # "Sign in with Google", which keeps a player's progress across devices.
    GOOGLE_CLIENT_ID: str = ""
    # Signs password-reset links. Blank: generated once into data/secret.key next to DB_PATH
    # (set it explicitly on a host whose disk is wiped on restart, or every restart voids open links).
    SECRET_KEY: str = ""
    # Password-reset mail over SMTP (Brevo and Resend free tiers both offer it). Blank SMTP_HOST:
    # the link is written to the log instead of sent.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    MAIL_FROM: str = ""
    # The address players open the app at, e.g. https://chess.example.com; the base of reset links.
    # Blank: links only for a request to localhost, else no mail (the Host header is the client's).
    PUBLIC_URL: str = ""

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
