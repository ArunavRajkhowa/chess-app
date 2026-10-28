"""Chooses a bot's move from honest engine lines. Strength comes from the search depth the bot
is given, the softmax temperature over centipawn loss and the chance of a slip (a move chosen
with one enemy long-range piece out of sight); personality nudges line scores. In the first plies
the bot plays book moves, preferring a line toward one of its favourite named openings. After the
book a bot with a Maia profile draws its move from Maia-3's human-move policy instead."""
from __future__ import annotations

import asyncio
import logging
import math
import random
import re
from dataclasses import dataclass
from functools import lru_cache

import chess
import chess.engine

from ..engine.pool import EnginePool
from ..engine.score import MATE_CP, cp_from_score
from ..openings.book import load_book
from ..review.report import PIECE_VALUES, exchange_gain
from . import maia
from .roster import Bot, MaiaProfile

LOGGER = logging.getLogger("chess.bots")


@dataclass
class BotChoice:
    move: chess.Move
    source: str  # "book" | "engine" | "slip" | "random" | "maia"
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


LONG_RANGE = (chess.BISHOP, chess.ROOK, chess.QUEEN)  # the pieces a slip overlooks
FREE_PIECE_PAWNS = 3  # a slipping bot always takes a capture among its lines that nets at least this much
# a slip may drop a minor piece, never a rook or the queen: 300 cp plus room for depth-2 noise (a guess).
# The engine scores Qxg5?? Bxg5 Bxg5 (queen for knight and bishop) at 396 cp, so _drops_a_major checks material too.
SLIP_MAX_LOSS_CP = 400


def _wins_a_piece(board: chess.Board, move: chess.Move) -> bool:
    """True when the move captures a piece and still nets FREE_PIECE_PAWNS after the opponent's best
    static exchange against the capturing piece this move uses."""
    victim = board.piece_type_at(move.to_square)
    if victim is None or victim == chess.PAWN:
        return False
    after = board.copy(stack=False)
    after.push(move)
    return PIECE_VALUES[victim] - exchange_gain(after, move.to_square) >= FREE_PIECE_PAWNS


def _drops_a_major(board: chess.Board, move: chess.Move) -> bool:
    """True when the move puts the bot's rook or queen where the opponent's best static exchange wins a rook's worth."""
    mover = board.piece_type_at(move.from_square)
    if mover not in (chess.ROOK, chess.QUEEN):
        return False
    taken = board.piece_type_at(move.to_square)
    if taken and PIECE_VALUES[taken] >= PIECE_VALUES[mover]:  # an even trade, not a dropped piece
        return False
    after = board.copy(stack=False)
    after.push(move)
    return exchange_gain(after, move.to_square) >= PIECE_VALUES[chess.ROOK]


def _blind_spot(board: chess.Board, rng: random.Random) -> chess.Board | None:
    """The board with one of the opponent's bishops, rooks or queens removed: the piece a club player
    forgets. None when the side to move is in check or the opponent has no such piece."""
    them = not board.turn
    squares = [sq for sq in chess.SQUARES if board.color_at(sq) == them and board.piece_type_at(sq) in LONG_RANGE]
    if board.is_check() or not squares:
        return None
    blind = board.copy(stack=False)
    blind.remove_piece_at(rng.choice(squares))
    return blind if blind.is_valid() else None


def _shape(probs: dict[chess.Move, float], profile: MaiaProfile) -> dict[chess.Move, float]:
    """Maia's policy at the profile's temperature, cut to the smallest set of moves holding top_p of it, renormalised."""
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    if profile.temperature <= 0:
        return {ranked[0][0]: 1.0}
    weights = [(mv, p ** (1 / profile.temperature)) for mv, p in ranked]
    total = sum(w for _, w in weights)
    kept, mass = {}, 0.0
    for mv, w in weights:
        kept[mv] = w / total
        mass += w / total
        if mass >= profile.top_p:
            break
    return {mv: w / mass for mv, w in kept.items()}


