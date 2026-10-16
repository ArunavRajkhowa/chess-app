import { Chess } from "chess.js";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Board } from "../components/board/Board";
import { MoveList } from "../components/play/MoveList";
import { checkSquare, destsFor, soundForMove } from "../lib/chess/game";
import { START_FEN, type PromotionPiece, type Square } from "../lib/chess/types";
import { Markdown } from "../lib/markdown";
import { play as playSound } from "../lib/sound";
import "./Games.css";

interface GameSummary { id: string; white: string; black: string; event: string; year: string; result: string; eco: string; opening: string; themes: string[]; why: string; level: number; plies: number }
interface GameDetail extends GameSummary { moves: { ply: number; san: string; uci: string; fen: string; comment: string | null }[]; key_moments: { ply: number; note: string }[]; pgn: string }
interface Theme { key: string; name: string; count: number }

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

export function GamesPage() {
  const { gameId } = useParams();
  if (gameId) return <GameStudy gameId={gameId} />;
  return <GamesIndex />;
}

function GamesIndex() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [themes, setThemes] = useState<Theme[]>([]);
  const [theme, setTheme] = useState<string | null>(null);
  useEffect(() => {
    get<{ games: GameSummary[]; themes: Theme[] }>(`/api/games${theme ? `?theme=${theme}` : ""}`).then((r) => { setGames(r.games); setThemes(r.themes); }).catch(() => undefined);
  }, [theme]);
  return (
    <div className="stack" data-testid="games">
      <div className="page-head"><div><h1>Master games</h1><p>Model games chosen for what they teach, with every key move explained. Replay them or guess the moves.</p></div></div>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <button className={`theme-chip ${theme === null ? "on" : ""}`} onClick={() => setTheme(null)}>All</button>
        {themes.map((t) => <button key={t.key} className={`theme-chip ${theme === t.key ? "on" : ""}`} onClick={() => setTheme(t.key)}>{t.name} <span className="faint num">{t.count}</span></button>)}
      </div>
      <div className="games-grid">
        {games.map((g) => (
          <Link key={g.id} to={`/games/${g.id}`} className="card game-tile" data-testid={`game-${g.id}`}>
            <div className="row" style={{ justifyContent: "space-between" }}><b>{g.white} – {g.black}</b><span className="chip num">{g.result}</span></div>
            <div className="faint">{g.event}{g.event && g.year ? ", " : ""}{g.year} · {g.eco} {g.opening}</div>
            <p className="muted" style={{ fontSize: 13 }}>{g.why}</p>
            <div className="row" style={{ flexWrap: "wrap" }}>{g.themes.map((t) => <span key={t} className="chip">{t}</span>)}<span className="chip chip-info">band {g.level}</span></div>
          </Link>
        ))}
        {games.length === 0 && <p className="faint">No games match.</p>}
      </div>
    </div>
  );
}

