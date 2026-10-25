"""The position fact sheet: everything the coach may say about a position, computed by rules
and the engine so the model explains facts instead of inventing them. Every move the coach is
allowed to name is in `candidate_moves`, `threats`, `opponent_threat`, `pawn_breaks` or `book`."""
from __future__ import annotations

from dataclasses import dataclass, field

import chess
import chess.engine

from ..engine.pool import EnginePool
from ..engine.score import cp_from_score, describe_score, win_percent_from_cp
from ..openings.book import load_book
from ..review import classify as C
from ..review.phases import ENDGAME, phase_of

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}
MINOR_VALUE = 3  # a discovered attack is worth naming when it hits a piece worth this or more
BOOK_LINE_PLIES = 6
TREND_PLIES = 6
_DIAGONALS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
_STRAIGHTS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_RAYS = {chess.BISHOP: _DIAGONALS, chess.ROOK: _STRAIGHTS, chess.QUEEN: _DIAGONALS + _STRAIGHTS}


@dataclass
class SideFacts:
    material: int
    pieces: dict[str, int]
    king_square: str
    castled: str  # "kingside" | "queenside" | "not yet" | "cannot"
    king_shield_pawns: int
    attackers_near_king: int
    developed_minors: int
    isolated_pawns: list[str]
    doubled_files: list[str]
    passed_pawns: list[str]
    backward_pawns: list[str] = field(default_factory=list)
    hanging_pieces: list[str] = field(default_factory=list)
    pinned_pieces: list[str] = field(default_factory=list)
    mobility: int = 0
    open_files_for_rooks: list[str] = field(default_factory=list)
    trapped_pieces: list[str] = field(default_factory=list)
    pieces_with_no_safe_square: list[str] = field(default_factory=list)
    holes_near_king: list[str] = field(default_factory=list)
    outposts: list[str] = field(default_factory=list)
    pawn_breaks: list[str] = field(default_factory=list)
    discovered_attacks: list[dict] = field(default_factory=list)


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


def _to_move(board: chess.Board, color: chess.Color) -> chess.Board | None:
    """The position with `color` to move, or None when that side's free move would be illegal."""
    if board.turn == color:
        return board
    b = board.copy(stack=False)
    b.turn = color
    b.ep_square = None
    return b if b.is_valid() else None


def _pawn_files(board: chess.Board, color: chess.Color) -> dict[int, list[int]]:
    files: dict[int, list[int]] = {}
    for sq in board.pieces(chess.PAWN, color):
        files.setdefault(chess.square_file(sq), []).append(chess.square_rank(sq))
    return files


def _passed(board: chess.Board, sq: int, color: chess.Color) -> bool:
    f, r = chess.square_file(sq), chess.square_rank(sq)
    ahead = range(r + 1, 8) if color == chess.WHITE else range(0, r)
    for df in (-1, 0, 1):
        ff = f + df
        if 0 <= ff < 8:
            for rr in ahead:
                p = board.piece_at(chess.square(ff, rr))
                if p and p.piece_type == chess.PAWN and p.color != color:
                    return False
    return True


def outposts(board: chess.Board, color: chess.Color) -> list[str]:
    """Knights in the enemy half, guarded by a pawn, that no enemy pawn can ever attack."""
    out = []
    for sq in board.pieces(chess.KNIGHT, color):
        in_enemy_half = chess.square_rank(sq) >= 4 if color == chess.WHITE else chess.square_rank(sq) <= 3
        if not in_enemy_half or not board.attackers(color, sq) & board.pieces(chess.PAWN, color):
            continue
        if _passed(board, sq, color):  # the same test as a passed pawn
            out.append(chess.square_name(sq))
    return out


def discovered_attacks(board: chess.Board, color: chess.Color) -> list[dict]:
    """Own pieces that can step off a line to uncover a slider's attack on the enemy king or a loose or bigger piece."""
    b = _to_move(board, color)
    if b is None:
        return []
    out = []
    for slider_type, rays in _RAYS.items():
        for slider in board.pieces(slider_type, color):
            for df, dr in rays:
                blocker = _first_along(board, slider, df, dr)
                if blocker is None or board.color_at(blocker) != color:
                    continue
                target = _first_along(board, blocker, df, dr)
                if target is None or board.color_at(target) == color:
                    continue
                t = board.piece_type_at(target)
                if t != chess.KING and PIECE_VALUES[t] < MINOR_VALUE:
                    continue
                if t != chess.KING and _value(board, target) <= PIECE_VALUES[slider_type] and board.attackers(not color, target):
                    continue
                line = chess.SquareSet.between(slider, target) | {target}
                moves = [m for m in b.legal_moves if m.from_square == blocker and m.to_square not in line]
                if moves:
                    out.append({
                        "piece": piece_name(board, blocker), "moves": [b.san(m) for m in moves[:2]],
                        "reveals": f"{piece_name(board, slider)} on the {'king' if t == chess.KING else piece_name(board, target)}",
                        "kind": "check" if t == chess.KING else "attack",
                    })
    return out


