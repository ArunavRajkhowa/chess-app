import type { Classification, ReviewedMove } from "../../lib/api";
import "./Review.css";

interface Props {
  graph: number[]; // white win% per position
  moves: ReviewedMove[];
  currentPly: number;
  onSelect: (ply: number) => void;
}

const MARK: Partial<Record<Classification, string>> = { brilliant: "!!", great: "!", blunder: "??", mistake: "?", miss: "✖", inaccuracy: "?!" };

/** Area chart of White's winning chances; click to jump to a move. */
export function EvalGraph({ graph, moves, currentPly, onSelect }: Props) {
  const w = 600;
  const h = 120;
  const n = Math.max(1, graph.length - 1);
  const x = (i: number) => (i / n) * w;
  const y = (p: number) => h - (p / 100) * h;
  const path = graph.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const area = `${path} L${w},${h} L0,${h} Z`;
  const onClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ply = Math.round(((e.clientX - rect.left) / rect.width) * n);
    onSelect(Math.max(0, Math.min(n, ply)));
  };
  return (
    <svg className="evalgraph" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" onClick={onClick} data-testid="evalgraph" role="img" aria-label="Evaluation over the game">
      <rect x={0} y={0} width={w} height={h} className="evalgraph-bg" />
      <path d={area} className="evalgraph-area" />
      <line x1={0} x2={w} y1={h / 2} y2={h / 2} className="evalgraph-mid" />
      <path d={path} className="evalgraph-line" />
      <line x1={x(currentPly)} x2={x(currentPly)} y1={0} y2={h} className="evalgraph-cursor" />
      {moves.filter((m) => m.is_key_moment && MARK[m.classification]).map((m) => (
        <g key={m.ply} transform={`translate(${x(m.ply)}, ${y(graph[m.ply] ?? 50)})`}>
          <circle r={7} className={`evalgraph-mark cls-${m.classification}`} />
          <text y={3} className="evalgraph-mark-text">{MARK[m.classification]}</text>
        </g>
      ))}
    </svg>
  );
}
