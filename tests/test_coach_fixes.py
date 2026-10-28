"""Coach fixes: a cut-off or failed answer still gets the move check, castling is checked, every
call logs its cost, and an oversized chat history turn is refused."""
from __future__ import annotations

import chess
import pytest

from backend.coach import client as C
from backend.coach.client import CoachDeclined
from backend.routers import coach as R
from tests import test_coach_llm as L
from tests.test_coach_llm import STOP, USAGE, delta, events, serve, sse

app, local_model = L.app, L.local_model  # the canned-model fixtures

LENGTH = {"choices": [{"index": 0, "delta": {}, "finish_reason": "length"}]}


def _done_and_text(r) -> tuple[dict, str]:
    ev = events(r)
    return ev[-1], "".join(e["text"] for e in ev if e["type"] == "text")


def test_an_answer_cut_at_max_tokens_says_so_and_is_checked(app):
    serve(sse(delta("Play Qh8 and the key idea is to play"), LENGTH, USAGE, "[DONE]"))
    done, text = _done_and_text(app.post("/api/coach/chat", json={"fen": chess.STARTING_FEN, "question": "what now?"}))
    assert text.endswith("(The coach stopped early.)")
    assert done == {"type": "done", "source": "llm", "model": "gpt-oss:20b", "unverified_moves": ["Qh8"]}


def test_a_mid_stream_error_still_checks_the_partial_text(app):
    serve(sse(delta("Play Qh8 now. "), {"error": {"message": "upstream timeout"}}))
    done, _ = _done_and_text(app.post("/api/coach/chat", json={"fen": chess.STARTING_FEN, "question": "what now?"}))
    assert done["source"] == "llm" and done["unverified_moves"] == ["Qh8"]


def test_a_refusal_after_text_does_not_add_the_rules_answer(app, monkeypatch):
    async def refuse_late(**kw):
        yield "Play Qh8. "
        raise CoachDeclined("the model declined this request")

    monkeypatch.setattr(R, "stream_text", refuse_late)
    done, text = _done_and_text(app.post("/api/coach/chat", json={"fen": chess.STARTING_FEN, "question": "what now?"}))
    assert text == "Play Qh8. \n\n(The coach stopped early.)"
    assert done["source"] == "llm" and done["unverified_moves"] == ["Qh8"]


def test_an_illegal_castle_is_unverified():
    board = chess.Board()  # castling is not legal in the start position
    assert R._unverified_moves("Castle now with O-O.", R._verified(board, {})) == ["O-O"]


def test_a_call_closed_after_the_first_chunk_logs_its_cost(local_model, event_loop):
    serve(sse(delta("Play "), delta("Nf3."), STOP, USAGE, "[DONE]"), cut=10_000)

    async def first_then_close():
        texts = C.stream_text(system="S", user="U", purpose="chat")
        await texts.__anext__()
        await texts.aclose()

    event_loop.run_until_complete(first_then_close())
    assert local_model == [("chat", "gpt-oss:20b", 0, 0, 0, 0)]  # usage not reported yet: logged as unknown


def test_a_mid_stream_error_logs_its_cost(local_model, event_loop):
    serve(sse(delta("start"), {"error": {"message": "upstream timeout"}}))

    async def drain():
        return [t async for t in C.stream_text(system="S", user="U", purpose="chat")]

    with pytest.raises(RuntimeError, match="upstream timeout"):
        event_loop.run_until_complete(drain())
    assert len(local_model) == 1


def test_an_oversized_history_turn_is_refused(app):
    history = [{"role": "user", "content": "x" * 50_000}] * 8
    r = app.post("/api/coach/chat", json={"fen": chess.STARTING_FEN, "question": "hi", "history": history})
    assert r.status_code == 422


def test_chat_history_reaches_the_prompt(app, monkeypatch):
    seen: list[str] = []

    async def record(*, system, user, purpose):
        seen.append(user)
        yield "ok"

    monkeypatch.setattr(R, "stream_text", record)
    history = [{"role": "user", "content": "What about Nf3?"}, {"role": "assistant", "content": "Nf3 develops a piece."}]
    app.post("/api/coach/chat", json={"fen": chess.STARTING_FEN, "question": "and after that?", "history": history})
    assert seen and "user: What about Nf3?\nassistant: Nf3 develops a piece." in seen[0]
