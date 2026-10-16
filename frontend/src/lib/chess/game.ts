import { Chess, type Move } from "chess.js";
import type { Color, Square } from "./types";

/** chess.js 1.x throws on an illegal move; most callers want null instead. A king dropped on its
 * own rook is played as that castling move, as on chess.com and lichess. */
export function safeMove(chess: Chess, move: string | { from: string; to: string; promotion?: string }): Move | null {
  if (typeof move !== "string") {
    const { from, to } = move;
    const castle = chess.moves({ verbose: true }).find((m) => m.from === from && castlingRook(m) === to);
    if (castle) move = { from: castle.from, to: castle.to };
  }
  try {
    return chess.move(move);
  } catch {
    return null;
  }
}

/** The square of the rook a castling move uses; null for any other move. */
function castlingRook(mv: Move): Square | null {
  if (mv.flags.includes("k")) return `h${mv.from[1]}` as Square;
  if (mv.flags.includes("q")) return `a${mv.from[1]}` as Square;
  return null;
}

/** Legal destinations per origin, in the shape the Board wants. With rookCastling, the king may
 * also drop on its own rook to castle; the caller must then send the played move (`Move.lan`). */
export function destsFor(chess: Chess, rookCastling = false): Map<Square, Square[]> {
  const m = new Map<Square, Square[]>();
  for (const mv of chess.moves({ verbose: true })) {
    const list = m.get(mv.from) ?? [];
    const rook = rookCastling ? castlingRook(mv) : null;
    for (const to of rook ? [mv.to, rook] : [mv.to]) if (!list.includes(to)) list.push(to);
    m.set(mv.from, list);
  }
  return m;
}

export function kingSquare(chess: Chess, color: Color): Square | null {
  const board = chess.board();
  for (const row of board) {
    for (const cell of row) {
      if (cell && cell.type === "k" && cell.color === color) return cell.square;
    }
  }
  return null;
}

export function checkSquare(chess: Chess): Square | null {
  return chess.inCheck() ? kingSquare(chess, chess.turn()) : null;
}

export function soundForMove(mv: Move, chess: Chess): "move" | "capture" | "check" | "castle" | "promote" {
  if (chess.inCheck()) return "check";
  if (mv.promotion) return "promote";
  if (mv.flags.includes("k") || mv.flags.includes("q")) return "castle";
  if (mv.captured) return "capture";
  return "move";
}

export function resultText(chess: Chess): { result: "1-0" | "0-1" | "1/2-1/2"; reason: string } | null {
  if (!chess.isGameOver()) return null;
  if (chess.isCheckmate()) return { result: chess.turn() === "w" ? "0-1" : "1-0", reason: "checkmate" };
  if (chess.isStalemate()) return { result: "1/2-1/2", reason: "stalemate" };
  if (chess.isThreefoldRepetition()) return { result: "1/2-1/2", reason: "threefold repetition" };
  if (chess.isInsufficientMaterial()) return { result: "1/2-1/2", reason: "insufficient material" };
  if (chess.isDrawByFiftyMoves()) return { result: "1/2-1/2", reason: "fifty-move rule" };
  return { result: "1/2-1/2", reason: "draw" };
}
