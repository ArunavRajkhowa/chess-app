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
}

export const CLASS_GLYPH: Record<Classification, string> = {
  brilliant: "!!", great: "!", best: "★", excellent: "👍", good: "✓", book: "📖",
  inaccuracy: "?!", mistake: "?", miss: "✖", blunder: "??", forced: "→",
};

export function MoveList({ moves, currentPly, onSelect, opening }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>(`[data-ply="${currentPly}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [currentPly]);
  const rows: MoveListItem[][] = [];
  for (let i = 0; i < moves.length; i += 2) rows.push(moves.slice(i, i + 2));
  return (
    <div className="movelist" ref={ref} data-testid="movelist">
      {opening && <div className="movelist-opening">{opening}</div>}
      {rows.map((pair, i) => (
        <div className="movelist-row" key={i}>
          <span className="movelist-num num">{i + 1}.</span>
          {pair.map((m) => (
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
          ))}
        </div>
      ))}
      {moves.length === 0 && <div className="faint" style={{ padding: 8 }}>No moves yet</div>}
    </div>
  );
}
