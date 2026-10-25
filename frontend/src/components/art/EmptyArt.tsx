import "./Art.css";

/** Empty states as invitations: a board waiting for a first move, a puzzle box, a signpost. */
const KIND = {
  // games: a board corner, one pawn ready on its square
  games: "M8 20h56M8 36h56M8 52h56M24 4v56M40 4v56M56 4v56M32 22a4 4 0 1 0 .01 0M30 29h4l-1-3h-2zM27 44h10l-2-14h-6zM25 48h14",
  // puzzles: a small board, every square ticked off
  puzzles: "M16 16h40v40H16zM16 36h40M36 16v40M30 44l4 4 8-8",
  // plan: a signpost with two arms and a flag at the top
  plan: "M36 10v52M36 10h18l5 4-5 4H36M36 26H18l-5 4 5 4h18M22 62h28M44 30h4",
} as const;

export function EmptyArt({ kind, size = 72, className = "" }: { kind: keyof typeof KIND; size?: number; className?: string }) {
  return (
    <svg className={`art ${className}`} width={size} height={size} viewBox="0 0 72 72" aria-hidden="true">
      <circle cx="36" cy="36" r="32" className="fill-soft" />
      <path d={KIND[kind]} className="line" />
    </svg>
  );
}
