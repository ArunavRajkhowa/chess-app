import type { Color, PromotionPiece, Square } from "../../lib/chess/types";
import { fileIndex } from "../../lib/chess/types";

interface Props {
  color: Color;
  square: Square;
  orientation: "white" | "black";
  onPick: (p: PromotionPiece) => void;
  onCancel: () => void;
}

const ORDER: PromotionPiece[] = ["q", "n", "r", "b"];

export function PromotionDialog({ color, square, orientation, onPick, onCancel }: Props) {
  const f = fileIndex(square);
  const col = orientation === "white" ? f : 7 - f;
  const fromTop = (orientation === "white") === (color === "w");
  return (
    <div className="board-promo-backdrop" onPointerDown={onCancel} role="dialog" aria-label="Choose promotion piece">
      <div
        className={`board-promo ${fromTop ? "from-top" : "from-bottom"}`}
        style={{ left: `${col * 12.5}%` }}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {ORDER.map((p) => (
          <button
            key={p}
            type="button"
            className={`board-promo-piece piece ${color}${p.toUpperCase()}`}
            aria-label={`Promote to ${p}`}
            data-testid={`promo-${p}`}
            onClick={() => onPick(p)}
          />
        ))}
      </div>
    </div>
  );
}
