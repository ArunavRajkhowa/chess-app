"""Shared fixtures. Nothing here reaches the network: the engine is a local process and no coach
model is configured in tests (the Anthropic and OpenAI-compatible settings are blanked, so a
developer's .env cannot send a test to a real model)."""
from __future__ import annotations

import asyncio
import os

import pytest

for _name in ("ANTHROPIC_API_KEY", "COACH_BASE_URL", "COACH_MODEL", "COACH_API_KEY", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "GOOGLE_CLIENT_ID"):
    os.environ[_name] = ""


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
