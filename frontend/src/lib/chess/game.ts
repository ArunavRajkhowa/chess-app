import { Chess, type Move } from "chess.js";
import type { Color, Square } from "./types";

/** chess.js 1.x throws on an illegal move; most callers want null instead. */
export function safeMove(chess: Chess, move: string | { from: string; to: string; promotion?: string }): Move | null {
  try {
    return chess.move(move);
  } catch {
    return null;
  }
}

/** Legal destinations per origin, in the shape the Board wants. */
export function destsFor(chess: Chess): Map<Square, Square[]> {
  const m = new Map<Square, Square[]>();
  for (const mv of chess.moves({ verbose: true })) {
    const list = m.get(mv.from) ?? [];
    if (!list.includes(mv.to)) list.push(mv.to);
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
