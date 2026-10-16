import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type GameSummary } from "../lib/api";
import "../components/review/Review.css";

export function ReviewPage() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [pgn, setPgn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  useEffect(() => { api.games().then((r) => setGames(r.games)).catch((e: Error) => setError(e.message)); }, []);

  const importPgn = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.importPgn(pgn, "full");
      navigate(`/review/${r.game_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Game review</h1>
          <p>Accuracy, move classifications, key moments and coach explanations for any game.</p>
        </div>
      </div>
      <div className="card">
        <div className="card-title"><h3>Import a PGN</h3><span className="faint">from chess.com, lichess, or a book</span></div>
        <textarea className="input" rows={5} value={pgn} onChange={(e) => setPgn(e.target.value)} placeholder='[White "You"] [Black "Opponent"] 1. e4 e5 2. Nf3 ...' data-testid="pgn-input" />
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn btn-primary" disabled={busy || !pgn.trim()} onClick={importPgn} data-testid="import-btn">{busy ? "Importing…" : "Review this game"}</button>
          {error && <span className="chip chip-danger">{error}</span>}
        </div>
      </div>
      <div className="card">
        <div className="card-title"><h3>Your games</h3><span className="faint">{games.length} games</span></div>
        {games.length === 0 ? <p className="faint">No games yet.</p> : (
          <table className="games-table" data-testid="games-table">
            <thead><tr><th>Opponent</th><th>Opening</th><th>Result</th><th>Moves</th><th /></tr></thead>
            <tbody>
              {games.map((g) => (
                <tr key={g.id}>
                  <td>{g.bot_avatar} {g.bot_name} <span className="faint">({g.player_color})</span></td>
                  <td className="faint">{g.opening_name ?? "—"}</td>
                  <td className="num">{g.status === "active" ? <span className="chip chip-info">in progress</span> : g.result}</td>
                  <td className="num">{Math.ceil(g.plies / 2)}</td>
                  <td>{g.status === "active" ? <Link to={`/play/${g.id}`} className="btn btn-sm">Resume</Link> : <Link to={`/review/${g.id}`} className="btn btn-sm btn-primary">Review</Link>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
