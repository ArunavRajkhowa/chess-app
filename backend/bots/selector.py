"""Chooses a bot's move from honest engine lines. Strength comes from the search depth the bot
is given and the softmax temperature over centipawn loss; personality nudges line scores. In the
first plies a line on the way to one of the bot's favourite named openings is preferred."""
from __future__ import annotations

import logging
import math
import random
import re
from dataclasses import dataclass
from functools import lru_cache

import chess
import chess.engine

from ..engine.pool import EnginePool
from ..engine.score import cp_from_score
from ..openings.book import load_book
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


@lru_cache(maxsize=None)
def _favourite_positions(favourites: tuple[str, ...]) -> frozenset[str]:
    """Every position (EPD) on a named book line of these openings, so 1.d4 counts toward the London System.
    A favourite matches whole words: "Slav" names the Slav and Semi-Slav, not the Boleslavsky Variation."""
    keys: set[str] = set()
    if not favourites:
        return frozenset()
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(f) for f in favourites) + r")\b", re.IGNORECASE)
    for op in load_book().all:
        if pattern.search(op.name):
            board = chess.Board()
            for token in op.pgn.split():
                if not token[0].isdigit():
                    board.push_san(token)
                    keys.add(board.epd())
    return frozenset(keys)


def _leads_to(board: chess.Board, move: chess.Move, positions: frozenset[str]) -> bool:
    board.push(move)
    key = board.epd()
    board.pop()
    return key in positions


ADAPTIVE_BOT_ID = "coach"
ADAPTIVE_MATERIAL_EDGE = 2  # pawns ahead/behind (bot's view) that change the bot's strength


def _adaptive(bot: Bot, board: chess.Board) -> tuple[float, float]:
    """Temperature and random-move chance for this move. Only the adaptive bot changes: when the
    player is ahead it plays sharper, when the player is behind it loosens up."""
    temp, rnd = bot.selection.temperature_cp, bot.selection.random_move_prob
    if bot.id != ADAPTIVE_BOT_ID:
        return temp, rnd
    balance = _material_balance(board, board.turn)
    if balance <= -ADAPTIVE_MATERIAL_EDGE:
        return temp * 0.4, 0.0
    if balance >= ADAPTIVE_MATERIAL_EDGE:
        return temp * 2.5, 0.08
    return temp, rnd


async def choose_move(board: chess.Board, bot: Bot, pool: EnginePool, rng: random.Random | None = None) -> BotChoice:
    rng = rng or random.Random()
    legal = list(board.legal_moves)
    if not legal:
        raise ValueError("no legal moves: the game is over")
    temp, random_prob = _adaptive(bot, board)

    if random_prob and rng.random() < random_prob:
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
    # In the opening, a line on the way to one of the bot's favourite openings wins over the others.
    in_book = board.ply() < bot.selection.book_plies
    named = dict(load_book().continuations(board)) if in_book else {}
    favourite = _favourite_positions(bot.personality.favourite_openings) if in_book else frozenset()
    candidates = [(mv, cp) for mv, cp in lines if _leads_to(board, mv, favourite)]
    if favourite and not candidates:
        # the favourite's move is not among the bot's top lines (Mei's 1...c6 at depth 4): judge it at
        # the same depth and play it when it costs no more than the bot's tolerance
        fav_moves = [mv for mv in legal if _leads_to(board, mv, favourite)]
        if fav_moves:
            fav_infos = await pool.play_move(
                board, options={"UCI_LimitStrength": False, "Skill Level": 20},
                depth=bot.search.depth if bot.search.movetime_seconds is None else None,
                time_seconds=bot.search.movetime_seconds, multipv=min(len(fav_moves), 3), root_moves=fav_moves,
            )
            fav_lines = [(i["pv"][0], cp_from_score(i["score"], board.turn)) for i in fav_infos if i.get("pv") and i.get("score") is not None]
            candidates = [(mv, cp) for mv, cp in fav_lines if best_cp - cp <= bot.personality.favourite_max_loss_cp]
            lines = lines + [(mv, cp) for mv, cp in candidates if mv not in dict(lines)]
    candidates = candidates or lines
    balance = _material_balance(board, board.turn)
    if temp <= 0 or len(candidates) == 1:
        chosen = candidates[0][0]
    else:
        scored = []
        for mv, cp in candidates:
            adj = cp + _personality_bonus(board, mv, bot, balance)
            scored.append((mv, adj))
        top = max(a for _, a in scored)
        weights = [math.exp((a - top) / temp) for _, a in scored]
        chosen = rng.choices([m for m, _ in scored], weights=weights, k=1)[0]

    chosen_cp = next(cp for mv, cp in lines if mv == chosen)
    eval_white = chosen_cp if board.turn == chess.WHITE else -chosen_cp
    return BotChoice(
        move=chosen, source="book" if chosen in named else "engine", cp_loss=max(0, best_cp - chosen_cp),
        best_move=best_move, eval_cp=eval_white,
    )
