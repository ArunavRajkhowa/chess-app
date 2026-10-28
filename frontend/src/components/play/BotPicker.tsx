import { useEffect, useState } from "react";
import { api, type BotPublic } from "../../lib/api";
import { BotAvatar } from "../art";
import "./BotPicker.css";

const TIERS: { key: BotPublic["tier"]; label: string; blurb: string }[] = [
  { key: "beginner", label: "Beginner", blurb: "250–800. Learn the pieces, win some games." },
  { key: "intermediate", label: "Intermediate", blurb: "1000–1600. Club strength." },
  { key: "advanced", label: "Advanced", blurb: "1800–2400. Serious opposition." },
  { key: "master", label: "Master", blurb: "2600–3200. Engines in disguise." },
  { key: "special", label: "Personalities", blurb: "Coach, trap setters, grinders." },
];

// The specialists are generated per course and theme (backend/bots/specialists.py); the filter keeps the list readable.
type Filter = "classic" | "opening" | "middlegame" | "endgame";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "classic", label: "Classic" }, { key: "opening", label: "Openings" }, { key: "middlegame", label: "Middlegame" }, { key: "endgame", label: "Endgame" },
];

const TIME_CONTROLS: { key: string | null; label: string }[] = [
  { key: null, label: "No clock" }, { key: "1+0", label: "1 min" }, { key: "3+2", label: "3 | 2" }, { key: "5+0", label: "5 min" },
  { key: "10+0", label: "10 min" }, { key: "15+10", label: "15 | 10" }, { key: "30+0", label: "30 min" },
];

interface Props {
  onStart: (bot: BotPublic, color: "white" | "black" | "random", coachMode: boolean, timeControl: string | null) => void;
  busy?: boolean;
  initialBotId?: string;
  initialColor?: "white" | "black";
}

export function BotPicker({ onStart, busy, initialBotId, initialColor }: Props) {
  const [bots, setBots] = useState<BotPublic[]>([]);
  const [selected, setSelected] = useState<BotPublic | null>(null);
  const [color, setColor] = useState<"white" | "black" | "random">(initialColor ?? "white");
  const [filter, setFilter] = useState<Filter>(initialBotId?.startsWith("opening-") ? "opening" : initialBotId?.startsWith("middlegame-") ? "middlegame" : initialBotId?.startsWith("endgame-") ? "endgame" : "classic");
  const [coachMode, setCoachMode] = useState(false);
  const [timeControl, setTimeControl] = useState<string | null>(null);
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
        <div className="row botpicker-filters" role="radiogroup" aria-label="Kind of bot">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" role="radio" aria-checked={filter === f.key} className={`btn btn-sm ${filter === f.key ? "btn-primary" : ""}`} onClick={() => setFilter(f.key)} data-testid={`bot-filter-${f.key}`}>{f.label}</button>
          ))}
        </div>
        {(filter === "classic"
          ? TIERS.map((tier) => ({ key: tier.key, label: tier.label, blurb: tier.blurb, list: bots.filter((b) => b.tier === tier.key) }))
          // specialists: one section per specialty, its four ratings side by side
          : [...new Map(bots.filter((b) => b.specialty?.kind === filter).map((b) => [b.specialty!.key, b])).values()].map((first) => ({
            key: first.specialty!.key, label: first.specialty!.name, blurb: first.tagline, list: bots.filter((b) => b.specialty?.kind === filter && b.specialty.key === first.specialty!.key),
          }))
        ).map((section) => {
          if (!section.list.length) return null;
          return (
            <section key={section.key} className="botpicker-tier">
              <header>
                <h3>{section.label}</h3>
                <span className="faint">{section.blurb}</span>
              </header>
              <div className="botpicker-grid">
                {section.list.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    className={`botcard ${selected?.id === b.id ? "selected" : ""}`}
                    onClick={() => { setSelected(b); if (b.id === "coach") setCoachMode(true); }}
                    data-testid={`bot-${b.id}`}
                  >
                    <span className="botcard-avatar" aria-hidden="true"><BotAvatar id={b.id} tier={b.tier} kind={b.specialty?.kind} size={36} /></span>
                    <span className="botcard-name">{b.specialty ? b.elo : b.name}</span>
                    {!b.specialty && <span className="botcard-elo num">{b.elo}</span>}
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
            <div className="botpicker-body">
              <div className="botpicker-hero">
                <span className="botpicker-hero-avatar" aria-hidden="true"><BotAvatar id={selected.id} tier={selected.tier} size={56} /></span>
                <div>
                  <h2>{selected.name}</h2>
                  <div className="muted">{selected.tagline} · <span className="num">{selected.elo}</span></div>
                </div>
              </div>
              <p className="muted">{selected.description}</p>
              {selected.personality.favourite_openings.length > 0 && (
                <details className="fold">
                  <summary>Openings it plays ({selected.personality.favourite_openings.length})</summary>
                  <div className="row" style={{ flexWrap: "wrap" }}>
                    {selected.personality.favourite_openings.map((o) => <span key={o} className="chip">{o}</span>)}
                  </div>
                </details>
              )}
              <div className="botpicker-colors" role="radiogroup" aria-label="Play as">
                {(["white", "random", "black"] as const).map((c) => (
                  <button key={c} type="button" role="radio" aria-checked={color === c} className={`colorbtn ${c} ${color === c ? "on" : ""}`} onClick={() => setColor(c)} title={`Play as ${c}`}>
                    {c === "random" ? "?" : ""}
                  </button>
                ))}
              </div>
              <div className="row" style={{ flexWrap: "wrap" }} role="radiogroup" aria-label="Time control">
                {TIME_CONTROLS.map((t) => (
                  <button key={t.label} type="button" role="radio" aria-checked={timeControl === t.key} className={`btn btn-sm ${timeControl === t.key ? "btn-primary" : ""}`} onClick={() => setTimeControl(t.key)} data-testid={`tc-${t.key ?? "none"}`}>{t.label}</button>
                ))}
              </div>
            </div>
            <div className="botpicker-foot">
              <label className="row" style={{ cursor: "pointer" }}>
                <input type="checkbox" checked={coachMode} onChange={(e) => setCoachMode(e.target.checked)} />
                <span>Coach mode: move feedback, hints, takebacks and threats</span>
              </label>
              <button type="button" className="btn btn-primary btn-lg botpicker-start" disabled={busy} onClick={() => onStart(selected, color, coachMode, timeControl)} data-testid="start-game">
                {busy ? "Starting…" : `Play ${selected.name}`}
              </button>
            </div>
          </>
        ) : (
          <p className="faint">Loading bots…</p>
        )}
      </aside>
    </div>
  );
}
