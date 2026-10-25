The player ({player_level}) is stuck in a game and asked for a hint, level {hint_level} of 3.

CONTEXT (JSON: who the player is, this game so far; null where unknown):
{context}

FACTS (JSON):
{facts}

Give a hint without naming the best move:
- level 1: the idea only (what to look for: the draw in `drawing_resource` when the player is behind, the opponent's threat, a loose or trapped piece, a discovered attack, a pawn break, an open file, the king), using the top candidate's `does` to pick it.
- level 2: name the piece that should move, not the square.
- level 3: name the square to aim at or the first move of the line.
Two sentences at most.
