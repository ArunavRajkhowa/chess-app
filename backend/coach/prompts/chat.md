The player ({player_level}) is looking at a position and asks a question.

FACTS (JSON):
{facts}

Answer the question using only these facts. If the player asks "what should I play", give the top candidate with its reason and line, and mention one alternative. If they ask about plans, use the pawn structure, king safety and piece activity facts.

If the facts contain `asked_moves`, the player asked about those moves (often "why was this not played?"). For each one, say what it is worth (its classification and evaluation against the best move) and why, from its explanation and the engine's reply line. If it reaches a named opening, say so. `reply_text` is the engine's answer with move numbers: a number with "." is White's move, with "..." Black's. `material_after_reply` is White's material minus Black's, in pawns, at the end of that answer: use it to say who stays ahead, never guess.
