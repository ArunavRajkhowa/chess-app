import { squareDistance, type PieceOnSquare, type Square } from "../../lib/chess/types";

export interface BoardPiece extends PieceOnSquare {
  id: number;
}

let nextId = 1;

/** Carries piece identities from the previous position into the next one so a moved piece keeps
    its DOM element and animates. Same-square same-piece matches first, then the nearest
    unmatched piece of the same kind, then a pawn that promoted; the rest are new. */
export function reconcilePieces(prev: BoardPiece[], next: PieceOnSquare[]): BoardPiece[] {
  const unmatched = new Set(prev.map((p) => p.id));
  const byId = new Map(prev.map((p) => [p.id, p]));
  const bySquare = new Map(prev.map((p) => [p.square, p]));
  const out: BoardPiece[] = [];
  const pending: PieceOnSquare[] = [];

  for (const n of next) {
    const same = bySquare.get(n.square);
    if (same && same.type === n.type && same.color === n.color && unmatched.has(same.id)) {
      unmatched.delete(same.id);
      out.push({ ...n, id: same.id });
    } else {
      pending.push(n);
    }
  }
  for (const n of pending) {
    let best: BoardPiece | null = null;
    let bestD = Infinity;
    for (const id of unmatched) {
      const p = byId.get(id)!;
      if (p.color !== n.color) continue;
      const promoted = p.type === "p" && n.type !== "p" && (n.square[1] === "8" || n.square[1] === "1");
      if (p.type !== n.type && !promoted) continue;
      const d = squareDistance(p.square, n.square);
      if (d < bestD) { bestD = d; best = p; }
    }
    if (best) {
      unmatched.delete(best.id);
      out.push({ ...n, id: best.id });
    } else {
      out.push({ ...n, id: nextId++ });
    }
  }
  return out;
}

export function squareKey(sq: Square): string { return sq; }
