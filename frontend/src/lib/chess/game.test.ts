import { Chess } from "chess.js";
import { describe, expect, it } from "vitest";
import { destsFor, safeMove } from "./game";

const CASTLE = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1";

describe("destsFor", () => {
  it("lists each piece's legal squares, and the rook squares for the king with rookCastling", () => {
    const start = destsFor(new Chess());
    expect(start.get("e2")).toEqual(["e3", "e4"]);
    expect(start.get("e1")).toEqual([]);
    expect(destsFor(new Chess(CASTLE), true).get("e1")?.sort()).toEqual(["a1", "c1", "d1", "f1", "g1", "h1"]);
  });

  it("keeps the position it was made from when the board moves on", () => {
    const c = new Chess();
    const dests = destsFor(c);
    c.move("e4");
    expect(dests.get("e2")).toEqual(["e3", "e4"]);
  });
});

describe("safeMove", () => {
  it("plays a king dropped on its own rook as castling, and returns null for an illegal move", () => {
    expect(safeMove(new Chess(CASTLE), { from: "e1", to: "h1" })?.san).toBe("O-O");
    expect(safeMove(new Chess(CASTLE), { from: "e1", to: "a1" })?.san).toBe("O-O-O");
    expect(safeMove(new Chess("r3k2r/8/8/8/8/8/8/R3K2R w - - 0 1"), { from: "e1", to: "h1" })).toBeNull();
    expect(safeMove(new Chess(), { from: "e2", to: "e5" })).toBeNull();
  });

  it("reads SAN and UCI strings, promotion included", () => {
    expect(safeMove(new Chess(), "Nf3")?.lan).toBe("g1f3");
    expect(safeMove(new Chess(), "g1f3")?.san).toBe("Nf3");
    expect(safeMove(new Chess("8/1P6/8/8/8/8/8/k6K w - - 0 1"), "b7b8n")?.san).toBe("b8=N");
    expect(safeMove(new Chess(), "e2e5")).toBeNull();
  });
});
