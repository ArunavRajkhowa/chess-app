"""The coach's OpenAI-compatible client against canned streams: the real-world shapes of Ollama,
Groq and OpenRouter (usage chunk, keep-alive comments, thinking in `reasoning` or <think> tags,
errors), with chunk boundaries cut through lines. No network: the transport is replaced."""
from __future__ import annotations

import json

import chess
import httpx
import pytest
from fastapi.testclient import TestClient

from backend import settings as s
from backend.app import create_app
from backend.coach import client as C
from backend.coach.client import CoachDeclined, _ThinkFilter


def sse(*events: dict | str) -> bytes:
    return "".join(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n" for e in events).encode()


def delta(text: str = "", **extra) -> dict:
    return {"choices": [{"index": 0, "delta": {"content": text, **extra}, "finish_reason": None}]}


STOP = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
USAGE = {"choices": [], "usage": {"prompt_tokens": 912, "completion_tokens": 41, "prompt_tokens_details": {"cached_tokens": 800}}}


class Pieces(httpx.AsyncByteStream):
    """A response body that arrives in separate pieces, as a real stream does."""

    def __init__(self, pieces: list[bytes]):
        self.pieces = pieces

    async def __aiter__(self):
        for piece in self.pieces:
            yield piece


def serve(body: bytes, *, status: int = 200, cut: int = 7, seen: list | None = None):
    """Installs a server that answers with `body` in pieces of `cut` bytes, so lines are split."""
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        pieces = [body[i:i + cut] for i in range(0, len(body), cut)]
        assert len(pieces) > 1 or len(body) <= cut
        kind = "text/event-stream" if status == 200 else "application/json"
        return httpx.Response(status, headers={"content-type": kind}, stream=Pieces(pieces))
    C._transport = httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def local_model(monkeypatch):
    monkeypatch.setattr(s.settings, "COACH_BASE_URL", "http://localhost:11434/v1/")
    monkeypatch.setattr(s.settings, "COACH_MODEL", "gpt-oss:20b")
    monkeypatch.setattr(s.settings, "COACH_API_KEY", "")
    costs: list[tuple] = []

    async def record(sql, params=()):
        costs.append(params)

    monkeypatch.setattr(C.database, "execute", record)
    yield costs
    C._transport = None


async def collect(**kw) -> str:
    return "".join([t async for t in C.stream_text(system="SYS", user="USER", purpose="chat", **kw)])


def test_a_stream_cut_through_lines_is_joined_and_its_usage_logged(local_model, event_loop):
    serve(sse(delta("Play "), {"choices": [{"delta": {"reasoning": "hidden thought"}}]}, delta("Nf3."), STOP, USAGE, "[DONE]"))
    assert event_loop.run_until_complete(collect()) == "Play Nf3."
    assert local_model == [("chat", "gpt-oss:20b", 912, 41, 800, 1)]


def test_keep_alive_comments_and_a_missing_usage_chunk(local_model, event_loop):
    serve(b": keep-alive\n\n" + sse(delta("e4"), STOP, "[DONE]"))
    assert event_loop.run_until_complete(collect()) == "e4"
    assert local_model == [("chat", "gpt-oss:20b", 0, 0, 0, 0)]  # zeros flagged as not reported


def test_think_blocks_are_dropped_even_when_a_tag_is_split():
    f = _ThinkFilter()
    out = "".join(f.feed(p) for p in ["Hi <th", "ink>secret</thi", "nk> there <", "b>ok"]) + f.flush()
    assert out == "Hi  there <b>ok"
    f = _ThinkFilter()
    assert f.feed("<think>never closed") + f.flush() == ""


def test_the_request_is_an_openai_chat_completion_with_optional_auth(local_model, event_loop, monkeypatch):
    seen: list[httpx.Request] = []
    serve(sse(delta("ok"), STOP, USAGE, "[DONE]"), seen=seen)
    event_loop.run_until_complete(collect())
    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == "http://localhost:11434/v1/chat/completions" and "authorization" not in request.headers
    assert body["model"] == "gpt-oss:20b" and body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert [m["role"] for m in body["messages"]] == ["system", "user"] and body["max_tokens"] == s.settings.COACH_MAX_TOKENS
    monkeypatch.setattr(s.settings, "COACH_API_KEY", "key-123")
    serve(sse(delta("ok"), STOP, "[DONE]"), seen=seen)
    event_loop.run_until_complete(collect())
    assert seen[1].headers["authorization"] == "Bearer key-123"


def test_failures_raise_so_the_router_can_fall_back(event_loop, monkeypatch):
    serve(json.dumps({"error": {"message": "Rate limit reached for model"}}).encode(), status=429)
    with pytest.raises(RuntimeError, match=r"HTTP 429: Rate limit reached"):
        event_loop.run_until_complete(collect())
    serve(sse(delta("start"), {"error": {"message": "upstream timeout"}}))
    with pytest.raises(RuntimeError, match="upstream timeout"):
        event_loop.run_until_complete(collect())
    serve(sse({"choices": [{"delta": {"reasoning": "thinking only"}, "finish_reason": "length"}]}, "[DONE]"))
    with pytest.raises(CoachDeclined, match="finish_reason=length"):  # a thinking model used every token
        event_loop.run_until_complete(collect())


def test_a_half_set_route_is_named(monkeypatch):
    monkeypatch.setattr(s.settings, "COACH_MODEL", "")
    assert C.llm_provider() is None and C.llm_problem() == "COACH_MODEL is empty: the coach needs both COACH_BASE_URL and COACH_MODEL"
    monkeypatch.setattr(s.settings, "COACH_MODEL", "x")
    monkeypatch.setattr(s.settings, "COACH_BASE_URL", "")
    assert C.llm_problem() == "COACH_BASE_URL is empty: the coach needs both COACH_BASE_URL and COACH_MODEL"
    monkeypatch.setattr(s.settings, "ANTHROPIC_API_KEY", "k")
    assert C.llm_provider() == C.PROVIDER_ANTHROPIC and C.llm_model() == s.settings.ANTHROPIC_MODEL


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(s.settings, "DB_PATH", str(tmp_path / "t.sqlite3"))
    with TestClient(create_app()) as c:
        yield c


def events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_the_router_streams_the_model_and_flags_moves_it_made_up(app):
    assert app.get("/api/health").json()["coach"] == {"llm": True, "provider": "openai-compatible", "model": "gpt-oss:20b", "problem": None}
    serve(sse(delta("Try Nf3 or the invented Qh8."), STOP, USAGE, "[DONE]"))
    r = app.post("/api/coach/chat", json={"fen": chess.STARTING_FEN, "question": "what now?", "level": "beginner"})
    ev = events(r)
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Try Nf3 or the invented Qh8."
    assert ev[-1]["type"] == "done" and ev[-1]["source"] == "llm" and ev[-1]["model"] == "gpt-oss:20b"
    assert ev[-1]["unverified_moves"] == ["Qh8"]


def test_the_router_falls_back_to_rules_when_the_server_fails(app):
    serve(b'{"error": "bad gateway"}', status=502)
    r = app.post("/api/coach/chat", json={"fen": chess.STARTING_FEN, "question": "what now?", "level": "beginner"})
    ev = events(r)
    assert ev[-1] == {"type": "done", "source": "rules"} and any(e["type"] == "text" and e["text"] for e in ev)
