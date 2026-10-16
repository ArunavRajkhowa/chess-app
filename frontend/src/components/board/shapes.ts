import type { Square } from "../../lib/chess/types";

export type Brush = "green" | "red" | "blue" | "yellow";

export interface Shape {
  orig: Square;
  dest?: Square;
  brush: Brush;
  /** Optional label drawn at the arrow head (e.g. a classification glyph). */
  label?: string;
}

export function shapeKey(s: Shape): string {
  return `${s.orig}${s.dest ?? ""}${s.brush}`;
}

export function toggleShape(list: Shape[], s: Shape): Shape[] {
  const k = `${s.orig}${s.dest ?? ""}`;
  const idx = list.findIndex((x) => `${x.orig}${x.dest ?? ""}` === k);
  if (idx >= 0) {
    const same = list[idx].brush === s.brush;
    const next = list.slice();
    if (same) next.splice(idx, 1);
    else next[idx] = s;
    return next;
  }
  return [...list, s];
}
