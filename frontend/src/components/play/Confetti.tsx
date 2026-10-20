import { useEffect, useState } from "react";
import "./Confetti.css";

const COLORS = ["var(--brand)", "var(--side-white)", "var(--c-brilliant)", "var(--c-great)", "var(--c-best)", "var(--accent)"];

/** A short burst of CSS confetti for a win. Respects reduced motion through the --anim token. */
export function Confetti({ show }: { show: boolean }) {
  const [pieces, setPieces] = useState<{ id: number; x: number; d: number; c: string; r: number }[]>([]);
  useEffect(() => {
    if (!show) { setPieces([]); return; }
    setPieces(Array.from({ length: 90 }, (_, i) => ({ id: i, x: Math.random() * 100, d: 0.6 + Math.random() * 1.2, c: COLORS[i % COLORS.length], r: Math.random() * 360 })));
    const t = setTimeout(() => setPieces([]), 3200);
    return () => clearTimeout(t);
  }, [show]);
  if (!pieces.length) return null;
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p) => (
        <i key={p.id} style={{ left: `${p.x}%`, animationDuration: `${p.d + 1.4}s`, animationDelay: `${Math.random() * 0.4}s`, background: p.c, transform: `rotate(${p.r}deg)` }} />
      ))}
    </div>
  );
}
