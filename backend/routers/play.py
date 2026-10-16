"""The play API: create a game against a bot, submit a move, get the bot's reply, ask for a
hint or a takeback, resign. The server holds the rules (python-chess) so a game is always legal."""
from __future__ import annotations

import logging
import random

import chess
import chess.pgn
from fastapi import APIRouter, HTTPException

from ..bots.roster import BOTS_BY_ID, bot_public, get_bot
from ..bots.selector import choose_move
from ..engine.pool import pool
from ..engine.score import cp_from_score, describe_score
from ..openings.book import load_book
from ..schema.play import GameState, HintResponse, MoveRecord, MoveRequest, MoveResponse, NewGameRequest
from ..storage import games as store

LOGGER = logging.getLogger("chess.play")
router = APIRouter(prefix="/api/play", tags=["play"])

HINT_DEPTH = 16
LIVE_EVAL_DEPTH = 12
PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _board_from_moves(moves: list[dict], start_fen: str | None = None) -> chess.Board:
    board = chess.Board(start_fen) if start_fen else chess.Board()
    for m in moves:
        board.push_uci(m["uci"])
    return board


def _board_of(row: dict) -> chess.Board:
    return _board_from_moves(row["moves"], row.get("start_fen"))


def _pgn(moves: list[dict], row: dict, bot_name: str) -> str:
    game = chess.pgn.Game()
    white = "You" if row["player_color"] == "white" else bot_name
    black = bot_name if row["player_color"] == "white" else "You"
    game.headers["Event"] = "Chess Coach bot game"
    game.headers["White"] = white
    game.headers["Black"] = black
    game.headers["Result"] = row.get("result") or "*"
    if row.get("start_fen"):
        game.setup(chess.Board(row["start_fen"]))
    if row.get("time_control"):
        minutes, inc = row["time_control"].split("+")
        game.headers["TimeControl"] = f"{int(minutes) * 60}+{inc}"
    if row.get("opening_eco"):
        game.headers["ECO"] = row["opening_eco"]
    if row.get("opening_name"):
        game.headers["Opening"] = row["opening_name"]
    node = game
    for m in moves:
        node = node.add_variation(chess.Move.from_uci(m["uci"]))
    return str(game)


def _termination(board: chess.Board) -> tuple[str, str] | None:
    if board.is_checkmate():
        return ("0-1" if board.turn == chess.WHITE else "1-0", "checkmate")
    if board.is_stalemate():
        return ("1/2-1/2", "stalemate")
    if board.is_insufficient_material():
        return ("1/2-1/2", "insufficient material")
    if board.can_claim_threefold_repetition():
        return ("1/2-1/2", "threefold repetition")
    if board.can_claim_fifty_moves():
        return ("1/2-1/2", "fifty-move rule")
    return None


async def _state(row: dict) -> GameState:
    moves = row["moves"]
    board = _board_of(row)
    bot = get_bot(row["bot_id"]) if row.get("bot_id") else None
    opening = None
    if not row.get("start_fen"):
        opening, _ = load_book().classify_game([chess.Move.from_uci(m["uci"]) for m in moves])
    return GameState(
        id=row["id"],
        fen=board.fen(),
        pgn=row.get("pgn") or _pgn(moves, row, bot.name if bot else "Opponent"),
        moves=[MoveRecord(**m) for m in moves],
        status=row["status"],
        result=row.get("result"),
        termination=row.get("termination"),
        player_color=row["player_color"],
        bot=bot_public(bot) if bot else {"id": "import", "name": row.get("black_name") or "Import", "avatar": "📄",
                                         "white_name": row.get("white_name"), "black_name": row.get("black_name")},
        coach_mode=bool(row.get("coach_mode")),
        time_control=row.get("time_control"),
        start_fen=row.get("start_fen"),
        opening={"eco": opening.eco, "name": opening.name} if opening else None,
        last_move=[moves[-1]["uci"][:2], moves[-1]["uci"][2:4]] if moves else None,
        in_check=board.is_check(),
        turn="w" if board.turn == chess.WHITE else "b",
        legal_moves=[m.uci() for m in board.legal_moves] if row["status"] == "active" else [],
        threats=threat_moves(board) if row["status"] == "active" else [],
    )


