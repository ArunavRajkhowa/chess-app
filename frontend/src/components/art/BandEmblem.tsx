import "./Art.css";

/** The piece each band is named after (PLAN.md §3), drawn as an ink line with a brass body. */
const PIECE: string[] = [
  // 0 Pawn
  "M24 11a5 5 0 1 0 .01 0zM21 21h6l-1.5-5.5h-3zM17 35h14l-3-13h-8zM14 39h20",
  // 1 Knight
  "M15 38h18l-1.5-5c6-3 8.5-9 6.5-15-1.5-4-5-7-9.5-8l-1.5-3.5-2.5 4c-6 2-9 7-9 12.5l5 2.5 2.5-3c0 4.5-4 7.5-8 10.5zM27 17a1.2 1.2 0 1 0 .01 0",
  // 2 Bishop
  "M24 7v4M24 13a3.5 3.5 0 1 0 .01 0zM24 17c-6 4-7.5 11.5-3 17h6c4.5-5.5 3-13-3-17zM21 25l6 4M17 36h14M14 40h20",
  // 3 Rook
  "M15 10h4v4h3.5v-4h3v4H29v-4h4v8H15zM18 18v15h12V18M15 35h18v4H15z",
  // 4 Queen
  "M12 17l4 13h16l4-13-6 5.5-4-8.5-4 8.5-6-5.5zM12 15a1.5 1.5 0 1 0 .01 0M36 15a1.5 1.5 0 1 0 .01 0M24 11a1.5 1.5 0 1 0 .01 0M15 34h18M15 38h18",
  // 5 King
  "M24 6v8M20 10h8M17 32h14l1-9.5c-3-2.5-6-2-8 2-2-4-5-4.5-8-2zM15 36h18M15 40h18",
  // 6 Super King: the king, crowned with a star
  "M24 4l1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5zM24 14v4M20 16h8M17 32h14l1-9.5c-3-2.5-6-2-8 2-2-4-5-4.5-8-2zM15 36h18M15 40h18",
  // 7 Candidate: a laurel branch either side of the king's cross
  "M24 10v10M20 14h8M10 36c0-9 4-15 10-19M38 36c0-9-4-15-10-19M12 30l-4-2M14 24l-4-3M17 19l-3-4M36 30l4-2M34 24l4-3M31 19l3-4M17 36h14M15 40h18",
  // 8 Master: the full wreath around the crown
  "M24 16l-4 5h8zM18 21h12l1 7H17zM10 34c-2-10 3-18 12-22M38 34c2-10-3-18-12-22M11 28l-4-1M13 22l-4-2M17 17l-3-4M37 28l4-1M35 22l4-2M31 17l3-4M16 36h16M14 40h20",
];

export function BandEmblem({ band, size = 40, className = "" }: { band: number; size?: number; className?: string }) {
  const d = PIECE[Math.max(0, Math.min(PIECE.length - 1, band))];
  return (
    <svg className={`art ${className}`} width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <circle cx="24" cy="24" r="22" className="fill-soft" />
      <path d={d} className="line" />
    </svg>
  );
}
