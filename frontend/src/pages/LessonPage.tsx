import { ArrowLeft, ArrowRight, Puzzle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DrillBoard, type DrillOutcome } from "../components/learn/DrillBoard";
import { LecturePlayer, type Frame } from "../components/learn/LecturePlayer";
import { Challenge, Quiz, Stage, sideOf, YourTurn, type StepProps } from "../components/learn/Tasks";
import type { Square } from "../lib/chess/types";
import { START_FEN } from "../lib/chess/types";
import { learnApi, type LessonDetail, type Section } from "../lib/learnApi";
import { prefetch, spokenMove } from "../lib/speech";
import { play as playSound } from "../lib/sound";
import { studyApi, useStudy, type StudyPly } from "../lib/studyApi";
import "./Learn.css";

const TASK_TYPES = new Set(["challenge", "quiz", "drill"]);
const REVIEWABLE = new Set(["challenge", "quiz"]); // the sections a miss brings back for review

/** A lesson plays as one video: the teaching sections run together and only a task stops the flow. */
type Step = { kind: "watch"; indices: number[]; game?: { index: number; section: Extract<Section, { type: "game" }> } } | { kind: "task"; index: number };

function stepsOf(sections: Section[]): Step[] {
  const steps: Step[] = [];
  for (let i = 0; i < sections.length; i++) {
    const s = sections[i];
    if (TASK_TYPES.has(s.type)) { steps.push({ kind: "task", index: i }); continue; }
    if (s.type === "game") { steps.push({ kind: "watch", indices: [i], game: { index: i, section: s } }); continue; }
    const last = steps[steps.length - 1];
    if (last && last.kind === "watch" && !last.game) last.indices.push(i);
    else steps.push({ kind: "watch", indices: [i] });
  }
  return steps;
}

