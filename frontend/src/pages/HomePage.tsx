import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Board } from "../components/board/Board";
import { api, type GameSummary } from "../lib/api";
import { puzzleApi, type Puzzle } from "../lib/puzzleApi";

export function HomePage() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [health, setHealth] = useState<{ engine: { name: string; kind: string }; coach: { llm: boolean; model: string } } | null>(null);
  const [daily, setDaily] = useState<{ date: string; puzzle: Puzzle; solved_today: boolean; streak: number } | null>(null);
  const [awards, setAwards] = useState<{ awards: { key: string; name: string; how: string; earned: boolean }[]; earned: number; total: number } | null>(null);
  useEffect(() => {
    api.games().then((r) => setGames(r.games.slice(0, 8))).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
    puzzleApi.daily().then(setDaily).catch(() => undefined);
    fetch("/api/awards").then((r) => r.json()).then(setAwards).catch(() => undefined);
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
      <div className="home-two">
        {daily && (
          <section className="card home-daily" data-testid="daily-card">
            <div className="card-title"><h3>Daily puzzle</h3><span className="faint">{daily.date} · rating {daily.puzzle.rating}{daily.streak > 0 ? ` · 🔥 ${daily.streak} day streak` : ""}</span></div>
            <div className="home-daily-body">
              <div style={{ width: 220 }}><Board fen={daily.puzzle.fen} orientation={daily.puzzle.solver_color} showCoordinates={false} /></div>
              <div className="col">
                <p className="muted">{daily.puzzle.solver_color === "white" ? "White" : "Black"} to play after the opponent's move. One puzzle a day, five hearts.</p>
                {daily.solved_today ? <span className="chip chip-ok">Solved today</span> : <Link to="/puzzles?daily=1" className="btn btn-primary" style={{ width: "fit-content" }}>Solve today's puzzle</Link>}
              </div>
            </div>
          </section>
        )}
      <section className="card grow">
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
      {awards && (
        <section className="card" data-testid="awards">
          <div className="card-title"><h3>Awards</h3><span className="faint">{awards.earned} of {awards.total}</span></div>
          <div className="awards-grid">
            {awards.awards.map((a) => (
              <div key={a.key} className={`award ${a.earned ? "earned" : ""}`} title={a.how}>
                <span className="award-icon" aria-hidden="true">{a.earned ? "🏅" : "○"}</span>
                <span><b>{a.name}</b><div className="faint">{a.how}</div></span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
