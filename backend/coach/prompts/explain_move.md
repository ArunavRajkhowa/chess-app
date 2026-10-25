The player ({player_level}) wants to understand this move from their game.

CONTEXT (JSON: who the player is, this game so far; null where unknown):
{context}

Move played: {move_san} by {mover}. Classification by the engine review: {classification}.
Engine's best move: {best_san} ({best_eval}). Best line: {best_line}.
Evaluation before the move (white's view): {eval_before}. After: {eval_after}.
Win chance for the mover: {win_before}% before, {win_after}% after.

FACTS about the position before the move (JSON):
{facts_before}

FACTS about the position after the move (JSON):
{facts_after}

Explain the move: what it does (`last_move.purpose` in the facts after), the threat it faced (`opponent_threat` in the facts before) and whether it met it, the one fact that decides the classification, the better move with its line and its `does` when there was one, the assessment after the move, one lesson to remember, and one question back about the better move.