/** The lesson's Markdown as words to say: no emphasis marks, no list markers. */
const plainText = (md: string) => md.replace(/[*`_]/g, "").replace(/^\s*(\d+\.|[-*])\s+/gm, "").replace(/\n+/g, " ").trim();
/** The squares a paragraph names light up while it is read. */
const namedSquares = (text: string): Square[] => [...new Set(text.match(/\b[a-h][1-8]\b/g) ?? [])].slice(0, 8);

/** A text section read paragraph by paragraph, each over the board the server chose for it. */
function textFrames(paragraphs: { md: string; fen: string }[]): Frame[] {
  return paragraphs.map((p) => ({ fen: p.fen, say: plainText(p.md) })).filter((f) => f.say).map((f) => ({ ...f, highlights: namedSquares(f.say).map((square) => ({ square, brush: "yellow" as const })) }));
}

/** A model game as a narrated walkthrough: every move spoken, the annotated ones in the author's words, the rest in the study's. */
function gameFrames(section: Extract<Section, { type: "game" }>, study: StudyPly[] | undefined): Frame[] {
  const title = section.title ?? `${section.headers.White ?? "White"} against ${section.headers.Black ?? "Black"}`;
  return [
    { fen: section.start_fen, say: `${title}. Watch how the game goes.` },
    ...section.plies.map((p, i) => {
      const move = p.ply % 2 ? `${Math.ceil(p.ply / 2)}. ${spokenMove(p.san)}` : spokenMove(p.san);
      const why = study?.[i]?.say;
      return { fen: p.fen, uci: p.uci, say: section.notes?.[String(p.ply)] ?? (why ? `${move}. ${why}` : move) };
    }),
  ];
}

function watchFrames(sections: Section[], step: Extract<Step, { kind: "watch" }>, study: StudyPly[] | undefined): Frame[] {
  const out: Frame[] = [];
  for (const i of step.indices) {
    const s = sections[i];
    if (s.type === "text") out.push(...textFrames(s.paragraphs));
    else if (s.type === "position") out.push({ fen: s.fen, say: s.caption ?? "", arrows: s.arrows, highlights: s.highlights });
    else if (s.type === "lecture") out.push(...s.frames);
    else if (s.type === "game") out.push(...gameFrames(s, study));
  }
  return out.filter((f) => f.say);
}

export function LessonPage() {
  const { lessonId = "" } = useParams();
  const navigate = useNavigate();
  const [lesson, setLesson] = useState<LessonDetail | null>(null);
  const [at, setAt] = useState(0);
  const [results, setResults] = useState<Record<number, boolean>>({});
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLesson(null); setAt(0); setResults({}); setFinished(false);
    learnApi.lesson(lessonId).then(setLesson).catch((e: Error) => setError(e.message));
  }, [lessonId]);

  const sections = useMemo(() => lesson?.sections ?? [], [lesson]);
  const steps = useMemo(() => stepsOf(sections), [sections]);
  const step = steps[at];
  const tasks = sections.filter((s) => TASK_TYPES.has(s.type)).length;
  const solved = Object.values(results).filter(Boolean).length;
  const missed = Object.entries(results).filter(([i, ok]) => !ok && REVIEWABLE.has(sections[Number(i)]?.type)).length;

  const finish = useCallback(async () => {
    if (!lesson) return;
    const score = tasks ? Math.round((100 * solved) / tasks) : 100;
    setFinished(true);
    playSound("win");
    const reviewable = Object.fromEntries(Object.entries(results).filter(([i]) => REVIEWABLE.has(lesson.sections[Number(i)]?.type)));
    try { await learnApi.progress(lesson.id, true, score, reviewable); } catch { /* offline */ }
  }, [lesson, tasks, solved, results]);

  const next = () => { if (at + 1 < steps.length) setAt(at + 1); else void finish(); };
  const onResult = (index: number, ok: boolean) => setResults((r) => ({ ...r, [index]: r[index] ?? ok }));

  if (error) return <div className="chip chip-danger">{error}</div>;
  if (!lesson || !step) return <p className="faint">Loading lesson…</p>;
  if (finished) {
    return (
      <div className="card lesson-done" data-testid="lesson-done">
        <h2>Lesson complete</h2>
        <p className="muted">{tasks ? `${solved} of ${tasks} tasks solved on the first try.` : "Watched and understood."}</p>
        {missed > 0 && <p className="muted" data-testid="lesson-review-note">{missed === 1 ? "The one you missed comes" : `The ${missed} you missed come`} back tomorrow in <Link to="/learn/review">Review</Link>.</p>}
        {lesson.practice.length > 0 && (
          <div className="lesson-practice">
            <p>Make it stick: solve puzzles that use what this lesson taught.</p>
            <div className="row" style={{ justifyContent: "center", flexWrap: "wrap" }}>
              {lesson.practice.map((t) => <Link key={t.key} to={`/puzzles?theme=${t.key}`} className="btn" data-testid={`practice-${t.key}`}><Puzzle size={14} /> {t.name} <span className="faint num">{t.count}</span></Link>)}
            </div>
          </div>
        )}
        <div className="row" style={{ justifyContent: "center", marginTop: 16 }}>
          <Link to="/learn" className="btn">Back to Learn</Link>
          {lesson.next && <Link to={`/learn/${lesson.next}`} className="btn btn-primary">Next lesson <ArrowRight size={14} /></Link>}
        </div>
      </div>
    );
  }

  const header = (
    <div className="lesson-head">
      <div className="row">
        <Link to="/learn" className="muted"><ArrowLeft size={14} /> Learn</Link>
        <span className="lesson-kicker grow">Band {lesson.band} · {lesson.strand}</span>
        <div className="row">
          {lesson.prev && <button className="btn btn-sm btn-ghost" onClick={() => navigate(`/learn/${lesson.prev}`)} aria-label="Previous lesson" title="Previous lesson"><ArrowLeft size={14} /></button>}
          {lesson.next && <button className="btn btn-sm btn-ghost" onClick={() => navigate(`/learn/${lesson.next}`)} aria-label="Next lesson" title="Next lesson"><ArrowRight size={14} /></button>}
        </div>
      </div>
      <h2>{lesson.title}</h2>
      <p className="muted">{lesson.objective}</p>
      <div className="lesson-progress">
        <span className="progress"><i style={{ width: `${(100 * at) / steps.length}%` }} /></span>
        <span className="faint num">part {at + 1} of {steps.length}{tasks ? ` · ${solved}/${tasks} solved` : ""}</span>
      </div>
    </div>
  );
  const isLast = at + 1 >= steps.length;
  const nextLabel = isLast ? "Finish lesson" : "Continue";
  if (step.kind === "watch") {
    return <Watch key={`${lesson.id}-${at}`} lessonId={lesson.id} sections={sections} step={step} header={header} onEnd={next} endLabel={isLast ? "Finish lesson" : steps[at + 1].kind === "task" ? "Your turn" : "Continue"} />;
  }
  const section = sections[step.index];
  const props: StepProps = { header, onNext: next, nextLabel };
  const report = (ok: boolean) => onResult(step.index, ok);
  switch (section.type) {
    case "challenge": return <Challenge key={`${lesson.id}-${at}`} section={section} onResult={report} {...props} />;
    case "quiz": return <Quiz key={`${lesson.id}-${at}`} section={section} fen={section.fen} onResult={report} {...props} />;
    case "drill": return <Drill key={`${lesson.id}-${at}`} section={section} onResult={report} {...props} />;
    default: return null;
  }
}

/** The teaching part of a lesson as one continuous narrated video; when it ends, the lesson moves on by itself. */
function Watch({ lessonId, sections, step, header, onEnd, endLabel }: { lessonId: string; sections: Section[]; step: Extract<Step, { kind: "watch" }>; header: ReactNode; onEnd: () => void; endLabel: string }) {
  const game = step.game;
  const res = useStudy(game ? () => studyApi.lesson(lessonId, game.index) : null, game ? `${lessonId}/${game.index}` : "");
  const frames = useMemo(() => watchFrames(sections, step, res?.study?.plies), [sections, step, res]);
  useEffect(() => { frames.slice(0, 3).forEach((f) => prefetch(f.say)); }, [frames]);
  const note = !game ? null : !res ? "Loading the engine's study…" : res.status === "running" ? `The engine is studying this game: move ${res.progress.done} of ${res.progress.total}.` : res.status === "failed" ? `The study failed: ${res.error ?? "unknown error"}` : null;
  const first = sections[step.indices[0]];
  const orientation = game ? "white" : "orientation" in first && first.orientation ? first.orientation : sideOf(frames[0]?.fen ?? START_FEN);
  if (!frames.length) return <Stage board={null} header={header}><button className="btn btn-primary" onClick={onEnd} data-testid="continue">{endLabel}</button></Stage>;
  return <LecturePlayer frames={frames} lessonId={lessonId} study={res?.study?.plies} studyNote={note} orientation={orientation} header={header} autoplay onEnd={onEnd} endLabel={endLabel} />;
}

function Drill({ section, onResult, header, onNext, nextLabel }: StepProps & { section: Extract<Section, { type: "drill" }>; onResult: (ok: boolean) => void }) {
  const [outcome, setOutcome] = useState<DrillOutcome | null>(null);
  const [resetToken, setResetToken] = useState(0);
  const board = <DrillBoard fen={section.fen} goal={section.goal} maxMoves={section.max_moves} orientation={section.orientation} resetToken={resetToken} onOutcome={(o) => { setOutcome(o); onResult(o.result === "success"); }} />;
  return (
    <Stage board={board} header={header}>
      <YourTurn fen={section.fen} prompt={section.prompt} kind="drill" />
      {section.tip && <div className="muted">{section.tip}</div>}
      <div className="row">
        <button className="btn btn-sm" onClick={() => { setOutcome(null); setResetToken((t) => t + 1); }}>Restart</button>
        {outcome && <button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button>}
        {!outcome && <button className="btn btn-sm btn-ghost" onClick={() => { onResult(false); onNext(); }}>Skip</button>}
      </div>
    </Stage>
  );
}
