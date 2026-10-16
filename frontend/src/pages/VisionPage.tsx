import { useEffect, useRef, useState } from "react";
import { Board } from "../components/board/Board";
import { FILES, RANKS } from "../lib/chess/types";
import { play as playSound } from "../lib/sound";
import "./Vision.css";

type Mode = "find" | "name";
const ROUND_SECONDS = 30;
const EMPTY = "8/8/8/8/8/8/8/8 w - - 0 1";

function randomSquare(): string {
  return FILES[Math.floor(Math.random() * 8)] + RANKS[Math.floor(Math.random() * 8)];
}

/** Board vision: find the named square, or name the highlighted one. Thirty seconds a round. */
export function VisionPage() {
  const [mode, setMode] = useState<Mode>("find");
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [randomFlip, setRandomFlip] = useState(false);
  const [target, setTarget] = useState<string>(randomSquare());
  const [options, setOptions] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [left, setLeft] = useState(ROUND_SECONDS);
  const [score, setScore] = useState(0);
  const [misses, setMisses] = useState(0);
  const [flash, setFlash] = useState<{ square: string; brush: "green" | "red" } | null>(null);
  const [best, setBest] = useState<{ find: number; name: number }>({ find: 0, name: 0 });
  const [result, setResult] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => { fetch("/api/vision").then((r) => r.json()).then((r) => setBest(r.best)).catch(() => undefined); }, []);

  const nextTarget = () => {
    const sq = randomSquare();
    setTarget(sq);
    if (randomFlip) setOrientation(Math.random() < 0.5 ? "white" : "black");
    const opts = new Set([sq]);
    while (opts.size < 4) opts.add(randomSquare());
    setOptions([...opts].sort(() => Math.random() - 0.5));
  };

  const start = () => {
    setScore(0); setMisses(0); setLeft(ROUND_SECONDS); setResult(null); setRunning(true);
    nextTarget();
    if (timer.current) clearInterval(timer.current);
    timer.current = window.setInterval(() => setLeft((l) => l - 1), 1000);
  };

  useEffect(() => {
    if (!running || left > 0) return;
    if (timer.current) clearInterval(timer.current);
    setRunning(false);
    playSound(score > 0 ? "win" : "lose");
    fetch("/api/vision/score", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, score, seconds: ROUND_SECONDS }) })
      .then((r) => r.json()).then((r) => { setBest(r.best); setResult(r.new_best ? `New best: ${score}!` : `Score ${score}. Best ${r.best[mode]}.`); })
      .catch(() => setResult(`Score ${score}.`));
  }, [left, running, mode, score]);

  const answer = (sq: string) => {
    if (!running) return;
    const ok = sq === target;
    setFlash({ square: ok ? sq : target, brush: ok ? "green" : "red" });
    setTimeout(() => setFlash(null), 350);
    if (ok) { setScore((s) => s + 1); playSound("correct"); } else { setMisses((m) => m + 1); playSound("wrong"); }
    nextTarget();
  };

  return (
    <div className="vision" data-testid="vision">
      <div>
        <div className="page-head"><div><h1>Board vision</h1><p>Know every square by name without looking at the coordinates. Thirty seconds a round.</p></div></div>
        <div className="row" style={{ marginBottom: 10, flexWrap: "wrap" }}>
          <button className={`btn btn-sm ${mode === "find" ? "btn-primary" : ""}`} onClick={() => { setMode("find"); setRunning(false); }} data-testid="vision-find">Find the square</button>
          <button className={`btn btn-sm ${mode === "name" ? "btn-primary" : ""}`} onClick={() => { setMode("name"); setRunning(false); }} data-testid="vision-name">Name the square</button>
          <label className="row faint"><input type="checkbox" checked={randomFlip} onChange={(e) => setRandomFlip(e.target.checked)} /> random orientation</label>
          <button className="btn btn-sm btn-ghost" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
        </div>
        <div className="vision-board" onClickCapture={mode === "find" && running ? (e) => { const el = (e.target as HTMLElement).closest("[data-square]"); if (el) { e.stopPropagation(); answer(el.getAttribute("data-square")!); } } : undefined}>
          <Board
            fen={EMPTY}
            orientation={orientation}
            showCoordinates={false}
            highlights={[...(mode === "name" && running ? [{ square: target, brush: "yellow" as const }] : []), ...(flash ? [flash] : [])]}
          />
        </div>
      </div>
      <aside className="card vision-side">
        {running ? (
          <>
            <div className="vision-target" data-testid="vision-target">{mode === "find" ? target : "Which square is highlighted?"}</div>
            <div className="row"><span className="chip chip-ok">score {score}</span><span className="chip chip-danger">misses {misses}</span><span className="chip num">{left}s</span></div>
            {mode === "name" && (
              <div className="vision-options">{options.map((o) => <button key={o} className="btn" onClick={() => answer(o)} data-testid={`opt-${o}`}>{o}</button>)}</div>
            )}
          </>
        ) : (
          <>
            <p className="muted">{mode === "find" ? "A square name appears; click it on the board." : "A square lights up; pick its name."} {result && <b>{result}</b>}</p>
            <div className="row"><span className="chip">best find: {best.find}</span><span className="chip">best name: {best.name}</span></div>
            <button className="btn btn-primary btn-lg" onClick={start} data-testid="vision-start">Start</button>
          </>
        )}
      </aside>
    </div>
  );
}