async def _persist(row: dict, board: chess.Board) -> None:
    bot = get_bot(row["bot_id"])
    term = _termination(board)
    if term:
        row["status"] = "finished"
        row["result"], row["termination"] = term
    opening = None
    if not row.get("start_fen"):
        opening, _ = load_book().classify_game([chess.Move.from_uci(m["uci"]) for m in row["moves"]])
    row["opening_eco"] = opening.eco if opening else None
    row["opening_name"] = opening.name if opening else None
    row["pgn"] = _pgn(row["moves"], row, bot.name)
    await store.save_game(
        row["id"], moves=row["moves"], pgn=row["pgn"], status=row["status"], result=row.get("result"),
        termination=row.get("termination"), opening_eco=row["opening_eco"], opening_name=row["opening_name"],
    )


async def _bot_reply(row: dict, board: chess.Board) -> MoveRecord | None:
    if board.is_game_over(claim_draw=True):
        return None
    bot = get_bot(row["bot_id"])
    choice = await choose_move(board, bot, pool)
    san = board.san(choice.move)
    board.push(choice.move)
    rec = {
        "ply": board.ply(), "san": san, "uci": choice.move.uci(), "fen": board.fen(),
        "by": "bot", "source": choice.source, "eval_cp": choice.eval_cp,
    }
    row["moves"].append(rec)
    return MoveRecord(**rec)


def _bot_comment(row: dict) -> str | None:
    bot = get_bot(row["bot_id"])
    if row["status"] != "finished":
        return None
    result = row.get("result")
    if result == "1/2-1/2":
        return bot.on_draw
    player_won = (result == "1-0") == (row["player_color"] == "white")
    return bot.on_loss if player_won else bot.on_win


def _parse_move(board: chess.Board, text: str) -> chess.Move:
    text = text.strip()
    looks_uci = len(text) in (4, 5) and text[0] in "abcdefgh" and text[1].isdigit() and text[2] in "abcdefgh"
    try:
        return chess.Move.from_uci(text) if looks_uci else board.parse_san(text)
    except ValueError:
        raise HTTPException(400, f"cannot parse move {text!r}")


@router.post("/games", response_model=GameState)
async def new_game(req: NewGameRequest) -> GameState:
    if req.bot_id not in BOTS_BY_ID:
        raise HTTPException(404, f"unknown bot {req.bot_id!r}")
    color = req.player_color if req.player_color != "random" else random.choice(["white", "black"])
    start_fen = None
    if req.fen:
        try:
            start_board = chess.Board(req.fen)
        except ValueError:
            raise HTTPException(400, f"bad FEN {req.fen!r}")
        if not start_board.is_valid() or start_board.is_game_over():
            raise HTTPException(400, "the start position is illegal or already finished")
        start_fen = start_board.fen()
    game_id = await store.insert_game(player_color=color, bot_id=req.bot_id, coach_mode=req.coach_mode,
                                      time_control=req.time_control, start_fen=start_fen)
    row = await store.read_game(game_id)
    assert row is not None
    board = _board_of(row)
    bot_to_move = board.turn != (chess.WHITE if color == "white" else chess.BLACK)
    if bot_to_move:
        await _bot_reply(row, board)
    await _persist(row, board)
    return await _state(row)


@router.get("/games")
async def games_index() -> dict:
    rows = await store.list_games()
    for r in rows:
        bot = BOTS_BY_ID.get(r["bot_id"])
        r["bot_name"] = bot.name if bot else (f'{r.get("white_name")} vs {r.get("black_name")}' if r.get("source") == "import" else r["bot_id"])
        r["bot_avatar"] = bot.avatar if bot else "📄"
    return {"games": rows}


@router.get("/games/{game_id}", response_model=GameState)
async def get_game(game_id: str) -> GameState:
    row = await store.read_game(game_id)
    if not row:
        raise HTTPException(404, "no such game")
    return await _state(row)


@router.post("/games/{game_id}/move", response_model=MoveResponse)
async def make_move(game_id: str, req: MoveRequest) -> MoveResponse:
    row = await store.read_game(game_id)
    if not row:
        raise HTTPException(404, "no such game")
    if row["status"] != "active":
        raise HTTPException(409, "game is finished")
    board = _board_of(row)
    player_is_white = row["player_color"] == "white"
    if board.turn != (chess.WHITE if player_is_white else chess.BLACK):
        raise HTTPException(409, "not your turn")
    move = _parse_move(board, req.move)
    if move not in board.legal_moves:
        raise HTTPException(400, f"illegal move {req.move!r} in {board.fen()}")

    san = board.san(move)
    board.push(move)
    player_rec = {"ply": board.ply(), "san": san, "uci": move.uci(), "fen": board.fen(), "by": "player", "source": None, "eval_cp": None}
    row["moves"].append(player_rec)

    bot_rec = None
    if not _termination(board):
        bot_rec = await _bot_reply(row, board)
    await _persist(row, board)

    eval_cp = None
    eval_text = None
    if req.want_eval and row["status"] == "active":
        infos = await pool.analyse(board, depth=LIVE_EVAL_DEPTH)
        eval_cp = cp_from_score(infos[0]["score"], chess.WHITE)
        eval_text = describe_score(infos[0]["score"], chess.WHITE)
    return MoveResponse(
        game=await _state(row), player_move=MoveRecord(**player_rec), bot_move=bot_rec,
        bot_says=_bot_comment(row), eval_cp=eval_cp, eval_text=eval_text,
    )


