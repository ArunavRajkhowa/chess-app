"""Rule-based coaching text from the fact sheet, used when no model is configured or the model
declines. Every sentence is a fact from the sheet, in the same order a model answer follows:
what just happened, the assessment, the plan, what to check, the suggestion, one question back."""
from __future__ import annotations

import chess

BEGINNER = "beginner"
BEGINNER_LINE_PLIES = 3  # a beginner reads a short line; the sheet keeps the whole one
LABELS = {"best": "the best move", "excellent": "an excellent move", "good": "a good move", "book": "a book move",
          "brilliant": "a brilliant sacrifice", "great": "a great move", "inaccuracy": "an inaccuracy",
          "mistake": "a mistake", "miss": "a missed chance", "blunder": "a blunder", "forced": "the only move"}
PROBLEMS = ("inaccuracy", "mistake", "blunder", "miss")


def _side(facts: dict, side: str) -> dict:
    return facts[side]


def _and(parts: list[str]) -> str:
    """One or two reasons as a verb phrase after "it": the reason "checkmate" reads "gives checkmate"."""
    parts = ["gives checkmate" if p == "checkmate" else p for p in parts]
    return parts[0] if len(parts) == 1 else f"{parts[0]} and {parts[1]}"


def _eval(text: str, level: str) -> str:
    return "" if level == BEGINNER else f" ({text})"


def _line(sans: list[str], level: str) -> str:
    return " ".join(sans[:BEGINNER_LINE_PLIES] if level == BEGINNER else sans)


def _mate_allowed(facts_after: dict, mover: str) -> int | None:
    """N when the after-move evaluation (White's view) is a forced mate for the opponent: "-M2" after a
    white move, "M2" after a black move. None otherwise."""
    sign = "-M" if mover == "white" else "M"
    ev = facts_after.get("evaluation") or ""
    return int(ev[len(sign):]) if ev.startswith(sign) and ev[len(sign):].isdigit() else None


def question_back(facts: dict) -> str:
    """One question the player can answer from the board, about the engine's move or the threat."""
    cands = facts.get("candidate_moves") or []
    if not cands:
        return ""
    top = cands[0]
    for d in top.get("does") or []:
        if d.startswith("attacks the"):
            return f"Before you play it: what does {top['move']} attack?"
        if d.startswith("forks"):
            return f"Which two pieces does {top['move']} fork?"
        if d.startswith("pins"):
            return f"What does {top['move']} pin, and to what?"
        if d.startswith("parries") or d.startswith("stops"):
            return f"What was the threat that {top['move']} deals with?"
    threat = facts.get("opponent_threat")
    if threat:
        return f"What happens if you ignore {threat['san']}?"
    return f"What is your opponent's best reply to {top['move']}?"


def check_first(facts: dict) -> str:
    """The one thing to look at before moving: the opponent's threat, a loose or trapped piece."""
    me = facts[facts["side_to_move"]]
    threat = facts.get("opponent_threat")
    rule = (facts.get("threats_against_side_to_move") or [None])[0]
    if threat:
        why = f": it {_and([threat['reason']])}" if threat.get("reason") else ""
        return f"Before you move, see what your opponent wants: {threat['san']}{why}."
    if rule:
        return f"Before you move, check {rule['san']}."
    if me.get("trapped_pieces"):
        return f"Your {me['trapped_pieces'][0]} is attacked and has no safe square."
    if me.get("hanging_pieces"):
        return f"Your {me['hanging_pieces'][0]} is under attack."
    return ""


def plan_text(facts: dict, level: str) -> str:
    """The plan from the imbalances, made concrete with a pawn break, a file or an outpost when there is one."""
    stm = facts["side_to_move"]
    me = facts[stm]
    side = "White" if stm == "white" else "Black"
    parts = []
    if facts.get("endgame"):  # in an endgame the theoretical rule comes before any plan
        parts.append(f"The rule for this {facts['endgame']['rule']}.")
    a = facts.get("assessment")
    if a and a.get("plans", {}).get(side):
        parts.append(f"Your plan: {a['plans'][side][0]}.")
    files = facts.get("files") or {}
    free = [f for f in files.get("open", []) if f not in files.get("rooks_or_queens_on", {})]
    if free and me.get("pieces", {}).get("rook") and facts.get("phase") != "endgame":  # in an endgame the rule speaks
        parts.append(f"The {free[0]}-file is open and nobody has a rook on it yet.")
    top = (facts.get("candidate_moves") or [{}])[0].get("move")
    breaks = [b for b in me.get("pawn_breaks") or [] if b != top]
    if breaks:
        parts.append(f"The pawn break {breaks[0]} is available.")
    if me.get("outposts"):
        parts.append(f"Your knight on {me['outposts'][0]} is an outpost no pawn can chase.")
    for d in me.get("discovered_attacks") or []:
        parts.append(f"Moving the {d['piece']} ({d['moves'][0]}) uncovers the {d['reveals']}.")
        break
    if not parts and facts.get("phase_goal"):
        parts.append(f"Your plan: {facts['phase_goal']}.")
    return " ".join(parts[:1] if level == BEGINNER else parts)


