import { Chess } from "chess.js";
import { Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Board } from "../components/board/Board";
import { MoveList } from "../components/play/MoveList";
import { checkSquare, destsFor, safeMove, soundForMove } from "../lib/chess/game";
import { START_FEN, type PromotionPiece, type Square } from "../lib/chess/types";
import { play as playSound } from "../lib/sound";
import "./Openings.css";

interface Continuation { san: string; uci: string; eco: string | null; name: string | null; lines_below: number }
interface Explore { fen: string; opening: { eco: string; name: string; pgn: string; ply: number } | null; continuations: Continuation[] }
interface Family { name: string; eco_from: string; eco_to: string; lines: number; pgn: string }
type Side = "white" | "black";
interface CourseSummary { id: string; name: string; side: Side; eco_from: string | null; eco_to: string | null; summary: string; lines: number; traps: number; model_games: number }
interface CourseLine {
  id: string; name: string; pgn: string; opening: { eco: string; name: string };
  moves: { ply: number; san: string; uci: string; fen: string; comment: string | null }[];
  mistake_ply?: number; mistake_by?: Side; punishment?: string;
}
interface CourseDetail extends Omit<CourseSummary, "lines" | "traps" | "model_games"> {
  ideas: Record<Side, string[]>; structures: { name: string; text: string }[]; pieces: Record<Side, string[]>;
  lines: CourseLine[]; traps: CourseLine[]; model_games: { id: string; white: string; black: string; year: string }[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

export function OpeningsPage() {
  const { courseId } = useParams();
  return courseId ? <CourseView courseId={courseId} /> : <Explorer />;
}

function Explorer() {
  const [chess] = useState(() => new Chess());
  const [fen, setFen] = useState(START_FEN);
  const [history, setHistory] = useState<{ san: string; fen: string; uci: string }[]>([]);
  const [explore, setExplore] = useState<Explore | null>(null);
  const [families, setFamilies] = useState<Family[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ eco: string; name: string; pgn: string; ply: number }[]>([]);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [viewPly, setViewPly] = useState(0);
  const [courses, setCourses] = useState<CourseSummary[]>([]);

  const latest = useRef("");
  const refresh = useCallback(async (moves: string[]) => {
    const key = moves.join(" ");
    latest.current = key;
    const r = await get<Explore>(`/api/openings/explore?moves=${encodeURIComponent(key)}`);
    if (latest.current === key) setExplore(r); // a later step may have asked first
  }, []);

  useEffect(() => {
    void refresh([]);
    get<{ families: Family[] }>("/api/openings/families").then((r) => setFamilies(r.families.slice(0, 40))).catch(() => undefined);
    get<{ courses: CourseSummary[] }>("/api/openings/courses").then((r) => setCourses(r.courses)).catch(() => undefined);
  }, [refresh]);
  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const t = setTimeout(() => get<{ results: typeof results }>(`/api/openings/search?q=${encodeURIComponent(query)}`).then((r) => setResults(r.results)).catch(() => undefined), 200);
    return () => clearTimeout(t);
  }, [query]);

  const sync = () => {
    const f = chess.fen();
    setFen(f);
    const h = chess.history({ verbose: true }).map((m) => ({ san: m.san, fen: m.after, uci: m.from + m.to + (m.promotion ?? "") }));
    setHistory(h);
    setViewPly(h.length);
    void refresh(h.map((m) => m.uci));
  };