def _first_along(board: chess.Board, sq: chess.Square, df: int, dr: int) -> chess.Square | None:
    f, r = chess.square_file(sq) + df, chess.square_rank(sq) + dr
    while 0 <= f < 8 and 0 <= r < 8:
        s = chess.square(f, r)
        if board.piece_at(s) is not None:
            return s
        f, r = f + df, r + dr
    return None


def unsafe_pieces(board: chess.Board, color: chess.Color) -> tuple[list[str], list[str]]:
    """(trapped, no safe square): pieces whose every move loses material; trapped ones are attacked now."""
    b = _to_move(board, color)
    if b is None or b.is_check():  # in check the legal moves only answer the check
        return [], []
    trapped, stuck = [], []
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for sq in board.pieces(pt, color):
            moves = [m for m in b.legal_moves if m.from_square == sq]
            if any(_escapes(b, m, color) for m in moves):
                continue
            if _loose(board, sq, color):
                trapped.append(piece_name(board, sq))
            elif moves:  # a piece boxed in by its own side is passive, not in danger
                stuck.append(piece_name(board, sq))
    return trapped, stuck


def _escapes(b: chess.Board, move: chess.Move, color: chess.Color) -> bool:
    victim = b.piece_at(move.to_square)
    if victim is not None and PIECE_VALUES[victim.piece_type] >= _value(b, move.from_square):
        return True
    after = b.copy(stack=False)
    after.push(move)
    return not _loose(after, move.to_square, color)


def holes_near_king(board: chess.Board, color: chess.Color) -> list[str]:
    """Squares beside or in front of the king that no own pawn can ever guard."""
    ksq = board.king(color)
    if ksq is None:
        return []
    step = 1 if color == chess.WHITE else -1
    pawns = _pawn_files(board, color)
    out = []
    for df in (-1, 0, 1):
        for dr in (0, step, 2 * step):
            f, r = chess.square_file(ksq) + df, chess.square_rank(ksq) + dr
            if not (0 <= f < 8 and 0 <= r < 8) or (df == 0 and dr == 0) or r in (0, 7):
                continue
            sq = chess.square(f, r)
            if board.piece_type_at(sq) == chess.PAWN and board.color_at(sq) == color:
                continue
            guard = any(any((rr < r) if color == chess.WHITE else (rr > r) for rr in pawns.get(f + d, [])) for d in (-1, 1))
            if not guard:
                out.append(chess.square_name(sq))
    return out


def pawn_breaks(board: chess.Board, color: chess.Color) -> list[str]:
    """Quiet pawn moves that attack an enemy pawn: the breaks that open the position."""
    b = _to_move(board, color)
    if b is None:
        return []
    out = []
    for m in b.legal_moves:
        if b.piece_type_at(m.from_square) != chess.PAWN or b.is_capture(m) or m.promotion:
            continue
        after = b.copy(stack=False)
        after.push(m)
        if any(after.piece_type_at(t) == chess.PAWN and after.color_at(t) != color for t in after.attacks(m.to_square)):
            out.append(b.san(m))
    return out


def file_facts(board: chess.Board) -> dict:
    """Open and half-open files and who has rooks or queens on them."""
    wp, bp = _pawn_files(board, chess.WHITE), _pawn_files(board, chess.BLACK)
    opened = [f for f in range(8) if f not in wp and f not in bp]
    half = {"white": [f for f in range(8) if f not in wp and f in bp], "black": [f for f in range(8) if f not in bp and f in wp]}
    heavy = {}
    for f in opened + half["white"] + half["black"]:
        sides = {"white" if p.color == chess.WHITE else "black" for sq, p in board.piece_map().items()
                 if chess.square_file(sq) == f and p.piece_type in (chess.ROOK, chess.QUEEN)}
        if sides:
            heavy[chess.FILE_NAMES[f]] = "contested" if len(sides) == 2 else sides.pop()
    return {
        "open": [chess.FILE_NAMES[f] for f in opened],
        "half_open": {k: [chess.FILE_NAMES[f] for f in v] for k, v in half.items()},
        "rooks_or_queens_on": heavy,
    }


