import { Chess } from "chess.js";
import { useMemo, useState } from "react";
import { Board } from "../board/Board";
import { checkSquare, destsFor, safeMove, soundForMove } from "../../lib/chess/game";
import type { PromotionPiece, Square } from "../../lib/chess/types";
import { learnApi } from "../../lib/learnApi";
import { play as playSound } from "../../lib/sound";

export type DrillGoal = "mate" | "promote" | "draw" | "survive" | "win_material";
export interface DrillOutcome { result: "success" | "fail"; reason: string }

interface Props {
  fen: string;
  goal: DrillGoal;
  maxMoves?: number;
  orientation?: "white" | "black";
  onOutcome: (o: DrillOutcome, moves: number) => void;
  /** Changes reset the board (use a key or a counter). */
  resetToken?: number;
}

/** A position played against the engine towards a goal. Shared by lesson drills and the endgame trainer. */
export function DrillBoard({ fen: startFen, goal, maxMoves, orientation, onOutcome, resetToken = 0 }: Props) {
  const [state, setState] = useState<{ token: number; fen: string; moves: number; outcome: DrillOutcome | null; busy: boolean; last: [Square, Square] | null }>({ token: resetToken, fen: startFen, moves: 0, outcome: null, busy: false, last: null });
  if (state.token !== resetToken) {
    setState({ token: resetToken, fen: startFen, moves: 0, outcome: null, busy: false, last: null });
  }
  const chess = useMemo(() => new Chess(state.fen), [state.fen]);
  const learner = new Chess(startFen).turn();
  const dests = useMemo(() => (state.outcome || state.busy ? new Map() : destsFor(chess)), [chess, state.outcome, state.busy]);

  const onMove = async (from: Square, to: Square, promotion?: PromotionPiece) => {
    const c = new Chess(state.fen);
    const mv = safeMove(c, { from, to, promotion });
    if (!mv) return;
    playSound(soundForMove(mv, c));
    setState((s) => ({ ...s, fen: c.fen(), last: [from, to], busy: true }));
    try {
      const r = await learnApi.drillMove(state.fen, from + to + (promotion ?? ""), goal, startFen);
      const n = state.moves + 1;
      let out = r.outcome;
      if (!out && maxMoves && n >= maxMoves) out = { result: "fail", reason: `move limit of ${maxMoves} reached` };
      const apply = () => setState((s) => ({ ...s, fen: r.fen, moves: n, busy: false, outcome: out, last: r.reply ? [r.reply.uci.slice(0, 2), r.reply.uci.slice(2, 4)] : s.last }));
      if (r.reply) {
        setTimeout(() => { apply(); const c2 = new Chess(r.fen); playSound(c2.inCheck() ? "check" : "move"); if (out) onOutcome(out, n); }, 300);
      } else {
        apply();
        if (out) onOutcome(out, n);
      }
      if (out) playSound(out.result === "success" ? "win" : "lose");
    } catch (e) {
      const out = { result: "fail" as const, reason: e instanceof Error ? e.message : String(e) };
      setState((s) => ({ ...s, busy: false, outcome: out }));
      onOutcome(out, state.moves + 1);
    }
  };

  return (
    <div className="stack">
      <Board fen={state.fen} orientation={orientation ?? (learner === "w" ? "white" : "black")} movable={{ color: learner, dests }} lastMove={state.last} check={checkSquare(chess)} onMove={onMove} />
      <div className="row">
        <span className="chip">moves: <b className="num">{state.moves}</b>{maxMoves ? ` / ${maxMoves}` : ""}</span>
        {state.busy && <span className="chip chip-info">engine…</span>}
        {state.outcome && <span className={`chip ${state.outcome.result === "success" ? "chip-ok" : "chip-danger"}`} data-testid={state.outcome.result === "success" ? "task-ok" : "task-bad"}>{state.outcome.result === "success" ? "Done: " : "Not this time: "}{state.outcome.reason}</span>}
      </div>
    </div>
  );
}