@router.post("/games/{game_id}/resign", response_model=GameState)
async def resign(game_id: str) -> GameState:
    row = await store.read_game(game_id)
    if not row:
        raise HTTPException(404, "no such game")
    if row["status"] != "active":
        raise HTTPException(409, "game is finished")
    row["status"] = "finished"
    row["result"] = "0-1" if row["player_color"] == "white" else "1-0"
    row["termination"] = "resignation"
    await _persist(row, _board_of(row))
    return await _state(row)


@router.post("/games/{game_id}/flag", response_model=GameState)
async def flag(game_id: str) -> GameState:
    """The player's clock ran out. The browser keeps the clock; the server records the result."""
    row = await store.read_game(game_id)
    if not row:
        raise HTTPException(404, "no such game")
    if row["status"] != "active":
        raise HTTPException(409, "game is finished")
    if not row.get("time_control"):
        raise HTTPException(409, "this game has no clock")
    row["status"] = "finished"
    row["result"] = "0-1" if row["player_color"] == "white" else "1-0"
    row["termination"] = "timeout"
    await _persist(row, _board_of(row))
    return await _state(row)


@router.post("/games/{game_id}/takeback", response_model=GameState)
async def takeback(game_id: str) -> GameState:
    """Undo the player's last move and the bot's reply to it."""
    row = await store.read_game(game_id)
    if not row:
        raise HTTPException(404, "no such game")
    if row["status"] != "active":
        raise HTTPException(409, "game is finished")
    moves = row["moves"]
    while moves and moves[-1]["by"] == "bot":
        moves.pop()
    if moves and moves[-1]["by"] == "player":
        moves.pop()
    await _persist(row, _board_of(row))
    return await _state(row)


@router.get("/games/{game_id}/hint", response_model=HintResponse)
async def hint(game_id: str) -> HintResponse:
    row = await store.read_game(game_id)
    if not row:
        raise HTTPException(404, "no such game")
    board = _board_of(row)
    if board.is_game_over(claim_draw=True):
        raise HTTPException(409, "game is finished")
    infos = await pool.analyse(board, depth=HINT_DEPTH)
    pv = infos[0]["pv"]
    best = pv[0]
    line_san = []
    b = board.copy()
    for mv in pv[:6]:
        line_san.append(b.san(mv))
        b.push(mv)
    return HintResponse(
        move_uci=best.uci(), move_san=board.san(best), eval_text=describe_score(infos[0]["score"], board.turn),
        line_san=line_san, threats=threat_sans(board),
    )


def threat_moves(board: chess.Board) -> list[dict]:
    """What the opponent would do if it were their move: mates, then captures of undefended or
    higher-value pieces. Cheap, rules-only, no engine. Mates first, then by material."""
    b = board.copy()
    if b.is_check():
        return []
    b.push(chess.Move.null())
    out: list[tuple[int, dict]] = []
    for mv in b.legal_moves:
        san = b.san(mv)
        b.push(mv)
        mate = b.is_checkmate()
        b.pop()
        if mate:
            out.append((100, {"san": san, "uci": mv.uci(), "kind": "mate", "gain": 100}))
            continue
        if b.is_capture(mv):
            victim = b.piece_at(mv.to_square)
            attacker = b.piece_at(mv.from_square)
            if victim is None or attacker is None:
                continue
            defended = b.is_attacked_by(not b.turn, mv.to_square)
            gain = PIECE_VALUES[victim.piece_type] - (0 if not defended else PIECE_VALUES[attacker.piece_type])
            if gain > 0:
                out.append((gain, {"san": san, "uci": mv.uci(), "kind": "capture", "gain": gain}))
    out.sort(key=lambda t: -t[0])
    return [d for _, d in out[:4]]


def threat_sans(board: chess.Board) -> list[str]:
    return [t["san"] for t in threat_moves(board)]
