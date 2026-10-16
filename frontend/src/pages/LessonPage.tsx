import { Chess } from "chess.js";
import { ArrowLeft, ArrowRight, Lightbulb } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Board } from "../components/board/Board";
import { DrillBoard, type DrillOutcome } from "../components/learn/DrillBoard";
import type { Shape } from "../components/board/shapes";
import { checkSquare, destsFor, safeMove, soundForMove } from "../lib/chess/game";
import { START_FEN, type PromotionPiece, type Square } from "../lib/chess/types";
import { learnApi, type LessonDetail, type Section } from "../lib/learnApi";
import { Markdown } from "../lib/markdown";
import { play as playSound } from "../lib/sound";
import "./Learn.css";

type TaskState = { status: "idle" | "ok" | "bad" | "done" | "revealed"; text: string; attempts: number; hint: boolean };

export function LessonPage() {
  const { lessonId = "" } = useParams();
  const navigate = useNavigate();
  const [lesson, setLesson] = useState<LessonDetail | null>(null);
  const [step, setStep] = useState(0);
  const [results, setResults] = useState<Record<number, boolean>>({});
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLesson(null); setStep(0); setResults({}); setFinished(false);
    learnApi.lesson(lessonId).then(setLesson).catch((e: Error) => setError(e.message));
  }, [lessonId]);

  const sections = lesson?.sections ?? [];
  const section = sections[step];
  const tasks = sections.filter((s) => s.type === "challenge" || s.type === "quiz" || s.type === "drill").length;
  const solved = Object.values(results).filter(Boolean).length;

  const finish = useCallback(async () => {
    if (!lesson) return;
    const score = tasks ? Math.round((100 * solved) / tasks) : 100;
    setFinished(true);
    playSound("win");
    try { await learnApi.progress(lesson.id, true, score); } catch { /* offline */ }
  }, [lesson, tasks, solved]);

  const next = () => { if (step + 1 < sections.length) setStep(step + 1); else void finish(); };
  const onResult = (ok: boolean) => setResults((r) => ({ ...r, [step]: r[step] ?? ok }));

  if (error) return <div className="chip chip-danger">{error}</div>;
  if (!lesson) return <p className="faint">Loading lesson…</p>;
  if (finished) {
    return (
      <div className="card lesson-done" data-testid="lesson-done">
        <h2>Lesson complete</h2>
        <p className="muted">{tasks ? `${solved} of ${tasks} tasks solved on the first try.` : "Read and understood."}</p>
        <div className="row" style={{ justifyContent: "center", marginTop: 16 }}>
          <Link to="/learn" className="btn">Back to Learn</Link>
          {lesson.next && <Link to={`/learn/${lesson.next}`} className="btn btn-primary">Next lesson <ArrowRight size={14} /></Link>}
        </div>
      </div>
    );
  }

  return (
    <div className="lesson" data-testid="lesson">
      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <Link to="/learn" className="muted"><ArrowLeft size={14} /> Learn</Link>
          <div className="lesson-steps" aria-label="progress">{sections.map((_, i) => <i key={i} className={i < step ? "done" : i === step ? "current" : ""} />)}</div>
        </div>
        <SectionView key={`${lesson.id}-${step}`} section={section} onResult={onResult} onNext={next} isLast={step + 1 >= sections.length} />
      </div>
      <aside className="lesson-side">
        <div className="card">
          <div className="faint" style={{ textTransform: "uppercase", fontSize: 11, letterSpacing: "0.05em" }}>Band {lesson.band} · {lesson.strand}</div>
          <h2>{lesson.title}</h2>
          <p className="muted">{lesson.objective}</p>
          <div className="row" style={{ marginTop: 8 }}><span className="chip">{lesson.minutes} min</span><span className="chip">{tasks} tasks</span><span className="chip chip-ok">{solved} solved</span></div>
        </div>
        <div className="row">
          {lesson.prev && <button className="btn btn-sm" onClick={() => navigate(`/learn/${lesson.prev}`)}>← Previous lesson</button>}
          {lesson.next && <button className="btn btn-sm btn-ghost" onClick={() => navigate(`/learn/${lesson.next}`)}>Skip to next →</button>}
        </div>
      </aside>
    </div>
  );
}