def eval_trend(win_percent_white: list[float]) -> dict | None:
    """The last plies' white win% and which way it moved; None with fewer than two points."""
    recent = [round(w, 1) for w in win_percent_white[-TREND_PLIES:]]
    if len(recent) < 2:
        return None
    swing = recent[-1] - recent[0]
    direction = "steady" if abs(swing) < C.INACCURACY_MAX_DROP else "white gaining" if swing > 0 else "black gaining"
    return {"win_percent_white": recent, "direction": direction}


def book_line(board: chess.Board) -> dict | None:
    """The most played book continuation from here and the name it reaches, or None out of book."""
    book = load_book()
    line, name, b = [], None, board.copy(stack=False)
    for _ in range(BOOK_LINE_PLIES):
        moves = book.book_moves(b)
        if not moves:
            break
        mv, op, _count = max(moves, key=lambda t: t[2])
        line.append(b.san(mv))
        b.push(mv)
        name = op.name if op else name
    return {"main_line": line, "leads_to": name} if line else None


# The rule a coach quotes for the endgame on the board, by what is left; checked against the sheet's material.
ENDGAME_RULES = (
    ("pawn", "pawn endgame: put the king in front of the pawn, take the opposition, count the tempi before a race"),
    ("rook", "rook endgame: the rook belongs behind the passed pawn; cut the enemy king off along a file; the Lucena bridge wins, the Philidor third rank draws"),
    ("opposite bishops", "opposite-coloured bishops: the side ahead needs two passed pawns far apart; one is a draw"),
    ("wrong bishop", "wrong-coloured bishop: the bishop cannot cover the rook pawn's queening corner, so a defending king that reaches the corner is a fortress; it is a draw"),
    ("queen", "queen endgame: checks come first; the side with the passed pawn hides the king from checks"),
    ("minor piece", "minor-piece endgame: a knight is weak against a far passed pawn; the bishop is better with pawns on both wings"),
)


def _square_colour(sq: chess.Square) -> int:
    return (chess.square_file(sq) + chess.square_rank(sq)) % 2


def endgame_rule(board: chess.Board) -> dict | None:
    """The kind of endgame and the rule for it, or None before the endgame."""
    if phase_of(board, board.ply()) != ENDGAME:
        return None
    if not board.pieces(chess.PAWN, chess.WHITE) and not board.pieces(chess.PAWN, chess.BLACK):
        return None  # every rule in ENDGAME_RULES is about pawns; a pawnless ending is mating technique
    kinds = {NAMES[pt] for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT) if board.pieces(pt, chess.WHITE) or board.pieces(pt, chess.BLACK)}
    wb, bb = list(board.pieces(chess.BISHOP, chess.WHITE)), list(board.pieces(chess.BISHOP, chess.BLACK))
    if not kinds:
        kind = "pawn"
    elif _wrong_bishop(board):
        kind = "wrong bishop"
    elif kinds == {"bishop"} and len(wb) == len(bb) == 1 and _square_colour(wb[0]) != _square_colour(bb[0]):
        kind = "opposite bishops"
    elif "queen" in kinds:
        kind = "queen"
    elif "rook" in kinds:
        kind = "rook"
    else:
        kind = "minor piece"
    return {"kind": kind, "rule": dict(ENDGAME_RULES)[kind]}


def _wrong_bishop(board: chess.Board) -> bool:
    """King, one bishop and rook pawns on one file against a bare king, the bishop off the queening square's colour."""
    for color in (chess.WHITE, chess.BLACK):
        pawns = board.pieces(chess.PAWN, color)
        bishops = list(board.pieces(chess.BISHOP, color))
        files = {chess.square_file(sq) for sq in pawns}
        if (board.occupied_co[not color] == chess.BB_SQUARES[board.king(not color)] and len(bishops) == 1 and files in ({0}, {7})
                and chess.popcount(board.occupied_co[color]) == 2 + len(pawns)):
            corner = chess.square(files.pop(), 7 if color == chess.WHITE else 0)
            return _square_colour(bishops[0]) != _square_colour(corner)
    return False


def _key(board: chess.Board) -> str:
    return " ".join(board.fen().split()[:4])


