"""Guided play: one grounded note after each player move, in the bot's domain (opening, middlegame
or endgame). Moves come from the book or the engine; a course comment is shown only when every
move it names is legal in the position it comments on."""
from __future__ import annotations

import re
from functools import lru_cache

import chess

from ..content.endgames import load_endgames
from ..engine.pool import EnginePool
from ..engine.score import cp_from_score
from ..openings.book import _position_key, load_book
from ..openings.courses import load_courses
from ..review.phases import phase_of
from ..study.assess import assess
from ..study.reasons import opponent_to_move
from .roster import SPECIALTY_ENDGAME, SPECIALTY_OPENING, Bot

VERDICT_DEPTH = 12
WIN_CP, DRAW_CP = 250, 150  # an endgame verdict, and the bar every endgame position's goal must meet (tests/test_endgames.py)
_SAN_TOKEN = re.compile(r"\b(?:O-O(?:-O)?|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]=[QRBN])")
GOAL_WORDS = {"mate": "checkmate", "promote": "promote a pawn", "draw": "hold the draw", "survive": "survive", "win_material": "win material"}


@lru_cache(maxsize=1)
def _course_comments() -> dict[str, str]:
    """Position key -> the course comment on the move that reached it, over every line and trap."""
    out: dict[str, str] = {}
    for course in load_courses().values():
        for line in course.lines + course.traps:
            for p in line.plies:
                if p["comment"]:
                    out.setdefault(_position_key(chess.Board(p["fen"])), p["comment"])
    return out


def _moves_legal_here(text: str, board: chess.Board) -> bool:
    """True when every piece move, capture or castle the text names is legal here for one side or the other."""
    legal = {b.san(mv).rstrip("+#") for b in (board, opponent_to_move(board)) for mv in b.legal_moves}
    return all(t in legal for t in _SAN_TOKEN.findall(text))


def _side_word(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


def opening_note(before: chess.Board, move: chess.Move) -> str | None:
    """Book move or left the book; None when the game was already out of the book before the move."""
    book = load_book()
    san = before.san(move)
    after = before.copy()
    after.push(move)
    comments = _course_comments()
    if _position_key(after) in book.lines_through:
        op = book.lookup(after)
        text = f"{san} is a book move" + (f": the {op.name}." if op else ".")
        idea = comments.get(_position_key(after))
        if idea and not _moves_legal_here(idea, after):
            idea = None  # the comment names a move that is legal for neither side here: a transposition, or a later move
        return text + (f" The idea: {idea}" if idea else "")
    if _position_key(before) not in book.lines_through:
        return None
    options = book.book_moves(before)
    if not options:
        return None
    main_mv, main_op, _ = max(options, key=lambda t: t[2])
    main_san = before.san(main_mv)
    text = f"You left the book with {san}. The main line here is {main_san}" + (f", the {main_op.name}." if main_op else ".")
    after_main = before.copy()
    after_main.push(main_mv)
    idea = comments.get(_position_key(after_main))
    if idea and not _moves_legal_here(idea, after_main):
        idea = None
    return text + (f" The idea: {idea}" if idea else "")


async def middlegame_note(board: chess.Board, player: chess.Color, pool: EnginePool) -> str:
    """The verdict and the imbalance that matters for the player, with the plan it gives."""
    a = await assess(board, pool)
    me = _side_word(player)
    mine = next((i for i in a["imbalances"] if i["side"] in (me, "both")), None)
    theirs = next((i for i in a["imbalances"] if i["side"] not in (me, "both")), None)
    if mine:
        return f"{a['verdict']} Your asset: {mine['text']}. Plan: {mine['plan_for']}."
    if theirs:
        return f"{a['verdict']} Watch out: {theirs['text']}. The plan against it: {theirs['plan_against']}."
    return f"{a['verdict']} Plan: {a['plans'][me][0]}."


def _endgame_record(start_fen: str | None) -> dict | None:
    if not start_fen:
        return None
    key = _position_key(chess.Board(start_fen))
    for p in load_endgames()["positions"]:
        board = chess.Board(p["fen"])
        if key in (_position_key(board), _position_key(board.mirror())):
            return p
    return None


def _verdict(cp: int) -> str:
    return "winning" if cp >= WIN_CP else "lost" if cp <= -WIN_CP else "drawn" if abs(cp) < DRAW_CP else "better" if cp > 0 else "worse"


async def endgame_note(before: chess.Board, move: chess.Move, pool: EnginePool, record: dict | None) -> str:
    """The engine's verdict before and after the move, from the player's side, and the record's rule."""
    player = before.turn
    san = before.san(move)
    infos = await pool.analyse(before, depth=VERDICT_DEPTH)
    cp_before = cp_from_score(infos[0]["score"], player)
    best_san = before.san(infos[0]["pv"][0]) if infos[0].get("pv") else None
    after = before.copy()
    after.push(move)
    if after.is_game_over():
        text = f"{san} ends the game."
    else:
        cp_after = cp_from_score((await pool.analyse(after, depth=VERDICT_DEPTH))[0]["score"], player)
        v_before, v_after = _verdict(cp_before), _verdict(cp_after)
        if v_after != v_before and cp_after < cp_before and best_san and best_san != san:
            text = f"{san} lets it slip: the position is {v_after} now, and {best_san} kept it {v_before}."
        else:
            text = f"{san} keeps the position {v_after}."
    if record:
        text += f" Goal: {GOAL_WORDS[record['goal']]}. The rule: {record['tip']}"
    return text


async def guide_note(bot: Bot, before: chess.Board, move: chess.Move, after_reply: chess.Board, start_fen: str | None, pool: EnginePool) -> str:
    """The note for this move: the specialist's domain first, the phase of the game otherwise."""
    kind = bot.specialty.kind if bot.specialty else phase_of(before, before.ply())
    if kind == SPECIALTY_OPENING:
        note = opening_note(before, move)
        if note:
            return note
    if kind == SPECIALTY_ENDGAME or phase_of(before, before.ply()) == "endgame":
        return await endgame_note(before, move, pool, _endgame_record(start_fen))
    if after_reply.is_game_over():
        return f"{before.san(move)}: the game is over."
    return await middlegame_note(after_reply, before.turn, pool)
