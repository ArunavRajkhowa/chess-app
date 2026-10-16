import { Timer, Trophy } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { DrillBoard, type DrillGoal, type DrillOutcome } from "../components/learn/DrillBoard";
import "./Endgames.css";

interface Theme { key: string; name: string; blurb: string }
interface Position { key: string; theme: string; title: string; fen: string; goal: DrillGoal; max_moves?: number; level: number; tip: string; learner_color: "white" | "black"; best: { solved: number; tried: number; best_moves: number | null; best_seconds: number | null } | null }

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

const GOAL_TEXT: Record<DrillGoal, string> = { mate: "Checkmate", promote: "Promote a pawn", draw: "Hold the draw", survive: "Survive", win_material: "Win material" };

export function EndgamesPage() {
  const [themes, setThemes] = useState<Theme[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [theme, setTheme] = useState("checkmates");
  const [current, setCurrent] = useState<Position | null>(null);
  const [resetToken, setResetToken] = useState(0);
  const [challenge, setChallenge] = useState<{ list: Position[]; i: number; solved: number; startedAt: number; done: boolean } | null>(null);
  const [now, setNow] = useState(Date.now());
  const startedAt = useRef(Date.now());

  const reload = () => get<{ themes: Theme[]; positions: Position[] }>("/api/endgames").then((r) => { setThemes(r.themes); setPositions(r.positions); }).catch(() => undefined);
  useEffect(() => { void reload(); }, []);
  useEffect(() => {
    if (!challenge || challenge.done) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [challenge]);

  const list = useMemo(() => positions.filter((p) => p.theme === theme), [positions, theme]);

  const start = (p: Position) => { setCurrent(p); setResetToken((t) => t + 1); startedAt.current = Date.now(); };
  const startChallenge = async () => {
    const r = await get<{ positions: Position[] }>(`/api/endgames/challenge?theme=${theme}`);
    setChallenge({ list: r.positions, i: 0, solved: 0, startedAt: Date.now(), done: false });
    start(r.positions[0]);
  };
  const onOutcome = async (o: DrillOutcome, _moves: number, line: string[]) => {
    if (!current) return;
    const seconds = (Date.now() - startedAt.current) / 1000;
    // the server replays the line and records its own verdict
    await fetch("/api/endgames/attempt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: current.key, line, seconds, mode: challenge ? "challenge" : "practice" }) }).catch(() => undefined);
    void reload();
    if (challenge) {
      const solved = challenge.solved + (o.result === "success" ? 1 : 0);
      const i = challenge.i + 1;
      if (i >= challenge.list.length) { setChallenge({ ...challenge, solved, i, done: true }); return; }
      setChallenge({ ...challenge, solved, i });
      setTimeout(() => start(challenge.list[i]), 900);
    }
  };
  const elapsed = challenge ? Math.floor(((challenge.done ? now : now) - challenge.startedAt) / 1000) : 0;

  return (
    <div className="endgames" data-testid="endgames">
      <div>
        <div className="page-head"><div><h1>Endgames</h1><p>Theory you must know, played out against the engine until it is yours.</p></div></div>
        <div className="row" style={{ flexWrap: "wrap", marginBottom: 12 }}>
          {themes.map((t) => <button key={t.key} className={`btn btn-sm ${theme === t.key ? "btn-primary" : ""}`} onClick={() => { setTheme(t.key); setChallenge(null); }} data-testid={`eg-theme-${t.key}`}>{t.name}</button>)}
          <button className="btn btn-sm" onClick={startChallenge} data-testid="eg-challenge"><Timer size={14} /> Timed challenge (5 in a row)</button>
        </div>
        {challenge && (
          <div className="card row" style={{ marginBottom: 12 }} data-testid="eg-challenge-bar">
            <span className="chip chip-info">position {Math.min(challenge.i + 1, challenge.list.length)} / {challenge.list.length}</span>
            <span className="chip chip-ok">solved {challenge.solved}</span>
            <span className="chip num">{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span>
            {challenge.done && <span className="chip"><Trophy size={12} /> finished: {challenge.solved}/{challenge.list.length}</span>}
          </div>
        )}
        {current ? (
          <div className="stack">
            <div className="card">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div><strong data-testid="eg-title">{current.title}</strong> <span className="chip">{GOAL_TEXT[current.goal]}</span> {current.max_moves && <span className="faint">within {current.max_moves} moves</span>}</div>
                <button className="btn btn-sm" onClick={() => setResetToken((t) => t + 1)}>Restart</button>
              </div>
              <p className="muted" style={{ marginTop: 6 }}>{current.tip}</p>
            </div>
            <DrillBoard key={current.key} fen={current.fen} goal={current.goal} maxMoves={current.max_moves} orientation={current.learner_color} onOutcome={onOutcome} resetToken={resetToken} />
          </div>
        ) : (
          <div className="card"><p className="faint">Pick a position on the right, or start a timed challenge.</p></div>
        )}
      </div>
      <aside className="endgames-side">
        <div className="card">
          <div className="card-title"><h3>{themes.find((t) => t.key === theme)?.name}</h3><span className="faint">{themes.find((t) => t.key === theme)?.blurb}</span></div>
          <ul className="eg-list">
            {list.map((p) => (
              <li key={p.key}>
                <button className={`eg-row ${current?.key === p.key ? "current" : ""}`} onClick={() => { setChallenge(null); start(p); }} data-testid={`eg-${p.key}`}>
                  <span className="grow"><b>{p.title}</b><div className="faint">{GOAL_TEXT[p.goal]} · level {p.level}</div></span>
                  {p.best?.solved ? <span className="chip chip-ok">{p.best.solved}/{p.best.tried}{p.best.best_moves ? ` · ${p.best.best_moves} moves` : ""}</span> : <span className="chip">{p.best?.tried ? `0/${p.best.tried}` : "new"}</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
