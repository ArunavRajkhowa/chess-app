import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Classification } from "../lib/api";
import { CLASS_GLYPH } from "../components/play/MoveList";
import "./Insights.css";

interface Insights {
  games: number;
  message?: string;
  accuracy?: { mean: number; best: number; worst: number; timeline: { at: string; accuracy: number; game_id: string }[] };
  results?: Record<string, number>;
  endings?: Record<string, number>;
  phase_accuracy?: Record<string, number>;
  phase_games_ended?: Record<string, number>;
  move_quality?: Record<Classification, { count: number; per_game: number; share: number }>;
  openings?: { name: string; eco: string | null; games: number; wins: number; draws: number; losses: number; accuracy: number }[];
  shapes?: Record<string, { count: number; description: string }>;
  worst_moves?: { game_id: string; ply: number; san: string; best: string; drop: number; phase: string; classification: string }[];
  work_on?: { area: string; why: string; action: string }[];
}

export function InsightsPage() {
  const [data, setData] = useState<Insights | null>(null);
  useEffect(() => { fetch("/api/insights/me").then((r) => r.json()).then(setData).catch(() => undefined); }, []);
  if (!data) return <p className="faint">Loading…</p>;
  if (!data.games) return <div className="stack"><div className="page-head"><div><h1>Insights</h1><p>{data.message}</p></div></div><Link to="/play" className="btn btn-primary" style={{ width: "fit-content" }}>Play a game</Link></div>;
  const acc = data.accuracy!;
  const w = 600, h = 120;
  const pts = acc.timeline.map((t, i) => `${(i / Math.max(1, acc.timeline.length - 1)) * w},${h - (t.accuracy / 100) * h}`).join(" ");
  const order: Classification[] = ["brilliant", "great", "best", "excellent", "good", "book", "inaccuracy", "mistake", "miss", "blunder"];
  return (
    <div className="stack" data-testid="insights">
      <div className="page-head"><div><h1>Insights</h1><p>{data.games} reviewed games against bots. Patterns, not single games.</p></div></div>
      {data.work_on && data.work_on.length > 0 && (
        <div className="card">
          <div className="card-title"><h3>What to work on</h3></div>
          <ul className="workon">{data.work_on.map((w) => <li key={w.area}><b>{w.area}</b> — {w.why} <span className="muted">{w.action}</span></li>)}</ul>
        </div>
      )}
      <div className="insights-grid">
        <div className="card">
          <div className="card-title"><h3>Accuracy</h3><span className="faint">mean {acc.mean} · best {acc.best} · worst {acc.worst}</span></div>
          <svg viewBox={`0 0 ${w} ${h}`} className="spark" preserveAspectRatio="none"><polyline points={pts} fill="none" stroke="var(--brand)" strokeWidth={2} /></svg>
          <div className="phase-grades" style={{ marginTop: 10 }}>
            {(["opening", "middlegame", "endgame"] as const).map((p) => <div key={p}><div className="faint">{p}</div><b className="num">{data.phase_accuracy?.[p] ?? "–"}</b></div>)}
          </div>
        </div>
        <div className="card">
          <div className="card-title"><h3>Results</h3></div>
          <div className="results-row">
            {(["win", "draw", "loss"] as const).map((k) => <div key={k} className={`result ${k}`}><b className="num">{data.results?.[k] ?? 0}</b><span>{k}</span></div>)}
          </div>
          <ul className="endings">{Object.entries(data.endings ?? {}).map(([k, v]) => <li key={k}><span className="num">{v}</span> {k.replace(":", " by ")}</li>)}</ul>
        </div>
        <div className="card">
          <div className="card-title"><h3>Move quality</h3><span className="faint">per game</span></div>
          <table className="report">
            <tbody>
              {order.map((c) => <tr key={c} className={data.move_quality![c].count === 0 ? "zero" : ""}><td><i className={`cls-badge cls-${c}`}>{CLASS_GLYPH[c]}</i> {c}</td><td className="num">{data.move_quality![c].per_game}</td><td className="num faint">{data.move_quality![c].share}%</td></tr>)}
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="card-title"><h3>Game shapes</h3></div>
          <ul className="shapes">{Object.entries(data.shapes ?? {}).map(([k, v]) => <li key={k}><b>{k}</b> <span className="num">×{v.count}</span><div className="faint">{v.description}</div></li>)}</ul>
        </div>
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <div className="card-title"><h3>Openings</h3></div>
          <table className="games-table">
            <thead><tr><th>Opening</th><th>Games</th><th>W / D / L</th><th>Accuracy</th></tr></thead>
            <tbody>{data.openings?.map((o) => <tr key={o.name}><td>{o.eco ? <span className="chip">{o.eco}</span> : null} {o.name}</td><td className="num">{o.games}</td><td className="num">{o.wins} / {o.draws} / {o.losses}</td><td className="num">{o.accuracy}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <div className="card-title"><h3>Your worst moves</h3><span className="faint">retry them in Game Review</span></div>
          <ul className="worst">{data.worst_moves?.map((m) => <li key={`${m.game_id}-${m.ply}`}><Link to={`/review/${m.game_id}`}><i className={`cls-badge cls-${m.classification}`}>{CLASS_GLYPH[m.classification as Classification]}</i> {m.san} <span className="faint">instead of {m.best} · −{m.drop}% · {m.phase}</span></Link></li>)}</ul>
        </div>
      </div>
    </div>
  );
}
