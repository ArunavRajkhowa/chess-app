"""The coach's model client: streams text from an OpenAI-compatible server (local Ollama, LM
Studio, llama.cpp, or a free hosted API) or from Anthropic, logs tokens, and lets the caller fall
back to rules when no model is set, a call fails or the model declines. Model ids come from the
environment, never from code."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path

import httpx

from ..settings import settings
from ..storage.db import database

LOGGER = logging.getLogger("chess.coach")
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Wire names: the provider the app reports in /api/health.
PROVIDER_OPENAI = "openai-compatible"
PROVIDER_ANTHROPIC = "anthropic"

TEMPERATURE = 0.3  # explanations should stay close to the fact sheet
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 180  # a local model on a CPU can take a minute to read the prompt

# Models that accept the server-side refusal fallback parameter (Claude API only).
_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")

# Tests replace this to serve a canned stream without a network.
_transport: httpx.AsyncBaseTransport | None = None


def prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def llm_provider() -> str | None:
    """The configured model route, or None when the coach answers from rules."""
    if settings.COACH_BASE_URL and settings.COACH_MODEL:
        return PROVIDER_OPENAI
    if settings.ANTHROPIC_API_KEY:
        return PROVIDER_ANTHROPIC
    return None


def llm_enabled() -> bool:
    return llm_provider() is not None


def llm_model() -> str:
    provider = llm_provider()
    return settings.COACH_MODEL if provider == PROVIDER_OPENAI else settings.ANTHROPIC_MODEL if provider == PROVIDER_ANTHROPIC else ""


def llm_problem() -> str | None:
    """A half-set OpenAI-compatible route, named so the user can fix it."""
    if bool(settings.COACH_BASE_URL) != bool(settings.COACH_MODEL):
        missing = "COACH_MODEL" if settings.COACH_BASE_URL else "COACH_BASE_URL"
        return f"{missing} is empty: the coach needs both COACH_BASE_URL and COACH_MODEL"
    return None


class CoachDeclined(RuntimeError):
    pass


async def _log_cost(purpose: str, model: str, input_tokens: int | None, output_tokens: int | None, cached_tokens: int | None) -> None:
    reported = input_tokens is not None and output_tokens is not None
    await database.execute(
        "INSERT INTO coach_cost(purpose, model, input_tokens, output_tokens, cache_read_tokens, usage_reported) VALUES(?,?,?,?,?,?)",
        (purpose, model, input_tokens or 0, output_tokens or 0, cached_tokens or 0, int(reported)),
    )
    LOGGER.info("coach %s model=%s in=%s out=%s cached=%s", purpose, model, input_tokens if reported else "?", output_tokens if reported else "?", cached_tokens or 0)


async def stream_text(*, system: str, user: str, purpose: str, max_tokens: int | None = None) -> AsyncIterator[str]:
    """Yields text chunks from the model. Raises CoachDeclined when the model refuses or answers
    nothing, and any other error when the call fails, so the caller can fall back to rules."""
    provider = llm_provider()
    if provider is None:
        raise RuntimeError("no coach model is set: fill COACH_BASE_URL and COACH_MODEL, or ANTHROPIC_API_KEY")
    run = _stream_openai if provider == PROVIDER_OPENAI else _stream_anthropic
    async with aclosing(run(system=system, user=user, purpose=purpose, max_tokens=max_tokens or settings.COACH_MAX_TOKENS)) as texts:
        async for text in texts:
            yield text


class _ThinkFilter:
    """Drops <think>...</think> blocks from a stream, even when a tag is split across chunks. Some
    reasoning models send their thinking inline; it is not coaching text."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.buffer = ""
        self.inside = False

    @staticmethod
    def _partial_tag_length(text: str, tag: str) -> int:
        """Length of the longest tail of `text` that could be the start of `tag`."""
        return next((k for k in range(min(len(tag) - 1, len(text)), 0, -1) if text.endswith(tag[:k])), 0)

    def feed(self, text: str) -> str:
        self.buffer += text
        out: list[str] = []
        while True:
            if self.inside:
                end = self.buffer.find(self.CLOSE)
                if end == -1:
                    self.buffer = self.buffer[len(self.buffer) - self._partial_tag_length(self.buffer, self.CLOSE):]
                    break
                self.buffer = self.buffer[end + len(self.CLOSE):]
                self.inside = False
            else:
                start = self.buffer.find(self.OPEN)
                if start == -1:
                    keep = self._partial_tag_length(self.buffer, self.OPEN)
                    out.append(self.buffer[: len(self.buffer) - keep])
                    self.buffer = self.buffer[len(self.buffer) - keep:]
                    break
                out.append(self.buffer[:start])
                self.buffer = self.buffer[start + len(self.OPEN):]
                self.inside = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self.inside else self.buffer
        self.buffer = ""
        return rest


def _error_text(body: str) -> str:
    """The message a server put in an error body, or the first part of the body."""
    try:
        err = json.loads(body).get("error")
        return str(err.get("message") if isinstance(err, dict) else err or body)[:300]
    except (ValueError, AttributeError):
        return body[:300]


async def _stream_openai(*, system: str, user: str, purpose: str, max_tokens: int) -> AsyncIterator[str]:
    url = settings.COACH_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.COACH_API_KEY:
        headers["Authorization"] = f"Bearer {settings.COACH_API_KEY}"
    body = {
        "model": settings.COACH_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": True,
        "stream_options": {"include_usage": True},  # without it most servers send no token counts
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
    }
    think = _ThinkFilter()
    usage: dict = {}
    finish_reason: str | None = None
    shown = 0
    timeout = httpx.Timeout(CONNECT_TIMEOUT_SECONDS, read=READ_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, transport=_transport) as http:
        async with http.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code != 200:
                detail = (await response.aread()).decode("utf-8", "replace")
                raise RuntimeError(f"{url} answered HTTP {response.status_code}: {_error_text(detail)}")
            async with aclosing(response.aiter_lines()) as lines:
                async for line in lines:
                    if not line.startswith("data:"):  # blank lines and ": keep-alive" comments
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":  # the server ends the body next; reading on closes the stream cleanly
                        continue
                    chunk = json.loads(data)
                    if chunk.get("error"):
                        raise RuntimeError(f"the model server reported an error mid-stream: {_error_text(json.dumps({'error': chunk['error']}))}")
                    usage = chunk.get("usage") or usage
                    for choice in chunk.get("choices") or []:
                        finish_reason = choice.get("finish_reason") or finish_reason
                        # `reasoning` and `reasoning_content` carry thinking on some servers: never shown
                        text = think.feed((choice.get("delta") or {}).get("content") or "")
                        if text:
                            shown += len(text)
                            yield text
    tail = think.flush()
    if tail:
        shown += len(tail)
        yield tail
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    await _log_cost(purpose, settings.COACH_MODEL, usage.get("prompt_tokens"), usage.get("completion_tokens"), cached)
    if not shown:
        raise CoachDeclined(f"the model sent no answer text (finish_reason={finish_reason}); a thinking model may have used all {max_tokens} tokens")


async def _stream_anthropic(*, system: str, user: str, purpose: str, max_tokens: int) -> AsyncIterator[str]:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    model = settings.ANTHROPIC_MODEL
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
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
    await _log_cost(purpose, final.model, usage.input_tokens, usage.output_tokens, getattr(usage, "cache_read_input_tokens", 0))
    if final.stop_reason == "refusal":
        raise CoachDeclined("the model declined this request")
