import { piecesFromFen, PIECE_VALUES, type Color, type PieceType } from "./types";

const START: Record<PieceType, number> = { p: 8, n: 2, b: 2, r: 2, q: 1, k: 1 };

export interface Captured {
  /** Pieces each side has captured from the other, most valuable first. */
  byWhite: PieceType[];
  byBlack: PieceType[];
  /** Material balance from White's view in pawns. */
  balance: number;
}

export function capturedFromFen(fen: string): Captured {
  const counts: Record<Color, Record<PieceType, number>> = { w: { p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 }, b: { p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 } };
  for (const p of piecesFromFen(fen)) counts[p.color][p.type]++;
  const order: PieceType[] = ["q", "r", "b", "n", "p"];
  const byWhite: PieceType[] = [];
  const byBlack: PieceType[] = [];
  let balance = 0;
  for (const t of order) {
    const whiteLost = Math.max(0, START[t] - counts.w[t]);
    const blackLost = Math.max(0, START[t] - counts.b[t]);
    for (let i = 0; i < blackLost; i++) byWhite.push(t);
    for (let i = 0; i < whiteLost; i++) byBlack.push(t);
    balance += PIECE_VALUES[t] * (counts.w[t] - counts.b[t]);
  }
  return { byWhite, byBlack, balance };
}
