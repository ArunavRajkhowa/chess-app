"""Every teaching board in the curriculum matches its words: a move quoted for the position shown is legal
there, and no late-game move is read over the starting position. Text and quiz boards come from the loader."""
from __future__ import annotations

import chess
import pytest

from backend.content.lessons import load_curriculum, quoted_moves

LATE_MOVE = 5  # a quote past this move number describes a game in progress, not the starting position


def _boards(lesson) -> list[tuple[str, str, str]]:
    """(where, fen, words) for every board a reader sees with words beside it."""
    out = []
    for i, s in enumerate(lesson.sections):
        if s["type"] == "text":
            out += [(f"section {i} paragraph {j}", p["fen"], p["md"]) for j, p in enumerate(s["paragraphs"])]
        elif s["type"] == "quiz":
            out.append((f"section {i}", s["fen"], s["question"]))
        elif s["type"] == "position" and s.get("caption"):
            out.append((f"section {i}", s["fen"], s["caption"]))
        elif s["type"] == "lecture":
            out += [(f"section {i} frame {j}", f["fen"], f["say"]) for j, f in enumerate(s["frames"])]
    return out


LESSONS = [lsn for m in load_curriculum() for lsn in m.lessons]


@pytest.mark.parametrize("lesson", LESSONS, ids=[lsn.id for lsn in LESSONS])
def test_every_teaching_board_matches_its_words(lesson):
    wrong = []
    for where, fen, words in _boards(lesson):
        board = chess.Board(fen)
        for number, white, san in quoted_moves(words):
            if fen == chess.STARTING_FEN and number > LATE_MOVE:
                wrong.append(f"{where}: {number}.{san} is read over the starting position")
            elif (number, white) == (board.fullmove_number, board.turn):
                try:
                    board.parse_san(san)
                except ValueError:
                    wrong.append(f"{where}: {number}.{san} is not legal on the board shown, {fen}")
    assert not wrong, f"{lesson.id}: " + "; ".join(wrong)
