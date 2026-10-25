import { useEffect, useRef } from "react";
import type { Classification } from "../../lib/api";
import "./MoveList.css";

export interface MoveListItem {
  ply: number;
  san: string;
  classification?: Classification;
}

interface Props {
  moves: MoveListItem[];
  currentPly: number; // 0 = start position
  onSelect: (ply: number) => void;
  opening?: string | null;
  /** Numbers moves from this position's move number; Black moving first gets an empty "…" cell. */
  startFen?: string | null;
}

export const CLASS_GLYPH: Record<Classification, string> = {
  brilliant: "!!", great: "!", best: "★", excellent: "✓", good: "✓", book: "≡",
  inaccuracy: "?!", mistake: "?", miss: "×", blunder: "??", forced: "□",
};

export function MoveList({ moves, currentPly, onSelect, opening, startFen }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  // Scroll the list only (never the page), only when the move is out of view, and after the frame is
  // painted: layout is clean then, so reading it costs nothing.
  useEffect(() => {
    let t = 0;
    const id = requestAnimationFrame(() => { t = window.setTimeout(() => {
      const list = ref.current;
      const el = list?.querySelector<HTMLElement>(`[data-ply="${currentPly}"]`);
      if (!list || !el) return;
      const l = list.getBoundingClientRect();
      const e = el.getBoundingClientRect();
      if (e.top < l.top) list.scrollTop -= l.top - e.top;
      else if (e.bottom > l.bottom) list.scrollTop += e.bottom - l.bottom;
    }); });
    return () => { cancelAnimationFrame(id); clearTimeout(t); };
  }, [currentPly]);
  const fields = (startFen ?? "").split(" ");
  const firstNumber = Number(fields[5]) || 1;
  const cells: (MoveListItem | null)[] = fields[1] === "b" && moves.length > 0 ? [null, ...moves] : moves;
  const rows: (MoveListItem | null)[][] = [];
  for (let i = 0; i < cells.length; i += 2) rows.push(cells.slice(i, i + 2));
  return (
    <div className="movelist" ref={ref} data-testid="movelist">
      {opening && <div className="movelist-opening">{opening}</div>}
      {rows.map((pair, i) => (
        <div className="movelist-row" key={i}>
          <span className="movelist-num num">{firstNumber + i}.</span>
          {pair.map((m) => (m === null ? <span key="skip" className="movelist-num">…</span> : (
            <button
              key={m.ply}
              type="button"
              data-ply={m.ply}
              className={`movelist-move ${m.ply === currentPly ? "current" : ""} ${m.classification ? `cls-${m.classification}` : ""}`}
              onClick={() => onSelect(m.ply)}
            >
              {m.san}
              {m.classification && m.classification !== "book" && m.classification !== "good" && m.classification !== "excellent" && (
                <i className={`cls-badge cls-${m.classification}`}>{CLASS_GLYPH[m.classification]}</i>
              )}
            </button>
          )))}
        </div>
      ))}
      {moves.length === 0 && <div className="faint" style={{ padding: 8 }}>No moves yet</div>}
    </div>
  );
}
