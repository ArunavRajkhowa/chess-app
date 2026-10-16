"""Chooses a bot's move from honest engine lines. Strength comes from the search depth the bot
is given and the softmax temperature over centipawn loss; personality nudges line scores; the
first plies may come from the opening book so games vary."""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass

import chess
import chess.engine

from ..engine.pool import EnginePool
from ..engine.score import cp_from_score
from ..openings.book import OpeningBook, load_book
from .roster import Bot

LOGGER = logging.getLogger("chess.bots")


@dataclass
class BotChoice:
    move: chess.Move
    source: str  # "book" | "engine" | "random"
    cp_loss: int  # vs the best line, 0 when best
    best_move: chess.Move | None
    eval_cp: int | None  # white's view after the chosen line's first move, per engine


def _personality_bonus(board: chess.Board, move: chess.Move, bot: Bot, material_balance: int) -> float:
    p = bot.personality
    bonus = 0.0
    is_capture = board.is_capture(move)
    board.push(move)
    gives_check = board.is_check()
    board.pop()
    if p.aggression:
        if is_capture:
            bonus += 25 * p.aggression
        if gives_check:
            bonus += 20 * p.aggression
        enemy_king = board.king(not board.turn)
        if enemy_king is not None and chess.square_distance(move.to_square, enemy_king) <= 2:
            bonus += 15 * p.aggression
    if p.solidity:
        if not is_capture and not gives_check:
            bonus += 12 * p.solidity
        piece = board.piece_at(move.from_square)
        if piece and piece.piece_type == chess.PAWN and chess.square_rank(move.to_square) in (3, 4):
            bonus -= 8 * p.solidity
    if p.trade_when_ahead and is_capture:
        captured = board.piece_at(move.to_square)
        mover = board.piece_at(move.from_square)
        if captured and mover and captured.piece_type == mover.piece_type:
            bonus += 20 * p.trade_when_ahead * (1 if material_balance > 0 else -0.5)
    return bonus


def _material_balance(board: chess.Board, color: chess.Color) -> int:
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    total = 0
    for pt, v in values.items():
        total += v * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color)))
    return total


def _book_move(board: chess.Board, bot: Bot, book: OpeningBook, rng: random.Random) -> chess.Move | None:
    conts = book.continuations(board)
    if not conts:
        return None
    weights = []
    for _, op in conts:
        w = 1.0
        for fav in bot.personality.favourite_openings:
            if fav.lower() in op.name.lower():
                w = 6.0
        weights.append(w)
    mv, _ = rng.choices(conts, weights=weights, k=1)[0]
    return mv


async def choose_move(board: chess.Board, bot: Bot, pool: EnginePool, rng: random.Random | None = None) -> BotChoice:
    rng = rng or random.Random()
    legal = list(board.legal_moves)
    if not legal:
        raise ValueError("no legal moves: the game is over")

    if board.ply() < bot.selection.book_plies:
        mv = _book_move(board, bot, load_book(), rng)
        if mv is not None and mv in legal:
            return BotChoice(move=mv, source="book", cp_loss=0, best_move=None, eval_cp=None)

    if bot.selection.random_move_prob and rng.random() < bot.selection.random_move_prob:
        mv = rng.choice(legal)
        return BotChoice(move=mv, source="random", cp_loss=0, best_move=None, eval_cp=None)

    multipv = min(bot.search.multipv, len(legal))
    infos = await pool.play_move(
        board,
        options={"UCI_LimitStrength": False, "Skill Level": 20},
        depth=bot.search.depth if bot.search.movetime_seconds is None else None,
        time_seconds=bot.search.movetime_seconds,
        multipv=multipv,
    )
    lines: list[tuple[chess.Move, int]] = []
    for info in infos:
        pv = info.get("pv")
        score = info.get("score")
        if not pv or score is None:
            continue
        lines.append((pv[0], cp_from_score(score, board.turn)))
    if not lines:
        mv = rng.choice(legal)
        return BotChoice(move=mv, source="random", cp_loss=0, best_move=None, eval_cp=None)

    best_move, best_cp = lines[0]
    temp = bot.selection.temperature_cp
    balance = _material_balance(board, board.turn)
    if temp <= 0 or len(lines) == 1:
        chosen = best_move
    else:
        scored = []
        for mv, cp in lines:
            adj = cp + _personality_bonus(board, mv, bot, balance)
            scored.append((mv, adj))
        top = max(a for _, a in scored)
        weights = [math.exp((a - top) / temp) for _, a in scored]
        chosen = rng.choices([m for m, _ in scored], weights=weights, k=1)[0]

    chosen_cp = next(cp for mv, cp in lines if mv == chosen)
    eval_white = chosen_cp if board.turn == chess.WHITE else -chosen_cp
    return BotChoice(
        move=chosen, source="engine", cp_loss=max(0, best_cp - chosen_cp),
        best_move=best_move, eval_cp=eval_white,
    )
