import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type GameSummary } from "../lib/api";

export function HomePage() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [health, setHealth] = useState<{ engine: { name: string; kind: string }; coach: { llm: boolean; model: string } } | null>(null);
  useEffect(() => {
    api.games().then((r) => setGames(r.games.slice(0, 8))).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
  }, []);
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Welcome back</h1>
          <p>Play, review, and learn. Everything runs on your machine.</p>
        </div>
        {health && (
          <div className="row">
            <span className="chip chip-ok">{health.engine.name}</span>
            <span className={`chip ${health.coach.llm ? "chip-ok" : "chip-warn"}`}>{health.coach.llm ? `Coach: ${health.coach.model}` : "Coach: offline mode"}</span>
          </div>
        )}
      </div>
      <div className="home-grid">
        <Link to="/play" className="card home-tile"><span className="home-tile-icon">♞</span><h2>Play a bot</h2><p className="muted">From 250 to 3200. Pick a personality.</p></Link>
        <Link to="/puzzles" className="card home-tile"><span className="home-tile-icon">🧩</span><h2>Puzzles</h2><p className="muted">Rated tactics, themes, Puzzle Rush.</p></Link>
        <Link to="/learn" className="card home-tile"><span className="home-tile-icon">🎓</span><h2>Learn</h2><p className="muted">A structured path from the rules to mastery.</p></Link>
        <Link to="/review" className="card home-tile"><span className="home-tile-icon">📈</span><h2>Game review</h2><p className="muted">Accuracy, key moments, coach explanations.</p></Link>
      </div>
      <section className="card">
        <div className="card-title"><h3>Recent games</h3><Link to="/review" className="muted">All games</Link></div>
        {games.length === 0 ? (
          <p className="faint">No games yet. <Link to="/play" style={{ color: "var(--brand)" }}>Play your first game</Link>.</p>
        ) : (
          <ul className="home-games">
            {games.map((g) => (
              <li key={g.id}>
                <span aria-hidden="true">{g.bot_avatar}</span>
                <Link to={g.status === "active" ? `/play/${g.id}` : `/review/${g.id}`} className="grow"><strong>{g.bot_name}</strong> <span className="faint">{g.opening_name ?? ""}</span></Link>
                <span className={`chip ${g.status === "active" ? "chip-info" : ""}`}>{g.status === "active" ? "in progress" : g.result}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
