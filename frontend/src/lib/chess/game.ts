import { Chess, type Move, type Square as ChessSquare } from "chess.js";
import type { Color, Square } from "./types";

/** chess.js 1.x throws on an illegal move; most callers want null instead. A king dropped on its
 * own rook is played as that castling move, as on chess.com and lichess. */
export function safeMove(chess: Chess, move: string | { from: string; to: string; promotion?: string }): Move | null {
  // chess.js reads a UCI string by writing the SAN of every legal move first; the object form does not
  if (typeof move === "string" && /^[a-h][1-8][a-h][1-8][qrbn]?$/.test(move)) move = { from: move.slice(0, 2), to: move.slice(2, 4), promotion: move[4] };
  if (typeof move !== "string") {
    const { from, to } = move;
    const king = chess.get(from as ChessSquare);
    const rook = chess.get(to as ChessSquare);
    // an e-file king on its own a- or h-rook goes two files over, which only castling allows; chess.move judges it
    if (king?.type === "k" && rook?.type === "r" && rook.color === king.color && from[0] === "e" && (to[0] === "a" || to[0] === "h")) {
      move = { from, to: `${to[0] === "h" ? "g" : "c"}${from[1]}` };
    }
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

/** Legal destinations per origin, in the shape the Board wants (it only calls `get`), worked out per
 * square on first ask. With rookCastling, the king may also drop on its own rook to castle; the caller
 * must then send the played move (`Move.lan`). The position is fixed when this is called. */
export function destsFor(chess: Chess, rookCastling = false): Map<Square, Square[]> {
  const fen = chess.fen();
  let board: Chess | null = null;
  return new (class extends Map<Square, Square[]> {
    get(sq: Square): Square[] {
      let list = super.get(sq);
      if (!list) {
        board ??= new Chess(fen);
        list = [];
        for (const mv of board.moves({ square: sq as ChessSquare, verbose: true })) {
          const rook = rookCastling ? castlingRook(mv) : null;
          for (const to of rook ? [mv.to, rook] : [mv.to]) if (!list.includes(to)) list.push(to);
        }
        super.set(sq, list);
      }
      return list;
    }
  })();
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

/** SAN moves from a position with move numbers, the way a book prints them: "5...Nxe4 6.d4 b5". */
export function numberedSan(fen: string, sans: string[]): string {
  const [, turn, , , , full] = fen.split(" ");
  let n = Number(full) || 1;
  let white = turn === "w";
  return sans.map((san, i) => {
    const text = white ? `${n}.${san}` : i === 0 ? `${n}...${san}` : san;
    if (!white) n += 1;
    white = !white;
    return text;
  }).join(" ");
}