def context_text(facts: dict) -> str:
    """What this game and this player already showed, when it bears on the next move."""
    ctx = facts.get("context") or {}
    game = ctx.get("game") or {}
    parts = []
    mistakes = game.get("earlier_mistakes") or []
    if mistakes:
        m = mistakes[-1]
        parts.append(f"Earlier, move {m['move_number']} {m['san']} was {LABELS.get(m['classification'], m['classification'])} ({m['best']} was better).")
    trend = game.get("eval_trend")
    if trend and trend["direction"] != "steady":
        parts.append(f"The last moves went {trend['direction'].replace('white', 'White').replace('black', 'Black')}.")
    player = ctx.get("player") or {}
    if player.get("weakest_phase") and player["weakest_phase"] == facts.get("phase"):
        parts.append(f"Your reviews say the {facts['phase']} is your weakest phase, so take your time here.")
    return " ".join(parts)


def drawing_text(facts: dict) -> str:
    """The draw the engine finds for the side behind in material, with the resource when the sheet names it."""
    d = facts.get("drawing_resource")
    if not d:
        return ""
    n = abs(facts["material_balance_white"])
    head = f"You are {n} pawn{'s' if n != 1 else ''} down, but the engine finds a draw with {d['move']}"
    if d["kind"] == "perpetual check":
        return f"{head} by perpetual check: {d['text']}."
    if d["kind"] == "stalemate":  # a board fact: the engine's line may draw another way
        line = (facts.get("candidate_moves") or [{}])[0].get("line") or []
        b = chess.Board(facts["fen"])
        for san in line:
            b.push_san(san)
        how = " by stalemate" if b.is_stalemate() else ""
        return f"{head}{how}. A stalemate trick is available: {d['text']}."
    return f"{head}."  # an endgame rule comes with the plan


def material_words(balance: int) -> str:
    """'material is level', 'White is 1 pawn ahead', 'Black is 3 pawns ahead' from White's balance."""
    if balance == 0:
        return "material is level"
    n = abs(balance)
    return f"{'White' if balance > 0 else 'Black'} is {n} pawn{'s' if n != 1 else ''} ahead"


def explain_move_text(*, move_san: str, mover: str, classification: str, best_san: str, best_line: list[str],
                      eval_before: str, eval_after: str, facts_before: dict, facts_after: dict, level: str) -> str:
    parts: list[str] = []
    opp = "black" if mover == "white" else "white"
    after_me = _side(facts_after, mover)
    after_opp = _side(facts_after, opp)
    parts.append(f"{move_san} is {LABELS.get(classification, classification)}.")
    mate_in = _mate_allowed(facts_after, mover)
    purpose = (facts_after.get("last_move") or {}).get("purpose") or []
    threat_before = facts_before.get("opponent_threat")
    if purpose:
        parts.append(f"It {_and(purpose)}.")
    if classification in PROBLEMS and best_san:
        replies = facts_after.get("candidate_moves") or []  # the opponent's best answers to the move
        if mate_in:  # a forced mate outweighs every other reason
            parts.append(f"This allows mate in {mate_in}" + (f": {' '.join(replies[0]['line'])}." if replies else "."))
        else:
            reasons = []
            if after_me.get("hanging_pieces"):
                reasons.append(f"it leaves your {after_me['hanging_pieces'][0]} hanging")
            if after_me.get("trapped_pieces"):
                reasons.append(f"your {after_me['trapped_pieces'][0]} is now trapped")
            # the threat is ignored only when it is still the opponent's best answer after the move
            if threat_before and replies and replies[0]["move"] == threat_before["san"]:
                reasons.append(f"it ignores the threat of {threat_before['san']}")
            if facts_after.get("in_check") and facts_after["side_to_move"] == mover:
                reasons.append("it walks into a check")
            if after_me.get("attackers_near_king", 0) >= 2:
                reasons.append(f"{after_me['attackers_near_king']} enemy pieces now sit near your king on {after_me['king_square']}")
            if not reasons and replies:
                reasons.append(f"it allows {replies[0]['move']}")
            if reasons:
                parts.append("The problem: " + "; ".join(reasons) + ".")
        best = next((c for c in facts_before.get("candidate_moves") or [] if c["move"] == best_san), None)
        does = f", which {_and(best['does'])}" if best and best.get("does") else ""
        evals = "" if level == BEGINNER else f" ({eval_before} before, {eval_after} after your move)"
        parts.append(f"Better was {best_san}{does}{evals}." + (f" The line: {_line(best_line, level)}." if best_line else ""))
    elif classification in ("best", "great", "brilliant", "excellent"):
        cands = facts_before.get("candidate_moves") or []
        if cands:
            parts.append(f"The engine's top line is {_line(cands[0]['line'], level)}{_eval(cands[0]['eval'], level)}.")
        if after_opp.get("hanging_pieces"):
            parts.append(f"It attacks the {after_opp['hanging_pieces'][0]}.")
    if level != BEGINNER and facts_after.get("assessment"):
        parts.append(facts_after["assessment"]["verdict"])
    lesson = _lesson(classification, facts_after, mover, mate_in)
    if lesson:
        parts.append(lesson)
    q = question_back(facts_before) if classification in PROBLEMS else ""
    if q:
        parts.append(q)
    return " ".join(parts)