function SectionView({ section, onResult, onNext, isLast }: { section: Section; onResult: (ok: boolean) => void; onNext: () => void; isLast: boolean }) {
  const nextLabel = isLast ? "Finish lesson" : "Continue";
  switch (section.type) {
    case "text":
      return (
        <div className="card stack">
          <Markdown md={section.md} />
          <div><button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button></div>
        </div>
      );
    case "position":
      return (
        <div className="stack">
          <Board fen={section.fen} orientation={section.orientation ?? "white"} shapes={(section.arrows ?? []).map((a) => ({ orig: a.from, dest: a.to, brush: a.brush }))} highlights={(section.highlights ?? []).map((h) => ({ square: h.square, brush: h.brush }))} />
          <div className="card"><p>{section.caption}</p><div style={{ marginTop: 10 }}><button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button></div></div>
        </div>
      );
    case "challenge":
      return <Challenge section={section} onResult={onResult} onNext={onNext} nextLabel={nextLabel} />;
    case "quiz":
      return <Quiz section={section} onResult={onResult} onNext={onNext} nextLabel={nextLabel} />;
    case "drill":
      return <Drill section={section} onResult={onResult} onNext={onNext} nextLabel={nextLabel} />;
    case "game":
      return <GameWalk section={section} onNext={onNext} nextLabel={nextLabel} />;
  }
}

function Challenge({ section, onResult, onNext, nextLabel }: { section: Extract<Section, { type: "challenge" }>; onResult: (ok: boolean) => void; onNext: () => void; nextLabel: string }) {
  const [fen, setFen] = useState(section.fen);
  const [index, setIndex] = useState(0);
  const [state, setState] = useState<TaskState>({ status: "idle", text: "", attempts: 0, hint: false });
  const [last, setLast] = useState<[Square, Square] | null>(null);
  const chess = useMemo(() => new Chess(fen), [fen]);
  const solverColor = new Chess(section.fen).turn();
  const over = state.status === "done" || state.status === "revealed";
  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (over) return;
    const c = new Chess(fen);
    const mv = safeMove(c, { from, to, promotion });
    if (!mv) return;
    const uci = from + to + (promotion ?? "");
    const expected = section.solution[index];
    const ok = section.accept_any_legal || (section.accept_any_check && c.inCheck()) || uci === expected || c.isCheckmate();
    if (ok) {
      playSound(soundForMove(mv, c));
      setLast([from, to]);
      const i = index + 1;
      if (i >= section.solution.length || c.isCheckmate() || section.accept_any_legal || section.accept_any_check) {
        setFen(c.fen()); setIndex(i); setState({ ...state, status: "done", text: section.explanation ?? "Correct." });
        playSound("correct");
        onResult(state.attempts === 0);
        return;
      }
      const reply = section.solution[i];
      setFen(c.fen()); setIndex(i);
      setTimeout(() => { const c2 = new Chess(c.fen()); const rm = safeMove(c2, reply); if (rm) playSound(soundForMove(rm, c2)); setFen(c2.fen()); setIndex(i + 1); setLast([reply.slice(0, 2), reply.slice(2, 4)]); }, 350);
    } else {
      playSound("wrong");
      setState({ ...state, status: "bad", attempts: state.attempts + 1, text: `${mv.san} is not it. Try again${section.hint ? " or take a hint" : ""}.` });
    }
  };
  // Giving up plays the rest of the solution on the board and does not count as solved.
  const reveal = () => {
    setState({ ...state, status: "revealed", text: section.explanation ?? "" });
    onResult(false);
    const c = new Chess(fen);
    section.solution.slice(index).forEach((uci, k) => {
      const mv = safeMove(c, uci);
      if (!mv) return;
      const sound = soundForMove(mv, c);
      const after = c.fen();
      setTimeout(() => { playSound(sound); setFen(after); setLast([uci.slice(0, 2), uci.slice(2, 4)]); }, 350 * k);
    });
  };
  const dests = useMemo(() => (over ? new Map() : destsFor(chess)), [chess, over]);
  const shapes: Shape[] = state.hint && !over ? [{ orig: section.solution[index].slice(0, 2), brush: "yellow" }] : [];
  return (
    <div className="stack">
      <Board fen={fen} orientation={section.orientation ?? (solverColor === "w" ? "white" : "black")} movable={{ color: chess.turn(), dests }} lastMove={last} check={checkSquare(chess)} shapes={shapes} onMove={onMove} />
      <div className="card stack">
        <strong data-testid="challenge-prompt">{section.prompt}</strong>
        {state.status === "bad" && <div className="task-banner bad" data-testid="task-bad">{state.text}</div>}
        {state.status === "done" && <div className="task-banner ok" data-testid="task-ok">Correct! {state.text} Solution: {section.solution_san.join(" ")}</div>}
        {state.status === "revealed" && <div className="task-banner" data-testid="task-revealed">The solution: {section.solution_san.join(" ")}. {state.text}</div>}
        <div className="row">
          {!over && section.hint && <button className="btn btn-sm" onClick={() => setState({ ...state, hint: true, attempts: state.attempts + 1, text: section.hint ?? "" , status: state.status === "idle" ? "bad" : state.status })}><Lightbulb size={14} /> Hint</button>}
          {!over && <button className="btn btn-sm btn-ghost" onClick={reveal}>Show solution</button>}
          {over && <button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button>}
        </div>
      </div>
    </div>
  );
}

