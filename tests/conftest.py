"""Shared fixtures. Nothing here reaches the network: the engine is a local process and the
coach's Anthropic client is never constructed in tests (ANTHROPIC_API_KEY is blanked)."""
from __future__ import annotations

import asyncio
import os

import pytest

os.environ["ANTHROPIC_API_KEY"] = ""


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
