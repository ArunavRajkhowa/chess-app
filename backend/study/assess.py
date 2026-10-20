"""A grandmaster's look at a position: the imbalances (Silman's word for what differs between the
two sides) and the plan each one suggests. Rules read the board; the engine anchors the verdict."""
from __future__ import annotations

import chess

from ..coach.facts import PIECE_VALUES, _side_facts
from ..engine.pool import EnginePool
from ..engine.score import cp_from_score
from ..review.phases import phase_of
from .reasons import _centre_distance, _non_pawn_material, _passed

ASSESS_DEPTH = 12
SPACE_MIN_GAP = 6
MOBILITY_MIN_GAP = 10
LEVEL_CP, SLIGHT_CP, CLEAR_CP = 40, 120, 300


def _space(board: chess.Board, color: chess.Color) -> int:
    """Squares in the opponent's half this side attacks or occupies."""
    ranks = range(4, 8) if color == chess.WHITE else range(0, 4)
    own = {sq for sq, p in board.piece_map().items() if p.color == color}
    controlled = set()
    for sq in own:
        controlled |= set(board.attacks(sq))
    return sum(1 for sq in controlled | own if chess.square_rank(sq) in ranks)


def _outposts(board: chess.Board, color: chess.Color) -> list[str]:
    out = []
    for sq in board.pieces(chess.KNIGHT, color):
        in_enemy_half = chess.square_rank(sq) >= 4 if color == chess.WHITE else chess.square_rank(sq) <= 3
        if not in_enemy_half or not board.attackers(color, sq) & board.pieces(chess.PAWN, color):
            continue
        if _passed(board, sq, color):  # no enemy pawn can ever attack the square: the same test as a passed pawn
            out.append(chess.square_name(sq))
    return out


def _item(side: str, kind: str, text: str, plan_for: str, plan_against: str) -> dict:
    return {"side": side, "kind": kind, "text": text, "plan_for": plan_for, "plan_against": plan_against}


