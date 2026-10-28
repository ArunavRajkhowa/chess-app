import { Chess } from "chess.js";
import { Flame, Lightbulb, RotateCcw, Timer, Trophy } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Board } from "../components/board/Board";
import { ExplorePanel, useExplore } from "../components/explore/Explore";
import type { Shape } from "../components/board/shapes";
import { checkSquare, destsFor, safeMove, soundForMove } from "../lib/chess/game";
import { START_FEN, type PromotionPiece, type Square } from "../lib/chess/types";
import { play as playSound } from "../lib/sound";
import { puzzleApi, type Puzzle, type PuzzleTheme } from "../lib/puzzleApi";
import "./Puzzles.css";

type Mode = "rated" | "custom" | "rush" | "daily" | "mistakes" | "review";
type Phase = "intro" | "solving" | "solved" | "failed" | "revealed";

interface Solver {
  chess: Chess;
  fen: string;
  index: number; // next expected move index in puzzle.moves
  lastMove: [Square, Square] | null;
  phase: Phase;
  wrongMove: [Square, Square] | null;
  hintLevel: number;
  played: string[]; // the solver's accepted moves, UCI, sent to the server to judge the attempt
}

function startSolver(p: Puzzle): Solver {
  const chess = new Chess(p.fen);
  return { chess, fen: chess.fen(), index: 0, lastMove: null, phase: "intro", wrongMove: null, hintLevel: 0, played: [] };
}

