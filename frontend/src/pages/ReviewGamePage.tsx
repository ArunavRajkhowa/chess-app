import { Chess } from "chess.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Board } from "../components/board/Board";
import type { Shape } from "../components/board/shapes";
import { EvalBar } from "../components/play/EvalBar";
import { MoveList, CLASS_GLYPH } from "../components/play/MoveList";
import { CoachPanel } from "../components/review/CoachPanel";
import { EvalGraph } from "../components/review/EvalGraph";
import { ReportTable } from "../components/review/ReportTable";
import { api, type GameReport, type ReviewedMove } from "../lib/api";
import { checkSquare, destsFor, soundForMove } from "../lib/chess/game";
import type { PromotionPiece, Square } from "../lib/chess/types";
import { winPercent } from "../lib/engine/uci";
import { gameAccuracy } from "../lib/review/accuracy";
import { classifyDrop } from "../lib/review/classify";
import { play as playSound } from "../lib/sound";
import { useEngine } from "../store/engine";
import { streamCoach } from "../lib/coach";
import "../components/review/Review.css";

const START = new Chess().fen();

export function ReviewGamePage() {
  const { gameId = "" } = useParams();
  const [report, setReport] = useState<GameReport | null>(null);
  const [names, setNames] = useState<{ white: string; black: string; playerColor: "white" | "black" | null }>({ white: "White", black: "Black", playerColor: null });
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ply, setPly] = useState(0);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [showBest, setShowBest] = useState(false);
  const [retry, setRetry] = useState<{ ply: number; status: "waiting" | "correct" | "wrong"; text: string } | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrating, setNarrating] = useState(false);
  const navigate = useNavigate();
  const evaluate = useEngine((s) => s.evaluate);
  const loadEngine = useEngine((s) => s.load);
  const pollRef = useRef<number | null>(null);

  useEffect(() => { void loadEngine(); }, [loadEngine]);

  const load = useCallback(async () => {
    try {
      const r = await api.review(gameId);
      setReport(r.report);
      const g = r.game;
      const white = g.white_name ?? (g.player_color === "white" ? "You" : g.bot_id ?? "Bot");
      const black = g.black_name ?? (g.player_color === "black" ? "You" : g.bot_id ?? "Bot");
      const pc = g.white_name ? null : (g.player_color as "white" | "black");
      setNames({ white, black, playerColor: pc });
      if (pc) setOrientation(pc);
      return true;
    } catch {
      return false;
    }
  }, [gameId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (await load()) return;
      try {
        const job = await api.startReview(gameId, "full");
        setProgress(job.progress);
        const tick = async () => {
          if (cancelled) return;
          const j = await api.reviewJob(job.id);
          setProgress(j.progress);
          if (j.status === "done") { await load(); return; }
          if (j.status === "failed") { setError(j.error ?? "review failed"); return; }
          pollRef.current = window.setTimeout(tick, 600);
        };
        void tick();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; if (pollRef.current) clearTimeout(pollRef.current); };
  }, [gameId, load]);

  const moves = report?.moves ?? [];
  const current: ReviewedMove | null = ply > 0 ? moves[ply - 1] ?? null : null;
  const fen = retry?.status === "waiting" || retry?.status === "wrong" ? moves[retry.ply - 1].fen_before : ply === 0 ? START : moves[ply - 1]?.fen_after ?? START;
  const chess = useMemo(() => new Chess(fen), [fen]);
  const keyMoments = report?.key_moments ?? [];
  const nextKey = keyMoments.find((k) => k > ply) ?? null;

  useEffect(() => { setShowBest(false); setExplanation(null); if (retry && retry.ply !== ply) setRetry(null); }, [ply]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!report) return;
      if (e.key === "ArrowLeft") setPly((p) => Math.max(0, p - 1));
      else if (e.key === "ArrowRight") setPly((p) => Math.min(moves.length, p + 1));
      else if (e.key === "ArrowUp") setPly(0);
      else if (e.key === "ArrowDown") setPly(moves.length);
      else if (e.key === "f") setOrientation((o) => (o === "white" ? "black" : "white"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [report, moves.length]);

  const onRetryMove = async (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (!retry || !current) return;
    const c = new Chess(fen);
    const mv = c.move({ from, to, promotion });
    if (!mv) return;
    playSound(soundForMove(mv, c));
    const uci = from + to + (promotion ?? "");
    if (uci === current.best_move_uci) {
      const accs = moves.filter((m) => m.color === current.color).map((m) => (m.ply === current.ply ? 100 : m.accuracy));
      const graph = current.color === "white" ? report!.eval_graph : report!.eval_graph.map((w) => 100 - w);
      const would = gameAccuracy(graph, accs);
      playSound("correct");
      setRetry({ ply: current.ply, status: "correct", text: `Correct! ${mv.san} was the best move. Your accuracy would have been ${would}%.` });
      return;
    }
    const r = await evaluate(c.fen(), { movetimeMs: 600 });
    const line = r?.lines[0];
    const wa = line ? (current.color === "white" ? winPercent(line) : 100 - winPercent(line)) : current.win_after;
    const cls = classifyDrop(current.win_before, wa, false);
    playSound("wrong");
    setRetry({ ply: current.ply, status: "wrong", text: `${mv.san} is ${cls === "best" ? "fine" : cls === "excellent" || cls === "good" ? "reasonable, but not the best" : "not it: still " + cls}. Try again, or press Show best.` });
  };

  const explain = async () => {
    if (!current) return;
    setExplaining(true);
    setExplanation("");
    try {
      await streamCoach("/api/coach/explain", { game_id: gameId, ply: current.ply }, (chunk) => setExplanation((t) => (t ?? "") + chunk));
    } catch (e) {
      setExplanation(`Coach unavailable: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExplaining(false);
    }
  };

  const practiceFromHere = async () => {
    const side = chess.turn() === "w" ? "white" : "black";
    try {
      const g = await api.newGame("coach", side, true, null, fen);
      navigate(`/play/${g.id}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };
  const tellStory = async () => {
    setNarrating(true);
    setNarrative("");
    try {
      await streamCoach("/api/coach/summary", { game_id: gameId }, (chunk) => setNarrative((t) => (t ?? "") + chunk));
    } catch (e) {
      setNarrative(`Coach unavailable: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setNarrating(false);
    }
  };

  if (error) return <div className="chip chip-danger">{error}</div>;
  if (!report) {
    return (
      <div className="review-progress" data-testid="review-progress">
        <h2>Reviewing your game…</h2>
        <p className="muted">Every position is analysed by Stockfish. {progress ? `${progress.done} of ${progress.total} positions` : "Starting"}</p>
        <div className="progress"><i style={{ width: `${progress && progress.total ? (100 * progress.done) / progress.total : 3}%` }} /></div>
      </div>
    );
  }

  const shapes: Shape[] = [];
  if (showBest && current) shapes.push({ orig: current.best_move_uci.slice(0, 2), dest: current.best_move_uci.slice(2, 4), brush: "green" });
  if (retry?.status === "wrong" && current) shapes.push({ orig: current.best_move_uci.slice(0, 2), brush: "yellow" });
  const lastMove: [Square, Square] | null = current && !retry ? [current.uci.slice(0, 2), current.uci.slice(2, 4)] : null;
  const markers = current && !retry && current.classification !== "book" && current.classification !== "good" && current.classification !== "excellent"
    ? [{ square: current.uci.slice(2, 4), text: CLASS_GLYPH[current.classification], className: `cls-${current.classification}` }]
    : [];
  const evalCp = ply === 0 ? 20 : current?.eval_after_cp ?? 0;
  const isMate = Math.abs(evalCp) >= 9000;
  const resultLine = report.result ? `${report.result} · ` : "";
  const opening = report.opening ? `${report.opening.eco} ${report.opening.name}` : "Unknown opening";
  const summary = `${resultLine}${opening}. White ${report.white.accuracy}% · Black ${report.black.accuracy}%. ${keyMoments.length} key moments.`;
  const canRetry = !!current && ["inaccuracy", "mistake", "blunder", "miss"].includes(current.classification) && (!names.playerColor || current.color === names.playerColor);

  return (
    <div className="review" data-testid="review">
      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
          <strong>{orientation === "white" ? names.black : names.white}</strong>
          <span className="faint">{report.result ?? "*"}</span>
        </div>
        <div className="gameview-board-row">
          <EvalBar cp={isMate ? undefined : evalCp} mate={isMate ? (evalCp > 0 ? 1 : -1) : undefined} orientation={orientation} />
          <Board
            fen={fen}
            orientation={orientation}
            movable={retry && retry.status !== "correct" ? { color: chess.turn(), dests: destsFor(chess) } : { color: "none", dests: new Map() }}
            lastMove={lastMove}
            check={checkSquare(chess)}
            shapes={shapes}
            markers={markers}
            onMove={onRetryMove}
          />
        </div>
        <div className="row" style={{ justifyContent: "space-between", marginTop: 6 }}>
          <strong>{orientation === "white" ? names.white : names.black}</strong>
          <button className="btn btn-ghost btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
        </div>
        <EvalGraph graph={report.eval_graph} moves={moves} currentPly={ply} onSelect={setPly} />
        {retry && <div className={`retry-banner ${retry.status === "wrong" ? "wrong" : ""}`} data-testid="retry-banner" style={{ marginTop: 8 }}>{retry.status === "waiting" ? "Your move: find something better." : retry.text}</div>}
      </div>

      <aside className="review-side">
        <div className="card">
          <div className="review-summary">
            <div><div className="review-acc white num" data-testid="acc-white">{report.white.accuracy}</div><div className="review-rating">{names.white} · est. {report.white.estimated_rating}</div></div>
            <div className="faint">accuracy</div>
            <div><div className="review-acc black num" data-testid="acc-black">{report.black.accuracy}</div><div className="review-rating">{names.black} · est. {report.black.estimated_rating}</div></div>
          </div>
          <div className="faint" style={{ textAlign: "center", marginTop: 6 }}>{opening} · depth {report.depth}</div>
          <div className="row" style={{ justifyContent: "center", marginTop: 10 }}>
            <button className="btn btn-sm" onClick={tellStory} disabled={narrating} data-testid="summary-btn">{narrating ? "Writing…" : "Coach summary"}</button>
            <button className="btn btn-sm" onClick={practiceFromHere} data-testid="practice-btn">Practice from here</button>
          </div>
          {narrative && <p className="coach-explanation" data-testid="narrative" style={{ marginTop: 10 }}>{narrative}</p>}
        </div>
        <div className="card">
          <CoachPanel
            move={current}
            summary={summary}
            explanation={explanation}
            explaining={explaining}
            onExplain={explain}
            onRetry={() => current && setRetry({ ply: current.ply, status: "waiting", text: "" })}
            onShowBest={() => setShowBest((s) => !s)}
            onNext={() => nextKey !== null && setPly(nextKey)}
            canRetry={canRetry}
            hasNext={nextKey !== null}
          />
          {keyMoments.length > 0 && (
            <div className="keymoments" style={{ marginTop: 10 }}>
              {keyMoments.map((k) => {
                const m = moves[k - 1];
                return <button key={k} className={k === ply ? "current" : ""} onClick={() => setPly(k)} title={m.classification}>{m.move_number}{m.color === "white" ? "." : "…"} {m.san} <i className={`cls-badge cls-${m.classification}`}>{CLASS_GLYPH[m.classification]}</i></button>;
              })}
            </div>
          )}
        </div>
        <div className="card">
          <ReportTable white={report.white} black={report.black} whiteName={names.white} blackName={names.black} />
          <div className="phase-grades" style={{ marginTop: 10 }}>
            {(["opening", "middlegame", "endgame"] as const).map((p) => (
              <div key={p}><div className="faint">{p}</div><div className="num"><b>{report.white.phase_accuracy[p] ?? "–"}</b> / <b>{report.black.phase_accuracy[p] ?? "–"}</b></div></div>
            ))}
          </div>
        </div>
        <div className="card" style={{ padding: 0 }}>
          <MoveList moves={moves.map((m) => ({ ply: m.ply, san: m.san, classification: m.classification }))} currentPly={ply} onSelect={setPly} opening={null} />
        </div>
        <Link to="/review" className="muted">← All games</Link>
      </aside>
    </div>
  );
}
