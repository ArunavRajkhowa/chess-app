"""Why a move: rules that read the board before and after one move and say what the move does, in
chess words (develops, attacks, pins, parries). No engine here; the annotator adds the engine's view.
Every sentence is a fact about the board, so the narration can never invent a threat."""
from __future__ import annotations

import chess

from ..coach.facts import NAMES, PIECE_VALUES, _passed

CENTRE = {chess.D4, chess.E4, chess.D5, chess.E5}
CENTRE_SQUARES = {chess.D4, chess.E4, chess.D5, chess.E5, chess.C3, chess.D3, chess.E3, chess.F3, chess.C4, chess.F4, chess.C5, chess.F5, chess.C6, chess.D6, chess.E6, chess.F6}
ENDGAME_MATERIAL = 13  # non-pawn material of both sides together, in pawns, below which the king is a fighting piece


def piece_name(board: chess.Board, sq: chess.Square) -> str:
    p = board.piece_at(sq)
    return f"{NAMES[p.piece_type]} on {chess.square_name(sq)}" if p else chess.square_name(sq)


def _value(board: chess.Board, sq: chess.Square) -> int:
    p = board.piece_at(sq)
    return PIECE_VALUES[p.piece_type] if p else 0


def _loose(board: chess.Board, sq: chess.Square, owner: chess.Color) -> bool:
    """A piece attacked and either undefended or attacked by something cheaper than itself."""
    attackers = board.attackers(not owner, sq)
    if not attackers:
        return False
    if not board.attackers(owner, sq):
        return True
    return min(_value(board, a) for a in attackers) < _value(board, sq)


def _targets_of(board: chess.Board, sq: chess.Square, mover: chess.Color) -> list[chess.Square]:
    """Enemy pieces (not the king) the piece on sq attacks and could profitably take: loose, or worth more."""
    own = _value(board, sq)
    out = []
    for t in board.attacks(sq):
        p = board.piece_at(t)
        if p is None or p.color == mover or p.piece_type == chess.KING:
            continue
        if not board.attackers(not mover, t) or PIECE_VALUES[p.piece_type] > own:
            out.append(t)
    return out


def _pinned_to_queen(board: chess.Board, attacker: chess.Square, target: chess.Square, enemy: chess.Color) -> bool:
    """The piece on target shields the enemy queen from the slider on attacker (a relative pin)."""
    if board.piece_type_at(attacker) not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    df = (chess.square_file(target) - chess.square_file(attacker))
    dr = (chess.square_rank(target) - chess.square_rank(attacker))
    step_f, step_r = (df > 0) - (df < 0), (dr > 0) - (dr < 0)
    f, r = chess.square_file(target) + step_f, chess.square_rank(target) + step_r
    while 0 <= f < 8 and 0 <= r < 8:
        p = board.piece_at(chess.square(f, r))
        if p is not None:
            return p.color == enemy and p.piece_type == chess.QUEEN and _value(board, target) < PIECE_VALUES[chess.QUEEN]
        f, r = f + step_f, r + step_r
    return False


def _non_pawn_material(board: chess.Board) -> int:
    return sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING))


def _centre_distance(sq: chess.Square) -> int:
    return min(chess.square_distance(sq, c) for c in CENTRE)


def _file_state(board: chess.Board, file: int, mover: chess.Color) -> str | None:
    """'open' with no pawns on the file, 'half-open' with none of the mover's, else None."""
    own = any(chess.square_file(s) == file for s in board.pieces(chess.PAWN, mover))
    theirs = any(chess.square_file(s) == file for s in board.pieces(chess.PAWN, not mover))
    if own:
        return None
    return "half-open" if theirs else "open"


