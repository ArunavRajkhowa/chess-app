import type { PieceType } from "../../lib/chess/types";
import "./PlayerCard.css";

interface Props {
  name: string;
  subtitle?: string;
  avatar: string;
  color: "white" | "black";
  captured: PieceType[];
  materialEdge: number; // positive = this side is ahead
  active?: boolean;
  thinking?: boolean;
  says?: string | null;
}

export function PlayerCard({ name, subtitle, avatar, color, captured, materialEdge, active, thinking, says }: Props) {
  const opp = color === "white" ? "b" : "w";
  return (
    <div className={`playercard ${active ? "active" : ""}`} data-testid={`player-${color}`}>
      <div className="playercard-avatar" aria-hidden="true">{avatar}</div>
      <div className="playercard-body">
        <div className="row">
          <strong>{name}</strong>
          {subtitle && <span className="faint">{subtitle}</span>}
          {thinking && <span className="chip chip-info">thinking…</span>}
        </div>
        <div className="playercard-captured" aria-label="captured pieces">
          {captured.map((t, i) => (
            <i key={i} className={`piece-mini ${opp}${t.toUpperCase()}`} />
          ))}
          {materialEdge > 0 && <span className="playercard-edge num">+{materialEdge}</span>}
        </div>
      </div>
      {says && <div className="playercard-bubble" role="status">{says}</div>}
    </div>
  );
}
