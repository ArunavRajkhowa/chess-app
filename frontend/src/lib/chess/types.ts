export type Color = "w" | "b";
export type PieceType = "p" | "n" | "b" | "r" | "q" | "k";
export type PromotionPiece = "q" | "r" | "b" | "n";
export type Square = string; // "a1".."h8"

export interface PieceOnSquare {
  type: PieceType;
  color: Color;
  square: Square;
}

export const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"] as const;
export const RANKS = ["1", "2", "3", "4", "5", "6", "7", "8"] as const;
export const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function fileIndex(sq: Square): number {
  return sq.charCodeAt(0) - 97;
}
export function rankIndex(sq: Square): number {
  return Number(sq[1]) - 1;
}
export function squareAt(file: number, rank: number): Square {
  return FILES[file] + RANKS[rank];
}
export function squareDistance(a: Square, b: Square): number {
  return Math.max(Math.abs(fileIndex(a) - fileIndex(b)), Math.abs(rankIndex(a) - rankIndex(b)));
}
export function isLightSquare(sq: Square): boolean {
  return (fileIndex(sq) + rankIndex(sq)) % 2 === 1;
}

/** Pieces from the placement field of a FEN. Pure and dependency-free so the board stays small. */
export function piecesFromFen(fen: string): PieceOnSquare[] {
  const placement = fen.split(" ")[0];
  const out: PieceOnSquare[] = [];
  const rows = placement.split("/");
  for (let r = 0; r < 8; r++) {
    let file = 0;
    for (const ch of rows[r] ?? "") {
      if (ch >= "1" && ch <= "8") {
        file += Number(ch);
      } else {
        const color: Color = ch === ch.toUpperCase() ? "w" : "b";
        out.push({ type: ch.toLowerCase() as PieceType, color, square: squareAt(file, 7 - r) });
        file++;
      }
    }
  }
  return out;
}

export function turnFromFen(fen: string): Color {
  return (fen.split(" ")[1] as Color) || "w";
}

export const PIECE_NAMES: Record<PieceType, string> = {
  p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king",
};
export const PIECE_VALUES: Record<PieceType, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
