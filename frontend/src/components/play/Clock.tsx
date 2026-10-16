import "./Clock.css";

export function formatClock(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (ms < 10_000 && ms > 0) return `${m}:${String(s).padStart(2, "0")}.${Math.floor((ms % 1000) / 100)}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function Clock({ ms, active, low }: { ms: number; active: boolean; low: boolean }) {
  return (
    <div className={`clock num ${active ? "active" : ""} ${low ? "low" : ""}`} data-testid="clock" aria-live={active ? "polite" : "off"}>
      {formatClock(ms)}
    </div>
  );
}
