"""Rule-based coaching text from the fact sheet, used when no Anthropic key is configured or
the model declines. Short, factual, and never wrong about the board because it only reads facts."""
from __future__ import annotations

LEVEL_WORDS = {"beginner": "simple", "intermediate": "", "advanced": "", "master": ""}


def _side(facts: dict, side: str) -> dict:
    return facts[side]


def explain_move_text(*, move_san: str, mover: str, classification: str, best_san: str, best_line: list[str],
                      eval_before: str, eval_after: str, facts_before: dict, facts_after: dict, level: str) -> str:
    parts: list[str] = []
    opp = "black" if mover == "white" else "white"
    after_me = _side(facts_after, mover)
    after_opp = _side(facts_after, opp)
    label = {"best": "the best move", "excellent": "an excellent move", "good": "a good move", "book": "a book move",
             "brilliant": "a brilliant sacrifice", "great": "a great move", "inaccuracy": "an inaccuracy",
             "mistake": "a mistake", "miss": "a missed chance", "blunder": "a blunder", "forced": "the only move"}.get(classification, classification)
    parts.append(f"{move_san} is {label}.")
    if classification in ("inaccuracy", "mistake", "blunder", "miss") and best_san:
        reasons = []
        if after_me["hanging_pieces"]:
            reasons.append(f"it leaves your {after_me['hanging_pieces'][0]} hanging")
        threats = facts_after.get("threats_against_side_to_move") or []
        if facts_after["side_to_move"] == opp and after_opp:
            pass
        if facts_after.get("in_check") and facts_after["side_to_move"] == mover:
            reasons.append("it walks into a check")
        if after_me["attackers_near_king"] >= 2:
            reasons.append(f"{after_me['attackers_near_king']} enemy pieces now sit near your king on {after_me['king_square']}")
        if not reasons and threats:
            reasons.append(f"the opponent now threatens {threats[0]['san']}")
        if reasons:
            parts.append("The problem: " + "; ".join(reasons) + ".")
        parts.append(f"Better was {best_san} ({eval_before} before, {eval_after} after your move)." + (f" The line: {' '.join(best_line)}." if best_line else ""))
    elif classification in ("best", "great", "brilliant", "excellent"):
        cands = facts_before.get("candidate_moves") or []
        if cands:
            parts.append(f"The engine's top line is {' '.join(cands[0]['line'])} with evaluation {cands[0]['eval']}.")
        if after_opp["hanging_pieces"]:
            parts.append(f"It attacks the {after_opp['hanging_pieces'][0]}.")
    lesson = _lesson(classification, facts_after, mover)
    if lesson:
        parts.append(lesson)
    return " ".join(parts)


def _lesson(classification: str, facts_after: dict, mover: str) -> str:
    me = _side(facts_after, mover)
    if classification in ("blunder", "mistake") and me["hanging_pieces"]:
        return "Lesson: before you move, check which of your pieces the reply could take for free."
    if classification in ("blunder", "mistake"):
        return "Lesson: look at your opponent's checks and captures before committing."
    if classification == "inaccuracy":
        return "Lesson: when two moves look similar, pick the one that also improves your worst piece."
    if facts_after["phase"] == "opening" and me["developed_minors"] < 2:
        return "Lesson: in the opening, bring out knights and bishops before anything fancy."
    return ""


def chat_text(facts: dict, question: str, level: str) -> str:
    cands = facts.get("candidate_moves") or []
    stm = facts["side_to_move"]
    me = facts[stm]
    lines = []
    if cands:
        top = cands[0]
        lines.append(f"The engine prefers {top['move']} ({top['eval']}). Line: {' '.join(top['line'])}.")
        if len(cands) > 1:
            lines.append(f"An alternative is {cands[1]['move']} ({cands[1]['eval']}).")
    threats = facts.get("threats_against_side_to_move") or []
    if threats:
        lines.append(f"Watch out for {threats[0]['san']}.")
    if me["hanging_pieces"]:
        lines.append(f"Your {me['hanging_pieces'][0]} is under attack.")
    if facts.get("opening"):
        lines.append(f"Opening: {facts['opening']['name']}.")
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
        if opp["hanging_pieces"]:
            return f"Look for a loose piece: the {opp['hanging_pieces'][0]} is not defended well."
        if (facts.get("threats_against_side_to_move") or []):
            return "First deal with your opponent's threat, then look for your own."
        if me["developed_minors"] < 2 and facts["phase"] == "opening":
            return "Development: get a knight or bishop into play."
        return "Look for checks, captures and threats, in that order."
    if hint_level == 2:
        return f"The piece on {piece_square} wants to move."
    return f"Aim at {uci[2:4]}."
