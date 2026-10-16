import { Chess } from "chess.js";
import { useMemo, useState } from "react";
import { Board } from "../components/board/Board";
import { checkSquare, destsFor, safeMove, soundForMove } from "../lib/chess/game";
import { play as playSound } from "../lib/sound";
import type { PromotionPiece, Square } from "../lib/chess/types";

/** Free board for development and end-to-end tests: both sides move, no server. */
export function BoardDemo() {
  const [chess] = useState(() => new Chess());
  const [fen, setFen] = useState(chess.fen());
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [last, setLast] = useState<[Square, Square] | null>(null);
  const dests = useMemo(() => destsFor(chess), [fen]); // eslint-disable-line react-hooks/exhaustive-deps

  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    const mv = safeMove(chess, { from, to, promotion });
    if (!mv) { playSound("illegal"); return; }
    playSound(soundForMove(mv, chess));
    setLast([from, to]);
    setFen(chess.fen());
  };

  return (
    <div style={{ maxWidth: 560, margin: "24px auto", padding: 16 }}>
      <Board fen={fen} orientation={orientation} movable={{ color: "both", dests }} lastMove={last} check={checkSquare(chess)} onMove={onMove} />
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
        <button className="btn btn-sm" onClick={() => { chess.undo(); setFen(chess.fen()); setLast(null); }}>Undo</button>
        <span className="mono faint" data-testid="demo-fen">{fen}</span>
      </div>
      <pre className="mono faint" data-testid="demo-pgn" style={{ whiteSpace: "pre-wrap" }}>{chess.pgn()}</pre>
    </div>
  );
}
