import { useEffect, useState } from "react";
import { api, type BotPublic } from "../../lib/api";
import "./BotPicker.css";

const TIERS: { key: BotPublic["tier"]; label: string; blurb: string }[] = [
  { key: "beginner", label: "Beginner", blurb: "250–800. Learn the pieces, win some games." },
  { key: "intermediate", label: "Intermediate", blurb: "1000–1600. Club strength." },
  { key: "advanced", label: "Advanced", blurb: "1800–2400. Serious opposition." },
  { key: "master", label: "Master", blurb: "2600–3200. Engines in disguise." },
  { key: "special", label: "Personalities", blurb: "Coach, trap setters, grinders." },
];

interface Props {
  onStart: (bot: BotPublic, color: "white" | "black" | "random", coachMode: boolean) => void;
  busy?: boolean;
  initialBotId?: string;
}

export function BotPicker({ onStart, busy, initialBotId }: Props) {
  const [bots, setBots] = useState<BotPublic[]>([]);
  const [selected, setSelected] = useState<BotPublic | null>(null);
  const [color, setColor] = useState<"white" | "black" | "random">("white");
  const [coachMode, setCoachMode] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.bots()
      .then((r) => {
        setBots(r.bots);
        const pick = r.bots.find((b) => b.id === (initialBotId ?? "nova")) ?? r.bots[0] ?? null;
        setSelected(pick);
      })
      .catch((e: Error) => setError(e.message));
  }, [initialBotId]);

  return (
    <div className="botpicker" data-testid="botpicker">
      <div className="botpicker-list">
        {error && <div className="chip chip-danger">Could not load bots: {error}</div>}
        {TIERS.map((tier) => {
          const list = bots.filter((b) => b.tier === tier.key);
          if (!list.length) return null;
          return (
            <section key={tier.key} className="botpicker-tier">
              <header>
                <h3>{tier.label}</h3>
                <span className="faint">{tier.blurb}</span>
              </header>
              <div className="botpicker-grid">
                {list.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    className={`botcard ${selected?.id === b.id ? "selected" : ""}`}
                    onClick={() => { setSelected(b); if (b.id === "coach") setCoachMode(true); }}
                    data-testid={`bot-${b.id}`}
                  >
                    <span className="botcard-avatar" aria-hidden="true">{b.avatar}</span>
                    <span className="botcard-name">{b.name}</span>
                    <span className="botcard-elo num">{b.elo}</span>
                  </button>
                ))}
              </div>
            </section>
          );
        })}
      </div>

      <aside className="botpicker-side card">
        {selected ? (
          <>
            <div className="botpicker-hero">
              <span className="botpicker-hero-avatar" aria-hidden="true">{selected.avatar}</span>
              <div>
                <h2>{selected.name}</h2>
                <div className="muted">{selected.tagline} · <span className="num">{selected.elo}</span></div>
              </div>
            </div>
            <p className="muted">{selected.description}</p>
            {selected.personality.favourite_openings.length > 0 && (
              <div className="row" style={{ flexWrap: "wrap" }}>
                {selected.personality.favourite_openings.map((o) => <span key={o} className="chip">{o}</span>)}
              </div>
            )}
            <div className="botpicker-colors" role="radiogroup" aria-label="Play as">
              {(["white", "random", "black"] as const).map((c) => (
                <button key={c} type="button" role="radio" aria-checked={color === c} className={`colorbtn ${c} ${color === c ? "on" : ""}`} onClick={() => setColor(c)} title={`Play as ${c}`}>
                  {c === "random" ? "?" : ""}
                </button>
              ))}
            </div>
            <label className="row" style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={coachMode} onChange={(e) => setCoachMode(e.target.checked)} />
              <span>Coach mode: move feedback, hints, takebacks and threats</span>
            </label>
            <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={() => onStart(selected, color, coachMode)} data-testid="start-game">
              {busy ? "Starting…" : `Play ${selected.name}`}
            </button>
          </>
        ) : (
          <p className="faint">Loading bots…</p>
        )}
      </aside>
    </div>
  );
}