export function PuzzlesPage() {
  const [mode, setMode] = useState<Mode>("rated");
  const [themes, setThemes] = useState<PuzzleTheme[]>([]);
  const [selectedThemes, setSelectedThemes] = useState<string[]>([]);
  const [opening, setOpening] = useState<string | null>(null); // a study plan's opening tag: kept for every puzzle until the player changes the filter
  const [range, setRange] = useState<[number, number]>([600, 2400]);
  const [puzzle, setPuzzle] = useState<Puzzle | null>(null);
  const [solver, setSolver] = useState<Solver | null>(null);
  const [playerRating, setPlayerRating] = useState<number | null>(null);
  const [result, setResult] = useState<{ delta: number; rating_after: number; puzzle_rating: number | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streak, setStreak] = useState(0);
  const [stats, setStats] = useState<{ rating: number; attempts: number; solved: number; accuracy: number | null; rush_best: Record<string, number> } | null>(null);
  // rush state
  const [rush, setRush] = useState<{ queue: Puzzle[]; i: number; score: number; wrong: number; endsAt: number | null; mode: "3m" | "5m" | "survival"; finished: boolean } | null>(null);
  const [now, setNow] = useState(Date.now());
  const startedAt = useRef<number>(Date.now());
  const [params] = useSearchParams();
  const [hearts, setHeartsState] = useState(5);
  const heartsKey = useRef<string | null>(null); // daily hearts survive a reload: "daily-hearts:<date>"
  const setHearts = (h: number | ((x: number) => number)) => setHeartsState((cur) => {
    const next = typeof h === "function" ? h(cur) : h;
    try { if (heartsKey.current) localStorage.setItem(heartsKey.current, String(next)); } catch { /* storage off */ }
    return next;
  });
  const recorded = useRef(false); // one attempt per puzzle load: a retry is practice, not a second result
  const [mistakes, setMistakes] = useState<{ queue: Puzzle[]; i: number; total: number } | null>(null);

  useEffect(() => {
    puzzleApi.themes().then((r) => setThemes(r.themes)).catch(() => undefined);
    puzzleApi.stats().then(setStats).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (params.get("daily")) {
      setMode("daily");
      puzzleApi.daily().then((r) => {
        heartsKey.current = `daily-hearts:${r.date}`;
        let saved: number | null = null;
        try { saved = Number(localStorage.getItem(heartsKey.current) ?? "") || null; } catch { /* storage off */ }
        setHearts(saved ?? 5);
        void load(r.puzzle);
      }).catch((e: Error) => setError(e.message));
    }
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!params.get("review")) return; // from Review: the puzzles missed before that are due again
    setMode("review");
    puzzleApi.review().then((r) => {
      if (!r.puzzles.length) { setError("No puzzles due for review."); return; }
      setMistakes({ queue: r.puzzles, i: 0, total: r.puzzles.length });
      void load(r.puzzles[0]);
    }).catch((e: Error) => setError(e.message));
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const theme = params.get("theme"); // from a lesson: practise what it taught
    const opening = params.get("opening"); // from a study plan: puzzles taken from games in this opening
    if (!theme && !opening) return;
    setMode("custom");
    setSelectedThemes(theme ? [theme] : []);
    setOpening(opening);
    puzzleApi.next({ themes: theme ? [theme] : undefined, opening: opening ?? undefined }).then((r) => load(r.puzzle, r.player_rating)).catch((e: Error) => setError(e.message));
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!rush || rush.finished || rush.endsAt === null) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [rush]);

  const finishRush = useCallback(async (r: NonNullable<typeof rush>) => {
    if (r.finished) return;
    const done = { ...r, finished: true };
    setRush(done);
    playSound(r.score > 0 ? "win" : "lose");
    try {
      const res = await puzzleApi.rushFinish(r.mode, r.score, r.wrong, (Date.now() - startedAt.current) / 1000);
      setStats((s) => (s ? { ...s, rush_best: { ...s.rush_best, [r.mode]: res.best } } : s));
    } catch { /* offline */ }
  }, []);

  useEffect(() => {
    if (rush && !rush.finished && rush.endsAt !== null && now >= rush.endsAt) void finishRush(rush);
  }, [now, rush, finishRush]);
  const remaining = rush && rush.endsAt !== null ? Math.max(0, Math.ceil((rush.endsAt - now) / 1000)) : null;
  const lastTen = remaining !== null && remaining <= 10 && remaining > 0 && !rush?.finished;
  useEffect(() => { if (lastTen) playSound("rushTick"); }, [remaining, lastTen]); // one tick a second while the clock runs down

  const load = useCallback(async (p: Puzzle, rating?: number) => {
    recorded.current = false;
    setPuzzle(p);
    setResult(null);
    setError(null);
    const s = startSolver(p);
    setSolver(s);
    if (rating !== undefined) setPlayerRating(rating);
    if (p.solver_first) {
      setSolver({ ...s, phase: "solving" });
      return;
    }
    // play the opponent's first move after a beat
    setTimeout(() => {
      setSolver((cur) => {
        if (!cur || cur.phase !== "intro" || cur.fen !== s.fen) return cur; // a later load() owns the board
        const c = new Chess(cur.fen);
        const mv = safeMove(c, p.moves[0]);
        if (!mv) return cur;
        playSound(soundForMove(mv, c));
        return { ...cur, chess: c, fen: c.fen(), index: 1, lastMove: [p.moves[0].slice(0, 2), p.moves[0].slice(2, 4)], phase: "solving" };
      });
    }, 500);
  }, []);

  const nextPuzzle = useCallback(async () => {
    try {
      if (mode === "mistakes" || mode === "review") {
        const q = mistakes ?? { queue: mode === "review" ? (await puzzleApi.review()).puzzles : (await puzzleApi.mistakes()).puzzles, i: -1, total: 0 };
        const i = q.i + 1;
        if (!q.queue.length) { setError(mode === "review" ? "No puzzles due for review." : "No mistakes yet. Play and review a few games first."); return; }
        if (i >= q.queue.length) { setError(mode === "review" ? "Review done: every puzzle that was due has had its turn." : "You have been through all your mistakes. Play more games."); return; }
        setMistakes({ ...q, i, total: q.queue.length });
        await load(q.queue[i]);
        return;
      }
      if (mode === "rush" && rush) {
        const i = rush.i + 1;
        if (i >= rush.queue.length) { await finishRush(rush); return; }
        setRush({ ...rush, i });
        await load(rush.queue[i]);
        return;
      }
      const r = mode === "custom"
        ? await puzzleApi.next({ themes: selectedThemes, opening: opening ?? undefined, min: range[0], max: range[1] })
        : await puzzleApi.next({});
      await load(r.puzzle, r.player_rating);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [mode, rush, selectedThemes, opening, range, load, finishRush, mistakes]);

  const startRush = async (m: "3m" | "5m" | "survival") => {
    try {
      const r = await puzzleApi.rushStart(m);
      startedAt.current = Date.now();
      const state = { queue: r.puzzles, i: 0, score: 0, wrong: 0, endsAt: r.seconds ? Date.now() + r.seconds * 1000 : null, mode: m, finished: false };
      setMode("rush");
      setRush(state);
      setStreak(0);
      await load(r.puzzles[0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const record = async (solved: boolean, moves: string[]) => {
    if (!puzzle || recorded.current) return;
    recorded.current = true;
    const hinted = (solver?.hintLevel ?? 0) >= 1; // lichess and chess.com count a hinted puzzle as missed
    if (mode === "rush" && rush) {
      const next = { ...rush, score: rush.score + (solved ? 1 : 0), wrong: rush.wrong + (solved ? 0 : 1) };
      setRush(next);
      if (next.wrong >= 3) { await finishRush(next); return; }
      puzzleApi.attempt(puzzle.id, moves, (Date.now() - startedAt.current) / 1000, "rush", hinted).catch(() => undefined);
      setTimeout(() => void nextPuzzleFrom(next), solved ? 500 : 1200);
      return;
    }
    try {
      const r = await puzzleApi.attempt(puzzle.id, moves, (Date.now() - startedAt.current) / 1000, mode === "rated" ? "rated" : mode === "daily" ? "daily" : mode === "mistakes" ? "mistakes" : mode === "review" ? "review" : "custom", hinted);
      setResult({ delta: r.delta, rating_after: r.rating_after, puzzle_rating: r.puzzle_rating });
      setPlayerRating(r.rating_after);
      // the stats card counts rated attempts only, as the server does
      if (mode === "rated") setStats((s) => (s ? { ...s, rating: r.rating_after, attempts: s.attempts + 1, solved: s.solved + (r.solved ? 1 : 0) } : s));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const nextPuzzleFrom = async (r: NonNullable<typeof rush>) => {
    const i = r.i + 1;
    if (i >= r.queue.length) { await finishRush(r); return; }
    setRush({ ...r, i });
    await load(r.queue[i]);
  };

  // once the puzzle is over, any move on the board is judged by the engine; the first is measured against the solution
  const explore = useExplore(solver?.fen ?? START_FEN, puzzle && solver ? puzzle.moves[solver.index] : undefined);
  const over = solver !== null && (solver.phase === "solved" || solver.phase === "failed" || solver.phase === "revealed") && mode !== "rush";

  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (!solver || !puzzle || solver.phase !== "solving") return;
    const c = new Chess(solver.fen);
    const mv = safeMove(c, { from, to, promotion });
    if (!mv) return;
    const expected = puzzle.moves[solver.index];
    const played = from + to + (promotion ?? "");
    const isMate = c.isCheckmate();
    const playedSoFar = [...solver.played, played];
    if (played === expected || isMate) {
      playSound(soundForMove(mv, c));
      const index = solver.index + 1;
      if (index >= puzzle.moves.length || isMate) {
        setSolver({ ...solver, chess: c, fen: c.fen(), index, lastMove: [from, to], phase: "solved", played: playedSoFar });
        setStreak((s) => s + 1);
        playSound("correct");
        void record(true, playedSoFar);
        return;
      }
      // opponent replies
      const reply = puzzle.moves[index];
      setSolver({ ...solver, chess: c, fen: c.fen(), index, lastMove: [from, to], played: playedSoFar });
      setTimeout(() => {
        const c2 = new Chess(c.fen());
        const rm = safeMove(c2, reply);
        if (rm) playSound(soundForMove(rm, c2));
        setSolver((cur) => (cur ? { ...cur, chess: c2, fen: c2.fen(), index: index + 1, lastMove: [reply.slice(0, 2), reply.slice(2, 4)] } : cur));
      }, 350);
    } else if (mode === "daily" && hearts > 1) {
      playSound("wrong");
      setHearts((h) => h - 1);
      setSolver({ ...solver, wrongMove: [from, to], hintLevel: Math.max(solver.hintLevel, 1) });
    } else {
      playSound("wrong");
      setSolver({ ...solver, phase: "failed", wrongMove: [from, to] });
      setStreak(0);
      void record(false, playedSoFar);
      if (mode !== "rush") explore.onMove(from, to, promotion); // play the miss so the engine shows why it fails
    }
  };

  const retry = () => {
    if (!puzzle) return;
    explore.reset();
    void load(puzzle).then(() => { recorded.current = true; }); // practice only: the first attempt already counted
    setResult(null);
  };

  const solverColor = puzzle?.solver_color === "white" ? "w" : "b";
  const dests = useMemo(() => (solver && solver.phase === "solving" ? destsFor(solver.chess) : new Map()), [solver]);
  const shapes: Shape[] = [];
  const hintMove = solver && puzzle && solver.phase === "solving" && solver.hintLevel >= 1 ? puzzle.moves[solver.index] : undefined;
  if (solver && hintMove) {
    const exp = hintMove;
    shapes.push(solver.hintLevel >= 2 ? { orig: exp.slice(0, 2), dest: exp.slice(2, 4), brush: "green" } : { orig: exp.slice(0, 2), brush: "yellow" });
  }
  const highlights = solver?.wrongMove && (solver.phase === "failed" || mode === "daily") ? [{ square: solver.wrongMove[1], brush: "red" as const }] : [];
  const trained = (puzzle?.themes ?? []).map((k) => themes.find((t) => t.key === k)).filter((t): t is PuzzleTheme => !!t?.motif);

  return (
    <div className="board-page puzzles" data-testid="puzzles">
      <div className="board-col">
        {puzzle && solver ? (
          <Board
            fen={explore.active ? explore.fen : solver.fen}
            orientation={puzzle.solver_color}
            movable={over ? { color: "both", dests: explore.dests } : { color: solver.phase === "solving" ? solverColor : "none", dests }}
            lastMove={explore.active ? explore.lastMove : solver.lastMove}
            check={explore.active ? explore.check : checkSquare(solver.chess)}
            shapes={explore.active ? [] : shapes}
            highlights={explore.active ? [] : highlights}
            onMove={over ? explore.onMove : onMove}
          />
        ) : <Board fen={START_FEN} />}
      </div>

      <aside className="side-col">
        {rush && (
          <div className="card rush-bar" data-testid="rush-bar">
            <div><div className="faint">score</div><div className="num rush-score">{rush.score}</div></div>
            <div><div className="faint">strikes</div><div className="rush-strikes">{"✖".repeat(rush.wrong)}<span className="faint">{"✖".repeat(3 - rush.wrong)}</span></div></div>
            <div><div className="faint">time</div><div className={`num rush-time ${lastTen ? "low pulse" : ""}`}>{remaining === null ? "∞" : `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`}</div></div>
            {rush.finished && <div className="rush-done"><Trophy size={16} /> Run over: {rush.score} solved. <button className="btn btn-sm" onClick={() => { setRush(null); setPuzzle(null); setSolver(null); }}>Back</button></div>}
          </div>
        )}
        {puzzle && solver && (
          <div className="card">
            <div className={`puzzle-state ${solver.phase}`} key={solver.phase}>
              <strong data-testid="puzzle-turn">{solver.phase === "solved" ? "Solved!" : solver.phase === "revealed" ? "Solution shown" : solver.phase === "failed" ? "Not quite" : solver.phase === "intro" ? `${mode === "daily" ? "Daily puzzle · " : ""}Watch the opponent's move…` : `${mode === "daily" ? "Daily puzzle · " : ""}${puzzle.solver_color === "white" ? "White" : "Black"} to play`}</strong>
              {(solver.phase === "intro" || solver.phase === "solving") && <span className="puzzle-goal" data-testid="puzzle-goal">{puzzle.goal}</span>}
            </div>
            <div className="row puzzle-meta">
              <span className="chip">puzzle {puzzle.rating}</span>
              {mode === "daily" && <span className="chip chip-danger puzzle-hearts" data-testid="hearts">{"♥".repeat(hearts)}<span className="faint">{"♥".repeat(5 - hearts)}</span></span>}
              {streak > 1 && <span className="chip chip-ok pop" key={streak}><Flame size={12} /> {streak} in a row</span>}
            </div>
            {playerRating !== null && mode === "rated" && <div className="faint">Your puzzle rating: <b className="num">{playerRating}</b>{result && <span className={result.delta >= 0 ? "ok" : "bad"}> ({result.delta >= 0 ? "+" : ""}{result.delta})</span>}</div>}
            {solver.phase === "solving" && (
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn btn-sm" onClick={() => setSolver({ ...solver, hintLevel: Math.min(2, solver.hintLevel + 1) })} data-testid="puzzle-hint"><Lightbulb size={14} /> {solver.hintLevel === 0 ? "Hint" : solver.hintLevel === 1 ? "Show move" : "Shown"}</button>
              </div>
            )}
            {(solver.phase === "failed" || solver.phase === "revealed") && (
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn btn-sm" onClick={retry} data-testid="puzzle-retry"><RotateCcw size={14} /> Retry</button>
                {solver.phase === "failed" && <button className="btn btn-sm" onClick={() => {
                  // play the rest of the line from where the solver went wrong; giving up is not solving
                  const c = new Chess(solver.fen);
                  const rest = puzzle.moves.slice(solver.index);
                  for (const m of rest) safeMove(c, m);
                  const last = rest[rest.length - 1];
                  explore.reset(); // the solution plays on the puzzle board, not on the miss
                  setSolver({ ...solver, chess: c, fen: c.fen(), lastMove: last ? [last.slice(0, 2), last.slice(2, 4)] : solver.lastMove, phase: "revealed" });
                }} data-testid="puzzle-show-solution">Show solution</button>}
                {mode !== "rush" && <button className="btn btn-sm btn-primary" onClick={nextPuzzle} data-testid="puzzle-next">Next</button>}
              </div>
            )}
            {solver.phase === "solved" && mode !== "rush" && (
              <div className="row" style={{ marginTop: 8 }}>
                {mode === "daily" ? <span className="chip chip-ok">Done for today. Come back tomorrow.</span> : <button className="btn btn-sm btn-primary" onClick={nextPuzzle} data-testid="puzzle-next">Next puzzle</button>}
              </div>
            )}
            {over && <div className="puzzle-explore"><ExplorePanel explore={explore} compareLabel="The solution" idle={<p className="faint">Try other moves on the board: the engine judges each one.</p>} /></div>}
            {over && trained.length > 0 && (
              <div className="puzzle-trained" data-testid="puzzle-trained">
                <span className="lesson-kicker">What this puzzle trains</span>
                {trained.map((t) => (
                  <div key={t.key}>
                    <b>{t.name}</b>: <span className="muted">{t.description}</span>
                    {t.lesson && <> <Link to={`/learn/${t.lesson.id}`} className="link">Lesson: {t.lesson.title}</Link></>}
                  </div>
                ))}
              </div>
            )}
            {puzzle.source?.white && <div className="faint" style={{ marginTop: 8 }}>From {puzzle.source.white} vs {puzzle.source.black}{/^\d{4}$/.test(String(puzzle.source.year ?? "")) ? `, ${puzzle.source.year}` : ""}{(puzzle.source as { played?: string }).played ? ` · you played ${(puzzle.source as { played?: string }).played}` : ""}</div>}
            {mode === "mistakes" && mistakes && <div className="faint">mistake {mistakes.i + 1} of {mistakes.total}</div>}
          </div>
        )}
        {!puzzle && (
          <div className="card puzzles-start">
            <h2>{mode === "rush" ? "Puzzle Rush" : mode === "custom" ? "Custom puzzles" : mode === "mistakes" ? "My mistakes" : mode === "review" ? "Review" : "Rated puzzles"}</h2>
            <p className="muted">{mode === "rush" ? "Solve as many as you can. Three mistakes end the run." : mode === "custom" ? "Pick themes and a rating range. These do not change your rating." : mode === "mistakes" ? "Positions from your reviewed games where you went wrong. Find the move you missed." : mode === "review" ? "Puzzles you missed before, back on the spaced ladder: a day, then three, a week, and on." : "Puzzles near your rating. Solve the whole line to earn points."}</p>
            {mode === "rush" ? (
              <div className="row">
                <button className="btn btn-primary" onClick={() => startRush("3m")} data-testid="rush-3m"><Timer size={14} /> 3 minutes</button>
                <button className="btn" onClick={() => startRush("5m")}><Timer size={14} /> 5 minutes</button>
                <button className="btn" onClick={() => startRush("survival")}>Survival</button>
              </div>
            ) : (
              <button className="btn btn-primary btn-lg" onClick={nextPuzzle} data-testid="start-puzzles">Start</button>
            )}
            {error && <span className="chip chip-danger">{error}</span>}
          </div>
        )}
        <div className="puzzles-modes">
          {(["rated", "custom", "rush", "mistakes"] as Mode[]).map((m) => (
            <button key={m} className={`btn btn-sm ${mode === m ? "btn-primary" : ""}`} onClick={() => { setMode(m); setOpening(null); setError(null); if (m !== "rush") setRush(null); if (m !== "mistakes") setMistakes(null); }} data-testid={`mode-${m}`}>{m === "rush" ? "Puzzle Rush" : m === "mistakes" ? "My mistakes" : m[0].toUpperCase() + m.slice(1)}</button>
          ))}
        </div>
        {mode === "custom" && (
          <details className="card fold" open={!puzzle}>
            <summary>Themes <span className="faint">· {opening ? `${opening.replace(/_/g, " ")} · ` : ""}{selectedThemes.length ? `${selectedThemes.length} selected` : "any"}</span></summary>
            <div className="row" style={{ margin: "10px 0" }}>
              <label className="faint">Rating</label>
              <input type="number" className="input" style={{ width: 90 }} value={range[0]} onChange={(e) => setRange([Number(e.target.value), range[1]])} />
              <span className="faint">to</span>
              <input type="number" className="input" style={{ width: 90 }} value={range[1]} onChange={(e) => setRange([range[0], Number(e.target.value)])} />
            </div>
            <div className="theme-grid">
              {themes.map((t) => (
                <button key={t.key} className={`theme-chip ${selectedThemes.includes(t.key) ? "on" : ""}`} title={t.description} onClick={() => { setOpening(null); setSelectedThemes((s) => (s.includes(t.key) ? s.filter((x) => x !== t.key) : [...s, t.key])); }}>
                  {t.name} <span className="faint num">{t.count}</span>
                </button>
              ))}
            </div>
          </details>
        )}
        {stats && (
          <div className="card">
            <div className="card-title"><h3>Your stats</h3></div>
            <div className="stats-grid">
              <div><div className="faint">rating</div><b className="num">{stats.rating}</b></div>
              <div><div className="faint">solved</div><b className="num">{stats.solved}/{stats.attempts}</b></div>
              <div><div className="faint">accuracy</div><b className="num">{stats.accuracy === null ? "–" : `${stats.accuracy}%`}</b></div>
              <div><div className="faint">rush best</div><b className="num">{Math.max(stats.rush_best["3m"] ?? 0, stats.rush_best["5m"] ?? 0, stats.rush_best.survival ?? 0)}</b></div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