def move_reasons(board: chess.Board, move: chess.Move) -> list[str]:
    """What the move does, most important first. Empty for a move the rules have nothing to say about."""
    mover = board.turn
    piece = board.piece_at(move.from_square)
    if piece is None:
        return []
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return ["checkmate"]
    out: list[str] = []
    name = NAMES[piece.piece_type]
    to, frm = move.to_square, move.from_square

    captured = board.piece_at(to)
    if board.is_en_passant(move):
        out.append("takes the pawn en passant")
    elif captured is not None:
        victim = NAMES[captured.piece_type]
        recapture = after.is_attacked_by(not mover, to)
        if not recapture:
            out.append(f"takes the {victim} on {chess.square_name(to)} for free")
        elif PIECE_VALUES[captured.piece_type] > PIECE_VALUES[piece.piece_type]:
            out.append(f"wins the {victim} for the {name}")
        elif PIECE_VALUES[captured.piece_type] == PIECE_VALUES[piece.piece_type]:
            out.append(f"trades {name}s" if captured.piece_type == piece.piece_type else f"trades the {name} for the {victim}")
        else:
            out.append(f"gives up the {name} for the {victim}")

    if board.is_check():
        if piece.piece_type == chess.KING:
            out.append("steps out of check")
        elif captured is not None:
            out.append("takes the checking piece")
        else:
            out.append("blocks the check")

    if after.is_check():
        out.append("gives check")

    # threats the moved piece makes from its new square
    targets = _targets_of(after, to, mover)
    if len(targets) >= 2:
        out.append("forks the " + " and the ".join(piece_name(after, t) for t in targets[:2]))
    elif targets:
        out.append(f"attacks the {piece_name(after, targets[0])}")

    # attacks uncovered by the move (another piece's line opened)
    for sq in chess.SQUARES:
        p = after.piece_at(sq)
        if p is None or p.color == mover or p.piece_type == chess.KING or sq in targets:
            continue
        before_atk = board.attackers(mover, sq) - {frm}
        after_atk = after.attackers(mover, sq) - {to}
        new = after_atk - before_atk
        if new and (not after.attackers(not mover, sq) or min(_value(after, a) for a in new) < PIECE_VALUES[p.piece_type]):
            out.append(f"uncovers an attack on the {piece_name(after, sq)}")
            break

    # pins
    if piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        for t in after.attacks(to):
            p = after.piece_at(t)
            if p is None or p.color == mover or p.piece_type == chess.KING:
                continue
            if after.is_pinned(not mover, t) and not board.is_pinned(not mover, t):
                out.append(f"pins the {piece_name(after, t)} to the king")
                break
            if _pinned_to_queen(after, to, t, not mover):
                out.append(f"pins the {piece_name(after, t)} to the queen")
                break

    if board.is_castling(move):
        out.append("castles: the king is safe and the rook comes into play")
    if move.promotion:
        out.append(f"promotes to a {NAMES[move.promotion]}")

    # defends a loose piece; escapes with an attacked one
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p is None or p.color != mover or p.piece_type in (chess.KING, chess.PAWN) or sq == frm:
            continue
        if _loose(board, sq, mover) and board.is_attacked_by(not mover, sq) and after.piece_at(sq) == p and not _loose(after, sq, mover):
            out.append(f"defends the {piece_name(after, sq)}")
            break
    if piece.piece_type not in (chess.KING, chess.PAWN) and _loose(board, frm, mover) and not _loose(after, to, mover) and captured is None:
        out.append(f"moves the attacked {name} to safety")

    home = 0 if mover == chess.WHITE else 7
    if piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(frm) == home and chess.square_rank(to) != home:
        out.append(f"develops the {name}")
    if piece.piece_type == chess.ROOK and chess.square_file(frm) != chess.square_file(to):
        state = _file_state(after, chess.square_file(to), mover)
        if state:
            out.append(f"puts the rook on the {state} {chess.FILE_NAMES[chess.square_file(to)]}-file")
    if piece.piece_type == chess.ROOK and chess.square_rank(to) == (6 if mover == chess.WHITE else 1):
        out.append("puts the rook on the seventh rank")

    if piece.piece_type == chess.PAWN:
        if to in CENTRE and captured is None:
            out.append("takes space in the centre")
        if _passed(after, to, mover) and not _passed(board, frm, mover):
            out.append("creates a passed pawn")
        elif _passed(board, frm, mover) and captured is None:
            out.append("pushes the passed pawn")
        ksq = board.king(mover)
        if ksq is not None and chess.square_distance(frm, ksq) == 1 and chess.square_rank(frm) == home + (1 if mover == chess.WHITE else -1) and chess.square_file(to) in (6, 7):
            out.append("makes luft for the king")
    else:
        # a piece on the square in front of an enemy passed pawn
        ahead = to + (8 if mover == chess.BLACK else -8)
        if 0 <= ahead < 64 and board.piece_type_at(ahead) == chess.PAWN and board.color_at(ahead) != mover and _passed(board, ahead, not mover):
            out.append("blockades the passed pawn")

    if piece.piece_type == chess.KING and not board.is_check() and _non_pawn_material(board) <= ENDGAME_MATERIAL and _centre_distance(to) < _centre_distance(frm):
        out.append("brings the king towards the centre")

    rooks = list(after.pieces(chess.ROOK, mover))
    if len(rooks) == 2 and piece.piece_type != chess.ROOK and not board.is_castling(move):
        a, b = rooks
        if chess.square_rank(a) == chess.square_rank(b) == home and a in after.attacks(b) and a not in board.attacks(b):
            out.append("connects the rooks")
    return out


def forcing_gains(board: chess.Board) -> list[dict]:
    """Mates and profitable captures for the side to move, best first: the same rule as the play API's
    threats, but for the side that is actually on the move."""
    out: list[tuple[int, dict]] = []
    for mv in board.legal_moves:
        san = board.san(mv)
        board.push(mv)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            out.append((100, {"san": san, "uci": mv.uci(), "kind": "mate", "gain": 100}))
            continue
        if board.is_capture(mv):
            victim = board.piece_at(mv.to_square)
            attacker = board.piece_at(mv.from_square)
            if victim is None or attacker is None:
                continue
            defended = board.is_attacked_by(not board.turn, mv.to_square)
            gain = PIECE_VALUES[victim.piece_type] - (0 if not defended else PIECE_VALUES[attacker.piece_type])
            if gain > 0:
                out.append((gain, {"san": san, "uci": mv.uci(), "kind": "capture", "gain": gain}))
    out.sort(key=lambda t: -t[0])
    return [d for _, d in out]


def parried_threat(board: chess.Board, move: chess.Move) -> dict | None:
    """The opponent's best forcing idea before the move that the move takes away, or None."""
    if board.is_check():
        return None
    before = forcing_gains(opponent_to_move(board))
    if not before:
        return None
    top = before[0]
    after = board.copy(stack=False)
    after.push(move)
    if after.is_check():
        return None  # a check is not a parry
    still = {t["uci"]: t["gain"] for t in forcing_gains(after)}
    if top["uci"] in still and still[top["uci"]] >= top["gain"]:
        return None
    return top


def opponent_to_move(board: chess.Board) -> chess.Board:
    """The same position with the other side to move, for "what would they do with a free move".
    Built by hand rather than with a null move, which the UCI layer refuses to send as history."""
    b = board.copy(stack=False)
    b.turn = not b.turn
    b.ep_square = None
    return b
