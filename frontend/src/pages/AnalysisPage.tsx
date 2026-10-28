import { Chess } from "chess.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Board } from "../components/board/Board";
import type { Shape } from "../components/board/shapes";
import { EvalBar } from "../components/play/EvalBar";
import { MoveList } from "../components/play/MoveList";
import { Assessment } from "../components/study/Assessment";
import { api } from "../lib/api";
import { checkSquare, destsFor, safeMove, soundForMove } from "../lib/chess/game";
import { START_FEN, type PromotionPiece, type Square } from "../lib/chess/types";
import { lineScoreText, type EngineLine } from "../lib/engine/uci";
import { play as playSound } from "../lib/sound";
import { useEngine } from "../store/engine";
import "./Analysis.css";

const DEPTH = 20;
const LINES = 3;
// Heights (px) the room under a width-limited board must have to take the engine card, else the paste box.
const ENGINE_UNDER_MIN = 260;
const LOAD_UNDER_MIN = 100;

function sanLine(fen: string, pv: string[]): string[] {
  const c = new Chess(fen);
  const out: string[] = [];
  for (const uci of pv.slice(0, 8)) {
    const mv = safeMove(c, { from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    if (!mv) break;
    out.push(mv.san);
  }
  return out;
}

/** Free analysis: play either side, three engine lines, eval bar, load a FEN or PGN, send a game to review. */
export function AnalysisPage() {
  const navigate = useNavigate();
  const [chess] = useState(() => new Chess());
  const [fen, setFen] = useState(START_FEN);
  const [startFen, setStartFen] = useState(START_FEN); // a loaded FEN, or the PGN's FEN header
  const [history, setHistory] = useState<{ san: string; fen: string }[]>([]);
  const [viewPly, setViewPly] = useState(0);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [lines, setLines] = useState<EngineLine[]>([]);
  const [engineOn, setEngineOn] = useState(true);
  const [input, setInput] = useState("");
  const [showArrow, setShowArrow] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const evaluate = useEngine((s) => s.evaluate);
  const status = useEngine((s) => s.status);
  const loadEngine = useEngine((s) => s.load);
  const evalFen = useRef("");
  const slotRef = useRef<HTMLDivElement>(null);
  const [under, setUnder] = useState<"engine" | "load" | null>(null);

  useEffect(() => { void loadEngine(); }, [loadEngine]);

  // a width-limited board leaves room under it: the engine card fills it, or the paste box when the room is smaller
  useEffect(() => {
    const el = slotRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const h = e.contentRect.height;
      setUnder(h >= ENGINE_UNDER_MIN ? "engine" : h >= LOAD_UNDER_MIN ? "load" : null);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const sync = useCallback(() => {
    const f = chess.fen();
    setFen(f);
    const verbose = chess.history({ verbose: true });
    setStartFen(verbose[0]?.before ?? f);
    const h = verbose.map((m) => ({ san: m.san, fen: m.after }));
    setHistory(h);
    setViewPly(h.length);
  }, [chess]);

  const boardChess = useMemo(() => new Chess(fen), [fen]);
  const over = boardChess.isGameOver();
  const result = boardChess.isCheckmate() ? (boardChess.turn() === "w" ? "0-1" : "1-0") : over ? "1/2-1/2" : undefined;

  useEffect(() => {
    if (!engineOn || over) return; // a finished game has nothing to search
    let cancelled = false;
    evalFen.current = fen;
    setLines([]);
    evaluate(fen, { depth: DEPTH, multipv: LINES, onUpdate: (ls) => { if (!cancelled && evalFen.current === fen) setLines(ls); } })
      .then((r) => { if (!cancelled && r && evalFen.current === fen) setLines(r.lines); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [fen, engineOn, evaluate, over]);

  const live = viewPly === history.length;
  const dests = useMemo(() => (live ? destsFor(boardChess) : new Map()), [boardChess, live]);
  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (!live) return;
    const mv = safeMove(chess, { from, to, promotion });
    if (!mv) return;
    playSound(soundForMove(mv, chess));
    sync();
  };
  const playUci = (uci: string) => {
    if (!live) return;
    const mv = safeMove(chess, { from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    if (mv) { playSound(soundForMove(mv, chess)); sync(); }
  };
  const goTo = (ply: number) => { setViewPly(ply); setFen(ply <= 0 ? startFen : history[ply - 1].fen); };
  const load = () => {
    const text = input.trim();
    if (!text) return;
    try {
      if (/^[rnbqkpRNBQKP1-8]+\/.*\s[wb]\s/.test(text)) { chess.load(text); } else { chess.loadPgn(text); }
      sync();
      setInput("");
    } catch {
      alert("Could not read that as a FEN or PGN.");
    }
  };
  const review = async () => {
    const pgn = chess.pgn();
    if (!history.length) return;
    setError(null);
    try {
      const r = await api.importPgn(pgn, "full");
      navigate(`/review/${r.game_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") goTo(Math.max(0, viewPly - 1));
      else if (e.key === "ArrowRight") goTo(Math.min(history.length, viewPly + 1));
      else if (e.key === "f") setOrientation((o) => (o === "white" ? "black" : "white"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const top = evalFen.current === fen ? lines[0] : undefined;
  const shownLines = evalFen.current === fen ? lines : [];
  const shapes: Shape[] = showArrow && top?.pv[0] ? [{ orig: top.pv[0].slice(0, 2), dest: top.pv[0].slice(2, 4), brush: "green" }] : [];
  const cur = viewPly > 0 ? history[viewPly - 1] : null;

  const engineCard = (
    <div className="card">
      <div className="card-title">
        <h3>Engine</h3>
        <div className="row">
          <label className="faint row"><input type="checkbox" checked={engineOn} onChange={(e) => setEngineOn(e.target.checked)} /> on</label>
          <label className="faint row"><input type="checkbox" checked={showArrow} onChange={(e) => setShowArrow(e.target.checked)} /> arrow</label>
          <span className="chip">{status === "ready" ? `depth ${lines[0]?.depth ?? 0}` : status}</span>
        </div>
      </div>
      <ul className="engine-lines" data-testid="engine-lines">
        {shownLines.map((l) => (
          <li key={l.multipv}>
            <button onClick={() => playUci(l.pv[0])} disabled={!live}>
              <b className={`num eval ${(l.cp ?? (l.mate ?? 0) * 1000) >= 0 ? "white" : "black"}`}>{lineScoreText(l)}</b>
              <span>{sanLine(fen, l.pv).join(" ")}</span>
            </button>
          </li>
        ))}
        {!shownLines.length && <li className="faint" data-testid="engine-status">{result ? `${boardChess.isCheckmate() ? "Checkmate" : "Draw"} · ${result}` : engineOn ? "thinking…" : "engine off"}</li>}
      </ul>
      <details className="fold analysis-fold">
        <summary>Assessment: imbalances and plans</summary>
        <Assessment fen={fen} />
      </details>
    </div>
  );
  const loadCard = (
    <div className="card analysis-load">
      <textarea className="input" rows={2} placeholder="Paste a FEN or a PGN" value={input} onChange={(e) => setInput(e.target.value)} data-testid="analysis-input" />
      <button className="btn btn-sm" onClick={load} data-testid="analysis-load">Load</button>
    </div>
  );

  return (
    <div className="board-page analysis" data-testid="analysis">
      <div className="board-col">
        <div className="row analysis-head">
          <h2>Analysis</h2>
          <div className="row">
            <button className="btn btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
            <button className="btn btn-sm" onClick={() => { chess.undo(); sync(); }} disabled={!history.length}>Undo</button>
            <button className="btn btn-sm" onClick={() => { chess.reset(); sync(); }}>Reset</button>
          </div>
        </div>
        <div className="gameview-board-row">
          <EvalBar cp={top?.cp} mate={top?.mate} result={result} orientation={orientation} loading={status !== "ready"} />
          <Board fen={fen} orientation={orientation} movable={{ color: live ? "both" : "none", dests }} lastMove={cur ? null : null} check={checkSquare(boardChess)} shapes={shapes} onMove={onMove} />
        </div>
        <div className="analysis-slot" ref={slotRef}>{under === "engine" ? engineCard : under === "load" ? loadCard : null}</div>
      </div>
      <aside className="side-col analysis-side">
        {under !== "engine" && engineCard}
        <div className="card analysis-moves">
          <MoveList moves={history.map((m, i) => ({ ply: i + 1, san: m.san }))} currentPly={viewPly} onSelect={goTo} opening={null} />
          <div className="row analysis-actions">
            <button className="btn btn-sm btn-primary" onClick={review} disabled={!history.length} data-testid="analysis-review">Review this game</button>
            <button className="btn btn-sm" onClick={() => navigator.clipboard?.writeText(fen)}>Copy FEN</button>
          </div>
          {error && <span className="chip chip-danger" data-testid="analysis-error">{error}</span>}
        </div>
        {under !== "load" && loadCard}
      </aside>
    </div>
  );
}
