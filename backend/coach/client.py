"""The Anthropic client for the coach: streams text, logs cost, falls back to rules when the key
is missing or the model declines. The model id comes from ANTHROPIC_MODEL, never from code."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from ..settings import settings
from ..storage.db import database

LOGGER = logging.getLogger("chess.coach")
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Models that accept the server-side refusal fallback parameter (Claude API only).
_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


def prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def llm_enabled() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


class CoachDeclined(RuntimeError):
    pass


async def stream_text(*, system: str, user: str, purpose: str, max_tokens: int | None = None) -> AsyncIterator[str]:
    """Yields text chunks from the model. Raises CoachDeclined on a refusal so the caller can fall back."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    model = settings.ANTHROPIC_MODEL
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens or settings.COACH_MAX_TOKENS,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": settings.COACH_EFFORT},
    }
    use_fallback = model.startswith(_FALLBACK_MODELS)
    if use_fallback:
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
    surface = client.beta.messages if use_fallback else client.messages
    async with surface.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text
        final = await stream.get_final_message()
    usage = final.usage
    await database.execute(
        "INSERT INTO coach_cost(purpose, model, input_tokens, output_tokens, cache_read_tokens) VALUES(?,?,?,?,?)",
        (purpose, final.model, usage.input_tokens, usage.output_tokens, getattr(usage, "cache_read_input_tokens", 0) or 0),
    )
    LOGGER.info("coach %s model=%s in=%d out=%d cached=%s stop=%s", purpose, final.model, usage.input_tokens,
                usage.output_tokens, getattr(usage, "cache_read_input_tokens", 0), final.stop_reason)
    if final.stop_reason == "refusal":
        raise CoachDeclined("the model declined this request")