function GameStudy({ gameId }: { gameId: string }) {
  const navigate = useNavigate();
  const [game, setGame] = useState<GameDetail | null>(null);
  const [ply, setPly] = useState(0);
  const [mode, setMode] = useState<"replay" | "guess">("replay");
  const [guessColor, setGuessColor] = useState<"w" | "b">("w");
  const [score, setScore] = useState({ points: 0, guesses: 0 });
  const [feedback, setFeedback] = useState<string | null>(null);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  useEffect(() => { get<GameDetail>(`/api/games/${gameId}`).then(setGame).catch(() => navigate("/games")); }, [gameId, navigate]);

  const fen = ply === 0 ? START_FEN : game?.moves[ply - 1]?.fen ?? START_FEN;
  const chess = useMemo(() => new Chess(fen), [fen]);
  const current = ply > 0 ? game?.moves[ply - 1] ?? null : null;
  const total = game?.moves.length ?? 0;
  const guessTurn = mode === "guess" && ply < total && chess.turn() === guessColor;
  const dests = useMemo(() => (guessTurn ? destsFor(chess) : new Map()), [chess, guessTurn]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") setPly((p) => Math.max(0, p - 1));
      else if (e.key === "ArrowRight" && !guessTurn) setPly((p) => Math.min(total, p + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [total, guessTurn]);

  // In guess mode, auto-play the other side's moves.
  useEffect(() => {
    if (mode !== "guess" || !game || ply >= total) return;
    if (chess.turn() !== guessColor) {
      const t = setTimeout(() => setPly((p) => Math.min(total, p + 1)), 600);
      return () => clearTimeout(t);
    }
  }, [mode, ply, chess, guessColor, game, total]);

  const onGuess = async (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (!game) return;
    const c = new Chess(fen);
    const mv = c.move({ from, to, promotion });
    if (!mv) return;
    const res = await fetch("/api/games/guess", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ game_id: game.id, ply: ply + 1, move: from + to + (promotion ?? "") }) });
    const r = await res.json();
    setScore((s) => ({ points: s.points + (r.points ?? 0), guesses: s.guesses + 1 }));
    setFeedback(`${r.your_san}: ${r.verdict === "master" ? "the master's move!" : `${r.note} Game move: ${r.master_san}.`}`);
    playSound(r.points >= 2 ? "correct" : "wrong");
    const master = new Chess(fen);
    const mm = master.move(game.moves[ply].uci);
    if (mm) playSound(soundForMove(mm, master));
    setPly(ply + 1);
  };

  if (!game) return <p className="faint">Loading game…</p>;
  const lastMove: [Square, Square] | null = current ? [current.uci.slice(0, 2), current.uci.slice(2, 4)] : null;
  return (
    <div className="gamestudy" data-testid="gamestudy">
      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <div><h2>{game.white} – {game.black}</h2><div className="faint">{game.event}{game.event && game.year ? ", " : ""}{game.year} · {game.eco} {game.opening} · {game.result}</div></div>
          <button className="btn btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
        </div>
        <Board fen={fen} orientation={orientation} movable={{ color: guessTurn ? guessColor : "none", dests }} lastMove={lastMove} check={checkSquare(chess)} onMove={onGuess} />
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn btn-sm" onClick={() => setPly(0)}>⏮</button>
          <button className="btn btn-sm" onClick={() => setPly(Math.max(0, ply - 1))}>◀</button>
          <button className="btn btn-sm" onClick={() => !guessTurn && setPly(Math.min(total, ply + 1))} disabled={guessTurn}>▶</button>
          <button className="btn btn-sm" onClick={() => setPly(total)} disabled={mode === "guess"}>⏭</button>
          <span className="chip num">{ply}/{total}</span>
        </div>
      </div>
      <aside className="games-side">
        <div className="card stack">
          <div className="row">
            <button className={`btn btn-sm ${mode === "replay" ? "btn-primary" : ""}`} onClick={() => { setMode("replay"); setFeedback(null); }}>Replay</button>
            <button className={`btn btn-sm ${mode === "guess" ? "btn-primary" : ""}`} onClick={() => { setMode("guess"); setPly(0); setScore({ points: 0, guesses: 0 }); setFeedback(null); }} data-testid="guess-mode">Guess the move</button>
            {mode === "guess" && (
              <select className="select" style={{ width: 110 }} value={guessColor} onChange={(e) => { setGuessColor(e.target.value as "w" | "b"); setPly(0); }}>
                <option value="w">as White</option><option value="b">as Black</option>
              </select>
            )}
          </div>
          {mode === "guess" && <div className="row"><span className="chip chip-ok">score {score.points} / {score.guesses * 3}</span>{guessTurn && <span className="chip chip-info">your guess</span>}</div>}
          {feedback && <div className="task-banner" data-testid="guess-feedback">{feedback}</div>}
          <p className="muted">{game.why}</p>
          {current?.comment && <div className="comment" data-testid="comment"><Markdown md={current.comment.replace(/^!+\s*/, "")} /></div>}
        </div>
        <div className="card" style={{ padding: 0 }}>
          <MoveList moves={game.moves.map((m) => ({ ply: m.ply, san: m.san }))} currentPly={ply} onSelect={(p) => !guessTurn && setPly(p)} opening={game.opening} />
        </div>
        {game.key_moments.length > 0 && (
          <div className="card">
            <div className="card-title"><h3>Key moments</h3></div>
            <div className="keymoments">{game.key_moments.map((k) => <button key={k.ply} className={k.ply === ply ? "current" : ""} onClick={() => setPly(k.ply)}>{Math.ceil(k.ply / 2)}{k.ply % 2 ? "." : "…"} {game.moves[k.ply - 1].san}</button>)}</div>
          </div>
        )}
        <Link to="/games" className="muted">← All games</Link>
      </aside>
    </div>
  );
}