def imbalances(board: chess.Board) -> list[dict]:
    w, b = _side_facts(board, chess.WHITE), _side_facts(board, chess.BLACK)
    facts = {"White": w, "Black": b}
    other = {"White": "Black", "Black": "White"}
    phase = phase_of(board, board.ply())
    items: list[dict] = []

    diff = w.material - b.material
    if diff:
        side = "White" if diff > 0 else "Black"
        n = abs(diff)
        items.append(_item(side, "material", f"{side} is {n} pawn{'s' if n != 1 else ''} up",
                           "trade pieces, not pawns, and steer for an endgame where the extra material tells",
                           "keep pieces on the board and make threats before the material decides"))
    for side, f in facts.items():
        o = facts[other[side]]
        if f.pieces["bishop"] == 2 and o.pieces["bishop"] < 2:
            items.append(_item(side, "bishop pair", f"{side} has the bishop pair",
                               "open the position and keep pawns on both wings so the bishops have room",
                               "keep the centre closed and trade one of the bishops"))
        if phase != "endgame" and f.castled == "not yet" and o.castled in ("kingside", "queenside"):
            items.append(_item(other[side], "king in the centre", f"{side}'s king is still in the centre",
                               "open the centre now with a pawn break and bring the rooks to the central files",
                               "castle at the first chance; until then keep the centre closed"))
        if f.attackers_near_king >= 2:
            items.append(_item(other[side], "king attack", f"{f.attackers_near_king} enemy pieces stand near {side}'s king on {f.king_square}",
                               "bring one more piece into the attack; look for sacrifices on the pawn cover",
                               "trade the attacking pieces or bring a defender back"))
        elif f.king_shield_pawns <= 1 and f.castled in ("kingside", "queenside") and phase != "endgame" and o.pieces["queen"]:
            items.append(_item(other[side], "weak king cover", f"{side}'s king has {f.king_shield_pawns} pawn{'s' if f.king_shield_pawns != 1 else ''} in front of it",
                               "aim the queen and a rook or bishop at the open king", "keep the queens on only if you can trade the attackers"))
        if f.developed_minors - o.developed_minors >= 2 and phase == "opening":
            items.append(_item(side, "development", f"{side} is ahead in development",
                               "open lines before the opponent catches up", "finish development and keep the position closed until then"))
        if f.isolated_pawns:
            items.append(_item(other[side], "isolated pawn", f"{side} has an isolated pawn on {', '.join(f.isolated_pawns)}",
                               "blockade the square in front of it with a piece, trade minor pieces, then attack it with rooks",
                               "use the half-open files beside it and the space it gives; attack before the endgame"))
        if f.doubled_files:
            items.append(_item(other[side], "doubled pawns", f"{side} has doubled pawns on the {' and '.join(f.doubled_files)}-file",
                               "fix them and attack the front pawn; they cannot defend each other", "use the half-open file they give you"))
        if f.passed_pawns:
            items.append(_item(side, "passed pawn", f"{side} has a passed pawn on {', '.join(f.passed_pawns)}",
                               "put a rook behind it and push it with the king's support", "blockade it with a knight; the square in front of it is the key"))
        for sq in _outposts(board, chess.WHITE if side == "White" else chess.BLACK):
            items.append(_item(side, "outpost", f"{side}'s knight on {sq} is an outpost no pawn can chase",
                               "build around it: it ties the opponent down", "trade it off with a bishop or a knight"))
    if w.open_files_for_rooks:
        file = w.open_files_for_rooks[0]
        items.append(_item("both", "open file", f"the {file}-file is open", "put a rook on it first, then double rooks", "contest it with your own rook"))
    sw, sb = _space(board, chess.WHITE), _space(board, chess.BLACK)
    if abs(sw - sb) >= SPACE_MIN_GAP:
        side = "White" if sw > sb else "Black"
        items.append(_item(side, "space", f"{side} has more space", "avoid trades and keep the opponent cramped",
                           "trade pieces to breathe, and strike at the base of the pawn chain"))
    if abs(w.mobility - b.mobility) >= MOBILITY_MIN_GAP:
        side = "White" if w.mobility > b.mobility else "Black"
        items.append(_item(side, "activity", f"{side}'s pieces are more active", "keep the initiative: make a threat with every move",
                           "improve the worst piece first, one square at a time"))
    if _non_pawn_material(board) <= 13:
        wk, bk = board.king(chess.WHITE), board.king(chess.BLACK)
        if wk is not None and bk is not None and abs(_centre_distance(wk) - _centre_distance(bk)) >= 2:
            side = "White" if _centre_distance(wk) < _centre_distance(bk) else "Black"
            items.append(_item(side, "king activity", f"{side}'s king is the more active one",
                               "use the king as a piece: walk it towards the pawns", "bring your king into play before anything else"))
    return items


def verdict(cp_white: int, items: list[dict]) -> str:
    mag = abs(cp_white)
    if mag < LEVEL_CP:
        side = None
        head = "The position is level"
    else:
        side = "White" if cp_white > 0 else "Black"
        head = f"{side} is {'slightly better' if mag < SLIGHT_CP else 'clearly better' if mag < CLEAR_CP else 'winning'}"
    if side:
        because = [i["text"] for i in items if i["side"] == side][:2]
        if because:
            return f"{head}: {'; '.join(because)}."
    return head + "."


# What a coach says when nothing sets the sides apart: the plan of the phase itself.
PHASE_PLANS = {
    "opening": ["finish development, castle, and connect the rooks before starting anything"],
    "middlegame": ["improve the worst-placed piece, then look for a pawn break that opens lines for it"],
    "endgame": ["bring the king into play and create a passed pawn"],
}


async def assess(board: chess.Board, engine: EnginePool) -> dict:
    items = imbalances(board)
    phase = phase_of(board, board.ply())
    cp = 0
    if not board.is_game_over():
        infos = await engine.analyse(board, depth=ASSESS_DEPTH)
        cp = cp_from_score(infos[0]["score"], chess.WHITE) if infos else 0
    plans = {
        "White": [i["plan_for"] if i["side"] in ("White", "both") else i["plan_against"] for i in items] or PHASE_PLANS[phase],
        "Black": [i["plan_for"] if i["side"] in ("Black", "both") else i["plan_against"] for i in items] or PHASE_PLANS[phase],
    }
    return {
        "fen": board.fen(), "eval_cp": cp, "phase": phase, "verdict": verdict(cp, items), "imbalances": items,
        "plans": {k: list(dict.fromkeys(v))[:4] for k, v in plans.items()},
        "material": {"White": sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color == chess.WHITE),
                     "Black": sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color == chess.BLACK)},
    }