def drawing_resource(board: chess.Board, candidates: list[dict], cp_white: int, balance_white: int, endgame: dict | None) -> dict | None:
    """How the side to move, behind in material, holds the draw the engine finds; None when it does not."""
    from ..study.assess import LEVEL_CP

    behind = balance_white if board.turn == chess.BLACK else -balance_white
    if behind <= 0 or not candidates or abs(cp_white) >= LEVEL_CP:
        return None
    top = candidates[0]
    me = board.turn
    movers = {m.from_square for m in board.legal_moves}
    if board.king(me) not in movers and len(movers) == 1:
        sq = movers.pop()
        bare = board.copy(stack=False)
        bare.remove_piece_at(sq)
        if bare.is_stalemate():
            return {"kind": "stalemate", "move": top["move"],
                    "text": f"your king has no legal move, so without the {piece_name(board, sq)} it is stalemate"}
    b, seen, checks, repeats = board.copy(stack=False), {_key(board)}, [], False
    for i, san in enumerate(top["line"]):
        b.push_san(san)
        if i % 2 == 0:
            checks.append(b.is_check())
        repeats |= _key(b) in seen
        seen.add(_key(b))
    if len(checks) >= 2 and all(checks) and repeats:
        return {"kind": "perpetual check", "move": top["move"],
                "text": f"{' '.join(top['line'])} repeats the position"}
    if endgame and endgame["kind"] in ("opposite bishops", "wrong bishop"):
        return {"kind": endgame["kind"], "move": top["move"], "text": endgame["rule"]}
    return None


def _side_facts(board: chess.Board, color: chess.Color) -> SideFacts:
    pieces = {NAMES[pt]: len(board.pieces(pt, color)) for pt in PIECE_VALUES}
    material = sum(PIECE_VALUES[pt] * len(board.pieces(pt, color)) for pt in PIECE_VALUES)
    ksq = board.king(color)
    king_square = chess.square_name(ksq) if ksq is not None else "-"
    home_rank = 0 if color == chess.WHITE else 7
    castled = "not yet"
    if ksq is not None:
        kf = chess.square_file(ksq)
        if chess.square_rank(ksq) == home_rank and kf >= 6:
            castled = "kingside"
        elif chess.square_rank(ksq) == home_rank and kf <= 2:
            castled = "queenside"
        elif not board.has_castling_rights(color):
            castled = "cannot"
    shield = 0
    attackers = 0
    if ksq is not None:
        for df in (-1, 0, 1):
            ff = chess.square_file(ksq) + df
            rr = chess.square_rank(ksq) + (1 if color == chess.WHITE else -1)
            if 0 <= ff < 8 and 0 <= rr < 8:
                p = board.piece_at(chess.square(ff, rr))
                if p and p.piece_type == chess.PAWN and p.color == color:
                    shield += 1
        zone = [s for s in chess.SQUARES if chess.square_distance(s, ksq) <= 2]
        attackers = len({a for s in zone for a in board.attackers(not color, s) if board.piece_type_at(a) not in (chess.PAWN, chess.KING)})
    developed = 0
    for pt in (chess.KNIGHT, chess.BISHOP):
        for sq in board.pieces(pt, color):
            if chess.square_rank(sq) != home_rank:
                developed += 1
    files = _pawn_files(board, color)
    isolated = [chess.square_name(chess.square(f, r)) for f, ranks in files.items() for r in ranks if (f - 1) not in files and (f + 1) not in files]
    doubled = [chess.FILE_NAMES[f] for f, ranks in files.items() if len(ranks) > 1]
    passed = [chess.square_name(sq) for sq in board.pieces(chess.PAWN, color) if _passed(board, sq, color)]
    hanging: list[str] = []
    pinned: list[str] = []
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for sq in board.pieces(pt, color):
            atk = board.attackers(not color, sq)
            if atk:
                defended = board.attackers(color, sq)
                cheapest = min(PIECE_VALUES[board.piece_at(a).piece_type] for a in atk)
                if not defended or cheapest < PIECE_VALUES[pt]:
                    hanging.append(f"{NAMES[pt]} on {chess.square_name(sq)}")
            if board.is_pinned(color, sq):
                pinned.append(f"{NAMES[pt]} on {chess.square_name(sq)}")
    mobility = 0
    if board.turn == color:
        mobility = board.legal_moves.count()
    else:
        b = board.copy()
        b.turn = color
        if not b.is_check():
            mobility = b.legal_moves.count()
    all_files = _pawn_files(board, chess.WHITE), _pawn_files(board, chess.BLACK)
    open_files = [chess.FILE_NAMES[f] for f in range(8) if f not in all_files[0] and f not in all_files[1]]
    if not (pieces["rook"] or pieces["queen"]):  # an open file is a fact only for a side that can use it
        open_files = []
    trapped, stuck = unsafe_pieces(board, color)
    endgame = phase_of(board, board.ply()) == ENDGAME
    return SideFacts(
        material=material, pieces=pieces, king_square=king_square, castled=castled, king_shield_pawns=shield,
        attackers_near_king=attackers, developed_minors=developed, isolated_pawns=isolated, doubled_files=doubled,
        passed_pawns=passed, hanging_pieces=hanging, pinned_pieces=pinned, mobility=mobility, open_files_for_rooks=open_files,
        trapped_pieces=trapped, pieces_with_no_safe_square=stuck, holes_near_king=[] if endgame else holes_near_king(board, color),
        outposts=outposts(board, color), pawn_breaks=pawn_breaks(board, color), discovered_attacks=discovered_attacks(board, color),
    )


