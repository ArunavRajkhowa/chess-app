import "./Art.css";

interface Props {
  /** The bot id; every feature of the face is derived from it, so a new bot needs no new art.
      A specialist id is "<kind>-<key>-<elo>", so its kind is read from the id. */
  id: string;
  tier?: string;
  /** What the bot specialises in; picks the hat. Unknown kinds fall back to the tier's crest. */
  kind?: string;
  size?: number;
  className?: string;
}

const hash = (s: string) => [...s].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);

// Crests say strength, like the band emblems: a pawn's knob, a knight's ear, a bishop's mitre, a crown.
const CREST: Record<string, string> = {
  beginner: "M24 6a3 3 0 1 0 .01 0M24 9v4",
  intermediate: "M17 14l-1-7 6 5M31 14l1-7-6 5",
  advanced: "M24 4l5 9H19z",
  master: "M15 13l-1-8 5 4 5-6 5 6 5-4-1 8z",
  special: "M15 12h18",
};
// Hats say specialty: a mortarboard, a mask, bricks, a gear, two swords, an open book, a chip.
const HAT: Record<string, string> = {
  coach: "M12 11l12-5 12 5-12 5zM32 12v6M18 13v3c0 2 12 2 12 0v-3",
  trap: "M14 9c3-3 17-3 20 0v5c-3 2-17 2-20 0zM18 12h3M27 12h3",
  defence: "M13 7h22v6H13zM13 13h22M18 7v6M28 7v6M23 13v-6",
  endgame: "M24 5l2 3h3l1 3-2 2 1 3-3 1-2 3-2-3-3-1 1-3-2-2 1-3h3zM24 10a2 2 0 1 0 .01 0",
  attack: "M16 6l10 10M32 6L22 16M16 12l4-4M32 12l-4-4",
  opening: "M13 8c4-2 8-2 11 0 3-2 7-2 11 0v6c-4-2-8-2-11 0-3-2-7-2-11 0z",
  engine: "M16 7h16v9H16zM19 10h3M26 10h3M20 13h8M14 10h2M32 10h2",
};
HAT.middlegame = HAT.attack;
const EYES = ["M19 25a1.5 1.5 0 1 0 .01 0M29 25a1.5 1.5 0 1 0 .01 0", "M19 25a2.5 2.5 0 1 0 .01 0M29 25a2.5 2.5 0 1 0 .01 0", "M17 25h4M27 25h4"];
const BROWS = ["M16 20l6 1M32 20l-6 1", "M16 21h6M26 21h6", "M16 22l6-2M32 22l-6-2"];
const MOUTHS = ["M19 33c2 2 8 2 10 0", "M20 33h8", "M22 32a2 2 0 1 0 4 0M22 32a2 2 0 1 1 4 0", "M19 32c2 3 8 3 10 0l-10 0"];
// a mole, freckles, cheek lines or nothing: the small thing that makes two faces two people
const MARKS = ["", "M31 29a.8 .8 0 1 0 .01 0", "M16 29a.6 .6 0 1 0 .01 0M18 30.5a.6 .6 0 1 0 .01 0M30 29a.6 .6 0 1 0 .01 0M32 30.5a.6 .6 0 1 0 .01 0", "M15 36h4M29 36h4"];

/** A generated face: the id picks eyes, brows and mouth; the tier or kind picks what it wears. */
export function BotAvatar({ id, tier, kind, size = 32, className = "" }: Props) {
  const h = hash(id);
  const top = (kind && HAT[kind]) ?? HAT[id] ?? HAT[id.split("-")[0]] ?? (tier && CREST[tier]) ?? ""; // no tier known: a bare head, never a guessed rank
  return (
    <svg className={`art ${className}`} width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <rect x="12" y="14" width="24" height="28" rx="7" className="fill-soft" />
      <rect x="12" y="14" width="24" height="28" rx="7" className="line" />
      <path d={top} className="line" />
      <path d={BROWS[h % BROWS.length]} className="line" />
      <path d={EYES[(h >> 3) % EYES.length]} className="ink" />
      <path d={MOUTHS[(h >> 6) % MOUTHS.length]} className="line" />
      <path d={MARKS[(h >> 9) % MARKS.length]} className="ink" style={{ stroke: "currentColor", strokeWidth: 1.5 }} />
    </svg>
  );
}