function Quiz({ section, onResult, onNext, nextLabel }: { section: Extract<Section, { type: "quiz" }>; onResult: (ok: boolean) => void; onNext: () => void; nextLabel: string }) {
  const [picked, setPicked] = useState<number | null>(null);
  const right = picked === section.answer;
  return (
    <div className="stack">
      {section.fen && <Board fen={section.fen} orientation={new Chess(section.fen).turn() === "w" ? "white" : "black"} />}
      <div className="card stack">
        <strong data-testid="quiz-question">{section.question}</strong>
        <div className="quiz-options">
          {section.options.map((o, i) => (
            <button key={i} className={`btn ${picked !== null && i === section.answer ? "right" : picked === i ? "wrong" : ""}`} disabled={picked !== null} onClick={() => { setPicked(i); onResult(i === section.answer); playSound(i === section.answer ? "correct" : "wrong"); }} data-testid={`quiz-option-${i}`}>{o}</button>
          ))}
        </div>
        {picked !== null && <div className={`task-banner ${right ? "ok" : "bad"}`} data-testid={right ? "task-ok" : "task-bad"}>{right ? "Correct. " : "Not quite. "}{section.explanation}</div>}
        {picked !== null && <div><button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button></div>}
      </div>
    </div>
  );
}

function Drill({ section, onResult, onNext, nextLabel }: { section: Extract<Section, { type: "drill" }>; onResult: (ok: boolean) => void; onNext: () => void; nextLabel: string }) {
  const [outcome, setOutcome] = useState<DrillOutcome | null>(null);
  const [resetToken, setResetToken] = useState(0);
  return (
    <div className="stack">
      <DrillBoard fen={section.fen} goal={section.goal} maxMoves={section.max_moves} orientation={section.orientation} resetToken={resetToken} onOutcome={(o) => { setOutcome(o); onResult(o.result === "success"); }} />
      <div className="card stack">
        <strong data-testid="drill-prompt">{section.prompt}</strong>
        {section.tip && <div className="muted">{section.tip}</div>}
        <div className="row">
          <button className="btn btn-sm" onClick={() => { setOutcome(null); setResetToken((t) => t + 1); }}>Restart</button>
          {outcome && <button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button>}
          {!outcome && <button className="btn btn-sm btn-ghost" onClick={() => { onResult(false); onNext(); }}>Skip</button>}
        </div>
      </div>
    </div>
  );
}

function GameWalk({ section, onNext, nextLabel }: { section: Extract<Section, { type: "game" }>; onNext: () => void; nextLabel: string }) {
  const [ply, setPly] = useState(0);
  const fen = ply === 0 ? START_FEN : section.plies[ply - 1].fen;
  const cur = ply > 0 ? section.plies[ply - 1] : null;
  const note = section.notes?.[String(ply)];
  return (
    <div className="stack">
      <Board fen={fen} orientation="white" lastMove={cur ? [cur.uci.slice(0, 2), cur.uci.slice(2, 4)] : null} check={checkSquare(new Chess(fen))} />
      <div className="card stack">
        <strong>{section.title ?? `${section.headers.White ?? "?"} – ${section.headers.Black ?? "?"}`}</strong>
        <div className="row"><button className="btn btn-sm" onClick={() => setPly(Math.max(0, ply - 1))}>◀</button><span className="chip num">{cur ? `${Math.ceil(cur.ply / 2)}${cur.ply % 2 ? "." : "..."} ${cur.san}` : "start"}</span><button className="btn btn-sm" onClick={() => setPly(Math.min(section.plies.length, ply + 1))}>▶</button></div>
        {note && <Markdown md={note} />}
        {ply >= section.plies.length && <div><button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button></div>}
      </div>
    </div>
  );
}