def _line_san(board: chess.Board, pv: list[chess.Move], n: int = 6) -> list[str]:
    b = board.copy()
    out = []
    for mv in pv[:n]:
        out.append(b.san(mv))
        b.push(mv)
    return out


async def position_facts(board: chess.Board, pool: EnginePool, *, depth: int = 14, multipv: int = 3,
                         last_move: chess.Move | None = None, previous_fen: str | None = None) -> dict:
    """The fact sheet. `previous_fen` lets a board built from a FEN say what `last_move` did."""
    from ..study.annotate import _threat  # the study's free-move search; it imports this module
    from ..study.assess import PHASE_PLANS, imbalances, plans_from, verdict
    from ..study.reasons import move_reasons
    from ..routers.play import threat_moves  # rule-based threats, shared with the play API

    infos = [] if board.is_game_over() else await pool.analyse(board, depth=depth, multipv=multipv)
    candidates = []
    for info in infos:
        pv = info.get("pv") or []
        if not pv:
            continue
        candidates.append({
            "move": board.san(pv[0]), "uci": pv[0].uci(), "eval": describe_score(info["score"], chess.WHITE),
            "win_percent_white": round(win_percent_from_cp(cp_from_score(info["score"], chess.WHITE)), 1),
            "line": _line_san(board, pv), "does": move_reasons(board, pv[0]),
        })
    white = _side_facts(board, chess.WHITE)
    black = _side_facts(board, chess.BLACK)
    opening = load_book().lookup(board)
    phase = phase_of(board, board.ply())
    items = imbalances(board)
    cp = cp_from_score(infos[0]["score"], chess.WHITE) if infos else 0
    mover_win = candidates[0]["win_percent_white"] if candidates else 50.0
    if board.turn == chess.BLACK:
        mover_win = 100.0 - mover_win
    endgame = endgame_rule(board)
    return {
        "fen": board.fen(),
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "move_number": board.fullmove_number,
        "phase": phase,
        "phase_goal": PHASE_PLANS[phase][0],
        "endgame": endgame,
        "in_check": board.is_check(),
        "game_over": board.is_game_over(),
        "last_move": None if last_move is None else _describe_last_move(board, last_move, previous_fen),
        "opening": {"eco": opening.eco, "name": opening.name} if opening else None,
        "book": book_line(board),
        "evaluation": candidates[0]["eval"] if candidates else ("#" if board.is_checkmate() else "½"),
        "material_balance_white": white.material - black.material,
        "drawing_resource": drawing_resource(board, candidates, cp, white.material - black.material, endgame),
        "assessment": {"verdict": verdict(cp, items), "imbalances": [i["text"] for i in items], "plans": plans_from(items, phase)},
        "files": file_facts(board),
        "white": white.__dict__,
        "black": black.__dict__,
        "candidate_moves": candidates,
        "threats_against_side_to_move": threat_moves(board),
        "opponent_threat": None if board.is_game_over() else await _threat(board, pool, mover_win),
    }


def _describe_last_move(board: chess.Board, move: chess.Move, previous_fen: str | None) -> dict:
    from ..study.annotate import parry_reason
    from ..study.reasons import move_reasons

    if previous_fen:
        b = chess.Board(previous_fen)
    else:
        b = board.copy()
        try:
            b.pop()
        except IndexError:
            return {"uci": move.uci()}
    if move not in b.legal_moves:
        return {"uci": move.uci()}
    san = b.san(move)
    piece = b.piece_at(move.from_square)
    captured = b.piece_at(move.to_square)
    purpose = move_reasons(b, move)
    parry = parry_reason(b, move)
    if parry:
        purpose.insert(0, parry)
    return {
        "san": san, "uci": move.uci(), "piece": NAMES[piece.piece_type] if piece else None,
        "captured": NAMES[captured.piece_type] if captured else None, "gives_check": board.is_check(),
        "is_castling": b.is_castling(move), "purpose": purpose,
    }
