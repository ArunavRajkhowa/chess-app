"""Bot selector: a seen free piece is always taken, a slip overlooks one enemy piece, book moves come first,
and after the book a Maia bot draws its move from Maia-3's policy (the real model)."""
from __future__ import annotations

import random
from dataclasses import replace

import chess
import pytest

from backend.bots import maia
from backend.bots.roster import BOTS, get_bot
from backend.bots.selector import LONG_RANGE, _shape, _wins_a_piece, choose_move
from backend.bots.specialists import specialist_bots
from backend.engine.pool import EnginePool

FREE_KNIGHT = "r1bqkbnr/pppp1ppp/2n5/4N3/4P3/8/PPPP1PPP/RNBQKB1R b KQkq - 0 3"  # 3.Nxe5?? after 1.e4 e5 2.Nf3 Nc6


def test_wins_a_piece_is_a_static_exchange_fact():
    board = chess.Board(FREE_KNIGHT)
    assert _wins_a_piece(board, chess.Move.from_uci("c6e5"))
    defended = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 2")
    assert not _wins_a_piece(defended, chess.Move.from_uci("f3e5"))  # a pawn, not a piece
    rook = chess.Board("4k3/8/2p5/3r4/4P3/8/8/3QK3 w - - 0 1")  # the rook on d5 is defended by c6
    assert _wins_a_piece(rook, chess.Move.from_uci("e4d5"))  # the pawn nets 5 - 1
    assert not _wins_a_piece(rook, chess.Move.from_uci("d1d5"))  # the queen nets 5 - 9


@pytest.fixture()
def engine(event_loop):
    pool = EnginePool()
    event_loop.run_until_complete(pool.start())
    yield pool
    event_loop.run_until_complete(pool.stop())


def test_every_low_bot_takes_a_free_knight(event_loop, engine):
    board = chess.Board(FREE_KNIGHT)
    rng = random.Random(4)
    for bot_id in ("sam", "nova", "rafa"):
        picks = [event_loop.run_until_complete(choose_move(board, get_bot(bot_id), engine, rng)).move for _ in range(8)]
        # at depth 3 the engine's lines drop the capture about 1 search in 20 (measured): it is not seen then
        assert sum(m.uci() == "c6e5" for m in picks) >= 7, (bot_id, picks)


def test_a_slip_overlooks_one_enemy_long_range_piece(event_loop, engine):
    board = chess.Board("r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 4 8")  # Italian, after the book
    seen = []
    real = engine.play_move

    async def spy(b, **kw):
        seen.append(b.copy())
        return await real(b, **kw)

    engine.play_move = spy
    slipper = get_bot("nova")
    slipper = replace(slipper, maia=None, selection=replace(slipper.selection, slip_prob=1.0))
    choice = event_loop.run_until_complete(choose_move(board, slipper, engine, random.Random(1)))
    missing = [sq for sq in chess.SQUARES if board.piece_at(sq) != seen[0].piece_at(sq)]
    assert len(missing) == 1 and board.piece_type_at(missing[0]) in LONG_RANGE and board.color_at(missing[0]) == chess.BLACK
    assert choice.source == "slip" and board.is_legal(choice.move) and choice.eval_cp is None


def test_opening_moves_are_book_moves(event_loop, engine):
    board = chess.Board()
    board.push_san("e4")
    rng = random.Random(3)
    picks = [event_loop.run_until_complete(choose_move(board, get_bot("nova"), engine, rng)) for _ in range(6)]
    assert all(c.source == "book" for c in picks), [(c.move.uci(), c.source) for c in picks]


MATE_OR_KNIGHT = "6k1/5ppp/8/n7/8/8/3B1PPP/4R1K1 w - - 0 1"  # Re8# mates, Bxa5 wins a free knight


@pytest.mark.parametrize("bot_id", ["nova", "leo", "omar", "viktor"])
def test_a_free_piece_never_beats_a_mate(event_loop, engine, bot_id):
    board = chess.Board(MATE_OR_KNIGHT)
    rng = random.Random(5)
    picks = [event_loop.run_until_complete(choose_move(board, get_bot(bot_id), engine, rng)).move.uci() for _ in range(4)]
    assert picks == ["e1e8"] * 4, picks


@pytest.mark.parametrize("bot_id", ["leo", "omar", "zara", "coach", "trickster"])
def test_a_book_move_never_leaves_a_free_piece(event_loop, engine, bot_id):
    board = chess.Board(FREE_KNIGHT)  # Bc5, f5 and Nf6 are book here and each leaves the knight on e5
    rng = random.Random(6)
    picks = [event_loop.run_until_complete(choose_move(board, get_bot(bot_id), engine, rng)).move.uci() for _ in range(4)]
    assert not {"f8c5", "f7f5", "g8f6"} & set(picks), picks


ITALIAN = "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 c2c3 g8f6 d2d4 e5d4".split()  # ten plies: the book phase is over


def test_maia_covers_the_ladder_from_1400_to_2600_only():
    with_maia = {b.id for b in BOTS if b.maia}
    assert with_maia == {b.id for b in BOTS if b.tier != "special" and 1400 <= b.elo <= 2600}
    assert not any(b.maia for b in specialist_bots().values())


@pytest.mark.parametrize("bot_id", ["mei", "ivy", "elena"])
def test_a_maia_bot_after_the_book_plays_a_move_from_its_policy(event_loop, engine, bot_id):
    bot = get_bot(bot_id)
    board = chess.Board()
    for uci in ITALIAN:
        board.push_uci(uci)
    allowed = _shape(maia.policy(board, bot.maia.elo_self, bot.maia.elo_self), bot.maia)
    calls = []
    real = engine.play_move

    async def spy(b, **kw):
        calls.append(b)
        return await real(b, **kw)

    engine.play_move = spy
    rng = random.Random(8)
    picks = [event_loop.run_until_complete(choose_move(board, bot, engine, rng)) for _ in range(6)]
    assert all(c.source == "maia" and board.is_legal(c.move) and c.move in allowed for c in picks)
    assert not calls  # the engine is not asked


def test_a_maia_bot_plays_book_moves_in_the_book_phase(event_loop, engine):
    board = chess.Board()
    board.push_san("e4")
    picks = [event_loop.run_until_complete(choose_move(board, get_bot("mei"), engine, random.Random(i))) for i in range(4)]
    assert all(c.source == "book" for c in picks), [(c.move.uci(), c.source) for c in picks]


@pytest.mark.parametrize("bot_id", ["max", "arjun", "trickster", "coach"])
def test_a_bot_without_maia_keeps_the_engine_selector(event_loop, engine, bot_id):
    board = chess.Board()
    for uci in ITALIAN:
        board.push_uci(uci)
    choice = event_loop.run_until_complete(choose_move(board, get_bot(bot_id), engine, random.Random(2)))
    assert choice.source in ("engine", "random", "book") and board.is_legal(choice.move)