  const playSan = (san: string) => {
    const mv = safeMove(chess, san);
    if (!mv) return;
    playSound(soundForMove(mv, chess));
    sync();
  };
  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    const mv = safeMove(chess, { from, to, promotion });
    if (!mv) return;
    playSound(soundForMove(mv, chess));
    sync();
  };
  const loadLine = async (pgn: string) => {
    chess.reset();
    for (const tok of pgn.split(" ")) {
      if (/^\d/.test(tok)) continue;
      safeMove(chess, tok);
    }
    sync();
    setResults([]);
    setQuery("");
  };
  const goTo = (ply: number) => {
    const target = ply <= 0 ? START_FEN : history[ply - 1].fen;
    setViewPly(ply);
    setFen(target);
    void refresh(history.slice(0, ply).map((m) => m.uci));
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") goTo(Math.max(0, viewPly - 1));
      else if (e.key === "ArrowRight") goTo(Math.min(history.length, viewPly + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const undo = () => { chess.undo(); sync(); };
  const reset = () => { chess.reset(); sync(); };

  const live = viewPly === history.length;
  const boardChess = useMemo(() => new Chess(fen), [fen]);
  const dests = useMemo(() => (live ? destsFor(boardChess) : new Map()), [boardChess, live]);
  const maxBelow = Math.max(1, ...(explore?.continuations.map((c) => c.lines_below) ?? [1]));
  const lastUci = viewPly > 0 ? history[viewPly - 1].uci : null;

  return (
    <div className="openings" data-testid="openings">
      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <div>
            <h2 data-testid="opening-name">{explore?.opening ? `${explore.opening.eco} · ${explore.opening.name}` : viewPly ? "Out of book" : "Starting position"}</h2>
            <div className="faint">{explore?.opening?.pgn ?? "Play moves on the board or pick a line."}</div>
          </div>
          <div className="row">
            <button className="btn btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
            <button className="btn btn-sm" onClick={undo} disabled={!history.length}>Undo</button>
            <button className="btn btn-sm" onClick={reset} disabled={!history.length}>Reset</button>
          </div>
        </div>
        <Board fen={fen} orientation={orientation} movable={{ color: live ? "both" : "none", dests }} lastMove={lastUci ? [lastUci.slice(0, 2), lastUci.slice(2, 4)] : null} check={checkSquare(boardChess)} onMove={onMove} />
        <div className="card" style={{ marginTop: 12, padding: 0 }}>
          <MoveList moves={history.map((m, i) => ({ ply: i + 1, san: m.san }))} currentPly={viewPly} onSelect={goTo} opening={explore?.opening?.name ?? null} />
        </div>
      </div>
      <aside className="openings-side">
        {!history.length && courses.length > 0 && (
          <div className="card">
            <div className="card-title"><h3>Opening courses</h3><span className="faint">why every move is played</span></div>
            <ul className="courses" data-testid="courses">
              {courses.map((c) => (
                <li key={c.id}>
                  <Link to={`/openings/courses/${c.id}`} data-testid={`course-${c.id}`}>
                    <b>{c.name}</b>
                    <span className="chip">as {c.side === "white" ? "White" : "Black"}</span>
                    <span className="faint num">{c.lines} lines · {c.traps} traps</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="card">
          <div className="row input-row">
            <Search size={16} className="faint" />
            <input className="input" placeholder="Search openings (Najdorf, London, C65…)" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="opening-search" />
          </div>
          {results.length > 0 && (
            <ul className="results">
              {results.map((r) => (
                <li key={r.pgn}><button onClick={() => loadLine(r.pgn)}><span className="chip">{r.eco}</span> {r.name} <span className="faint">{r.pgn}</span></button></li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <div className="card-title"><h3>Named continuations</h3><span className="faint">{explore?.continuations.length ?? 0}</span></div>
          {explore && explore.continuations.length === 0 && <p className="faint">No named lines from here. You are on your own: use the engine in Play or Coach.</p>}
          <ul className="conts" data-testid="continuations">
            {explore?.continuations.map((c) => (
              <li key={c.uci}>
                <button onClick={() => playSan(c.san)} disabled={!live}>
                  <b className="conts-san">{c.san}</b>
                  <span className="conts-name">{c.name && <><span className="chip">{c.eco}</span> {c.name}</>}</span>
                  <span className="conts-bar"><i style={{ width: `${Math.max(4, (100 * c.lines_below) / maxBelow)}%` }} /></span>
                  <span className="faint num">{c.lines_below}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        {!history.length && (
          <div className="card">
            <div className="card-title"><h3>Browse families</h3></div>
            <div className="families">
              {families.map((f) => (
                <button key={f.name} className="theme-chip" onClick={() => loadLine(f.pgn)} title={`${f.eco_from}–${f.eco_to}, ${f.lines} lines`}>{f.name} <span className="faint num">{f.lines}</span></button>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

const moveLabel = (ply: number, san: string) => `${Math.ceil(ply / 2)}${ply % 2 ? "." : "..."}${san}`;

/** One course: step its lines and traps with a note on every move, or practise a line from memory. */
function CourseView({ courseId }: { courseId: string }) {
  const navigate = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [pick, setPick] = useState<{ kind: "lines" | "traps"; i: number }>({ kind: "lines", i: 0 });
  const [ply, setPly] = useState(0);
  // practice: the learner's moves found first try, the ones missed, and the last miss to explain
  const [practice, setPractice] = useState<{ right: number; wrong: number; miss: string | null } | null>(null);
  const [shaking, setShaking] = useState(false);
  useEffect(() => { get<CourseDetail>(`/api/openings/courses/${courseId}`).then(setCourse).catch(() => navigate("/openings")); }, [courseId, navigate]);

  const line = course ? course[pick.kind][pick.i] ?? null : null;
  const moves = line?.moves ?? [];
  const fen = ply === 0 ? START_FEN : moves[ply - 1].fen;
  const board = useMemo(() => new Chess(fen), [fen]);
  const learner = course?.side === "black" ? "b" : "w";
  const done = ply >= moves.length;
  const myTurn = practice !== null && !done && board.turn() === learner;
  const dests = useMemo(() => (myTurn ? destsFor(board) : new Map()), [board, myTurn]);

  const step = useCallback((to: number) => {
    if (to === ply + 1 && to <= moves.length) {
      const c = new Chess(fen);
      const mv = safeMove(c, moves[to - 1].uci);
      if (mv) playSound(soundForMove(mv, c));
    }
    setPly(Math.max(0, Math.min(moves.length, to)));
  }, [ply, fen, moves]);

  // in practice the other side's moves play themselves
  useEffect(() => {
    if (!practice || done || board.turn() === learner) return;
    const t = setTimeout(() => step(ply + 1), 500);
    return () => clearTimeout(t);
  }, [practice, done, board, learner, ply, step]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (practice) return;
      if (e.key === "ArrowLeft") step(ply - 1);
      else if (e.key === "ArrowRight") step(ply + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [practice, ply, step]);

  const choose = (kind: "lines" | "traps", i: number) => { setPick({ kind, i }); setPly(0); setPractice(null); };

  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (!myTurn || !practice) return;
    const expected = moves[ply];
    if (from + to + (promotion ?? "") === expected.uci) {
      setPractice({ ...practice, right: practice.right + 1, miss: null });
    } else {
      const c = new Chess(fen);
      const tried = safeMove(c, { from, to, promotion });
      playSound("wrong");
      setShaking(true);
      setPractice({ ...practice, wrong: practice.wrong + 1, miss: `${tried ? `Not ${tried.san}. ` : ""}The line plays ${moveLabel(expected.ply, expected.san)}.${expected.comment ? ` ${expected.comment}` : ""}` });
    }
    step(ply + 1);
  };

  if (!course || !line) return <p className="faint">Loading course…</p>;
  const current = ply > 0 ? moves[ply - 1] : null;
  const isTrap = line.mistake_ply !== undefined;
  const mistake = isTrap ? moves[line.mistake_ply! - 1] : null;
  const highlights = mistake && ply === mistake.ply ? [{ square: mistake.uci.slice(2, 4), brush: "red" as const }] : [];
  const other: Side = course.side === "white" ? "black" : "white";
  return (
    <div className="openings" data-testid="course">
      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <div>
            <h2 data-testid="course-line">{line.name}</h2>
            <div className="faint">{line.opening.eco} · {line.opening.name}</div>
          </div>
          {pick.kind === "lines" && (practice
            ? <button className="btn btn-sm" onClick={() => { setPractice(null); setPly(0); }}>Stop practice</button>
            : <button className="btn btn-sm btn-primary" onClick={() => { setPly(0); setPractice({ right: 0, wrong: 0, miss: null }); }} data-testid="practise-line">Practise this line</button>)}
        </div>
        <div className={`course-board ${shaking ? "shake" : ""}`} onAnimationEnd={() => setShaking(false)}>
          <Board fen={fen} orientation={course.side} movable={{ color: myTurn ? learner : "none", dests }} lastMove={current ? [current.uci.slice(0, 2), current.uci.slice(2, 4)] : null} check={checkSquare(board)} highlights={highlights} onMove={onMove} />
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn btn-sm" onClick={() => step(0)} disabled={!!practice}>⏮</button>
          <button className="btn btn-sm" onClick={() => step(ply - 1)} disabled={!!practice}>◀</button>
          <button className="btn btn-sm" onClick={() => step(ply + 1)} disabled={!!practice}>▶</button>
          <button className="btn btn-sm" onClick={() => step(moves.length)} disabled={!!practice}>⏭</button>
          <span className="chip num">{ply}/{moves.length}</span>
        </div>
        <div className="card" style={{ marginTop: 12, padding: 0 }}>
          <MoveList moves={(practice ? moves.slice(0, ply) : moves).map((m) => ({ ply: m.ply, san: m.san }))} currentPly={ply} onSelect={(p) => !practice && step(p)} opening={line.opening.name} />
        </div>
      </div>
      <aside className="openings-side course-side">
        <div className="card stack">
          <Link to="/openings" className="muted">← Openings</Link>
          <h2>{course.name}</h2>
          <div className="row"><span className="chip">as {course.side === "white" ? "White" : "Black"}</span>{course.eco_from && <span className="chip num">{course.eco_from}–{course.eco_to}</span>}</div>
          <p className="muted">{course.summary}</p>
        </div>
        <div className="card stack" data-testid="course-note">
          {practice ? (
            <>
              {practice.miss && <div className="course-note bad" data-testid="practice-miss">{practice.miss}</div>}
              {done
                ? <div className="course-note ok" data-testid="practice-done">Line complete: {practice.right} of {practice.right + practice.wrong} moves from memory.</div>
                : <div className="faint">{myTurn ? "Your move: play the line's move." : "Watch the reply…"}</div>}
            </>
          ) : (
            <>
              {current?.comment ? <p><b>{moveLabel(current.ply, current.san)}</b> {current.comment}</p> : <p className="faint">{ply === 0 ? "Step through the moves: each move with an idea has a note." : `${moveLabel(current!.ply, current!.san)}: no note on this move.`}</p>}
              {mistake && (ply >= mistake.ply
                ? <div className="course-note bad" data-testid="trap-punishment"><b>{moveLabel(mistake.ply, mistake.san)} is the mistake.</b> {line.punishment}</div>
                : <div className="faint">{line.mistake_by === course.side ? "A trap to avoid" : "A trap to set"}: step to {moveLabel(mistake.ply, mistake.san)}.</div>)}
            </>
          )}
        </div>
        <div className="card">
          <div className="card-title"><h3>Lines</h3></div>
          <ul className="course-items">
            {course.lines.map((l, i) => <li key={l.id}><button className={pick.kind === "lines" && pick.i === i ? "on" : ""} onClick={() => choose("lines", i)}>{l.name}</button></li>)}
          </ul>
          <div className="card-title" style={{ marginTop: 12 }}><h3>Traps</h3></div>
          <ul className="course-items">
            {course.traps.map((t, i) => (
              <li key={t.id}>
                <button className={pick.kind === "traps" && pick.i === i ? "on" : ""} onClick={() => choose("traps", i)} data-testid={`trap-${t.id}`}>
                  <span className="grow">{t.name}</span><span className="chip">{t.mistake_by === course.side ? "avoid" : "set"}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="card stack">
          <details open><summary>Ideas for {course.side === "white" ? "White" : "Black"}</summary><ul>{course.ideas[course.side].map((t) => <li key={t}>{t}</li>)}</ul></details>
          <details><summary>What {other === "white" ? "White" : "Black"} wants</summary><ul>{course.ideas[other].map((t) => <li key={t}>{t}</li>)}</ul></details>
          <details><summary>Pawn structures</summary><ul>{course.structures.map((s) => <li key={s.name}><b>{s.name}.</b> {s.text}</li>)}</ul></details>
          <details><summary>Key pieces</summary><ul>{course.pieces[course.side].map((t) => <li key={t}>{t}</li>)}</ul></details>
          {course.model_games.length > 0 && (
            <details><summary>Model games <span className="faint num">{course.model_games.length}</span></summary>
              <ul>{course.model_games.map((g) => <li key={g.id}><Link to={`/games/${g.id}`}>{g.white} – {g.black}{/^\d{4}$/.test(g.year) ? `, ${g.year}` : ""}</Link></li>)}</ul>
            </details>
          )}
        </div>
      </aside>
    </div>
  );
}