async def _maia_move(board: chess.Board, profile: MaiaProfile, rng: random.Random) -> chess.Move:
    probs = await asyncio.to_thread(maia.policy, board, profile.elo_self, profile.elo_self)
    shaped = _shape(probs, profile)
    return rng.choices(list(shaped), weights=list(shaped.values()), k=1)[0]


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
    in_book = board.ply() < bot.selection.book_plies
    if bot.maia is not None and not in_book:
        # Maia's policy holds legal moves only; its evaluation is not an engine's, so none is reported
        return BotChoice(move=await _maia_move(board, bot.maia, rng), source="maia", cp_loss=0, best_move=None, eval_cp=None)
    temp, random_prob = _adaptive(bot, board)

    if random_prob and rng.random() < random_prob:
        mv = rng.choice(legal)
        return BotChoice(move=mv, source="random", cp_loss=0, best_move=None, eval_cp=None)

    depth = bot.search.depth if bot.search.movetime_seconds is None else None
    slip = None
    if not in_book and bot.selection.slip_prob and rng.random() < bot.selection.slip_prob:
        blind = _blind_spot(board, rng)
        if blind is not None:
            seen = await pool.play_move(blind, options={"UCI_LimitStrength": False, "Skill Level": 20}, depth=depth,
                                        time_seconds=bot.search.movetime_seconds)
            mv = seen[0]["pv"][0] if seen and seen[0].get("pv") else None
            if mv is not None and board.is_legal(mv):
                slip = mv

    multipv = min(bot.search.multipv, len(legal))
    infos = await pool.play_move(
        board,
        options={"UCI_LimitStrength": False, "Skill Level": 20},
        depth=depth,
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
    if slip is not None:
        slip_cp = dict(lines).get(slip)
        if slip_cp is None:
            judged = await pool.play_move(board, options={"UCI_LimitStrength": False, "Skill Level": 20}, depth=depth,
                                          time_seconds=bot.search.movetime_seconds, root_moves=[slip])
            slip_cp = cp_from_score(judged[0]["score"], board.turn) if judged and judged[0].get("score") is not None else None
        # judged on the real board: a slip that gives away more than a minor piece is not played
        # a mate score on either side is the engine's choice, as for the free-piece grab below
        no_mate = slip_cp is not None and max(abs(best_cp), abs(slip_cp)) < MATE_CP - 1000
        if no_mate and best_cp - slip_cp <= SLIP_MAX_LOSS_CP and not _drops_a_major(board, slip):
            eval_white = slip_cp if board.turn == chess.WHITE else -slip_cp
            return BotChoice(move=slip, source="slip", cp_loss=max(0, best_cp - slip_cp), best_move=best_move, eval_cp=eval_white)
    # In the opening, a line on the way to one of the bot's favourite openings wins over the others.
    named = dict(load_book().continuations(board)) if in_book else {}
    favourite = _favourite_positions(bot.personality.favourite_openings) if in_book else frozenset()
    max_loss = bot.personality.favourite_max_loss_cp  # a book move never costs more than this (no free piece)
    fav_top = [(mv, cp) for mv, cp in lines if _leads_to(board, mv, favourite)]
    candidates = [(mv, cp) for mv, cp in fav_top if best_cp - cp <= max_loss]
    if favourite and not fav_top:
        # the favourite's move is not among the bot's top lines (Mei's 1...c6 at depth 4): judge it at
        # the same depth and play it when it costs no more than the bot's tolerance
        fav_moves = [mv for mv in legal if _leads_to(board, mv, favourite)]
        if fav_moves:
            fav_infos = await pool.play_move(
                board, options={"UCI_LimitStrength": False, "Skill Level": 20},
                depth=depth, time_seconds=bot.search.movetime_seconds, multipv=min(len(fav_moves), 3), root_moves=fav_moves,
            )
            fav_lines = [(i["pv"][0], cp_from_score(i["score"], board.turn)) for i in fav_infos if i.get("pv") and i.get("score") is not None]
            candidates = [(mv, cp) for mv, cp in fav_lines if best_cp - cp <= max_loss]
            lines = lines + [(mv, cp) for mv, cp in candidates if mv not in dict(lines)]
    candidates = candidates or [(mv, cp) for mv, cp in lines if mv in named and best_cp - cp <= max_loss] or lines
    balance = _material_balance(board, board.turn)
    grabs = []
    if bot.selection.slip_prob and abs(best_cp) < MATE_CP - 1000:
        # the human-shaped error model only: a club player never leaves a seen free piece, even for a
        # better quiet move; a line with a mate in it is left to the engine's choice
        grabs = [mv for mv, cp in lines if abs(cp) < MATE_CP - 1000 and _wins_a_piece(board, mv)]
    if grabs:
        chosen = grabs[0]
    elif temp <= 0 or len(candidates) == 1:
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
