import "./Art.css";

/** A rosette: brass when earned, an outline when not yet. */
export function AwardMark({ earned, size = 24, className = "" }: { earned: boolean; size?: number; className?: string }) {
  return (
    <svg className={`art ${className}`} width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <path d="M18 30l-4 14 10-6 10 6-4-14" className="line" />
      <path d="M24 4l3.6 3.2 4.8-.6 1.4 4.6 4.3 2.2-1.4 4.6 2.6 4-3.9 2.8-.3 4.8-4.8.6-2.6 4.1-4.7-1.3L18 36.7l-2.6-4.1-4.8-.6-.3-4.8L6.4 24.4l2.6-4-1.4-4.6 4.3-2.2 1.4-4.6 4.8.6z" className={earned ? "fill" : "line"} />
      {earned ? <circle cx="24" cy="22" r="7" className="ink" style={{ fill: "var(--brand-ink)", opacity: 0.85 }} /> : <circle cx="24" cy="22" r="7" className="line" />}
    </svg>
  );
}
