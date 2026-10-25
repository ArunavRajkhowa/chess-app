The player ({player_level}) is looking at a position and asks a question.

CONTEXT (JSON: who the player is, this game so far, the lesson they are in; null where unknown):
{context}

FACTS (JSON):
{facts}

Answer the question using only these facts, in the order the rules give: what just happened, the assessment, the plan, what to check, the alternative, one question back. If the player asks "what should I play", give the top candidate with its reason (`does`) and line, and mention one alternative. If they ask about plans, use `assessment`, the pawn breaks, the files and the outposts.

If the facts contain `asked_moves`, the player asked about those moves (often "why was this not played?"). For each one, say what it is worth (its classification and evaluation against the best move) and why, from its explanation and the engine's reply line. If it reaches a named opening, say so. `reply_text` is the engine's answer with move numbers: a number with "." is White's move, with "..." Black's. `material_after_reply` is White's material minus Black's, in pawns, at the end of that answer: use it to say who stays ahead, never guess.