def _lesson(classification: str, facts_after: dict, mover: str, mate_in: int | None) -> str:
    me = _side(facts_after, mover)
    if classification in ("blunder", "mistake") and me.get("hanging_pieces") and not mate_in:
        return "Lesson: before you move, check which of your pieces the reply could take for free."
    if classification in ("blunder", "mistake"):
        return "Lesson: look at your opponent's checks and captures before committing."
    if classification == "inaccuracy":
        return "Lesson: when two moves look similar, pick the one that also improves your worst piece."
    if facts_after.get("phase") == "opening" and me.get("developed_minors", 2) < 2:
        return "Lesson: in the opening, bring out knights and bishops before anything fancy."
    return ""


def chat_text(facts: dict, question: str, level: str) -> str:
    cands = facts.get("candidate_moves") or []
    lines = []
    for a in facts.get("asked_moves") or []:  # the moves the question names come first: they are what was asked
        if a["reply_text"]:
            answer = f" The engine's answer: {a['reply_text']}; after it {material_words(a['material_after_reply'])}."
        else:
            answer = " The game is over."
        lines.append(a["explanation"] + answer + (f" That is the {a['opening']['name']}." if a["opening"] else ""))
    last = facts.get("last_move") or {}
    if last.get("purpose"):
        lines.append(f"Your opponent's {last['san']} {_and(last['purpose'])}.")
    a = facts.get("assessment")
    if a and level != BEGINNER:
        named = [i for i in a["imbalances"] if i not in a["verdict"]][:2]  # a level verdict names no imbalance
        lines.append(a["verdict"] + (f" Imbalances: {'; '.join(named)}." if named else ""))
    draw = drawing_text(facts)
    if draw:
        lines.append(draw)
    check = check_first(facts) if not facts.get("game_over") else ""
    if check:
        lines.append(check)
    if cands:
        top = cands[0]
        does = f": it {_and(top['does'])}" if top.get("does") else ""
        lines.append(f"The engine prefers {top['move']}{_eval(top['eval'], level)}{does}. Line: {_line(top['line'], level)}.")
        if len(cands) > 1 and level != BEGINNER:
            lines.append(f"An alternative is {cands[1]['move']}{_eval(cands[1]['eval'], level)}.")
    if not facts.get("game_over"):
        plan = plan_text(facts, level)
        if plan:
            lines.append(plan)
    ctx = context_text(facts)
    if ctx:
        lines.append(ctx)
    if facts.get("opening"):
        book = facts.get("book")
        main = f" The main line from here: {' '.join(book['main_line'])}." if book and level != BEGINNER else ""
        lines.append(f"Opening: {facts['opening']['name']}.{main}")
    q = question_back(facts)
    if q:
        lines.append(q)
    if not lines:
        lines.append("The game is over; nothing to suggest here.")
    return " ".join(lines)


def hint_text(facts: dict, hint_level: int) -> str:
    cands = facts.get("candidate_moves") or []
    if not cands:
        return "No hint available: the game is over."
    top = cands[0]
    uci = top["uci"]
    piece_square = uci[:2]
    stm = facts["side_to_move"]
    me = facts[stm]
    opp = facts["black" if stm == "white" else "white"]
    if hint_level <= 1:
        if facts.get("drawing_resource"):
            return f"You are behind in material: look for the draw ({facts['drawing_resource']['kind']})."
        if opp.get("hanging_pieces"):
            return f"Look for a loose piece: the {opp['hanging_pieces'][0]} is not defended well."
        if opp.get("trapped_pieces"):
            return f"The {opp['trapped_pieces'][0]} has no safe square: can you win it?"
        if facts.get("opponent_threat") or facts.get("threats_against_side_to_move"):
            return "First deal with your opponent's threat, then look for your own."
        if me.get("discovered_attacks"):
            return f"Your {me['discovered_attacks'][0]['piece']} is standing in front of one of your own pieces: moving it uncovers something."
        if top.get("does"):
            idea = top["does"][0]
            if idea.startswith("develops"):
                return "Development: get a knight or bishop into play."
            if idea.startswith("puts the rook"):
                return "Think about where your rooks belong: an open file or the seventh rank."
            if idea.startswith(("takes space", "creates a passed", "pushes the passed")):
                return "A pawn move: think about space and passed pawns."
            if idea.startswith(("attacks", "forks", "pins")):
                return "Look for a move that makes a threat the opponent must answer."
        if me.get("developed_minors", 2) < 2 and facts.get("phase") == "opening":
            return "Development: get a knight or bishop into play."
        return "Look for checks, captures and threats, in that order."
    if hint_level == 2:
        return f"The piece on {piece_square} wants to move."
    return f"Aim at {uci[2:4]}."
