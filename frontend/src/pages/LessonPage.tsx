import { ArrowLeft, ArrowRight, Puzzle, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Board } from "../components/board/Board";
import { ExplorePanel, useExplore } from "../components/explore/Explore";
import { DrillBoard, type DrillOutcome } from "../components/learn/DrillBoard";
import { LecturePlayer, type Frame } from "../components/learn/LecturePlayer";
import { Challenge, Quiz, Stage, sideOf, type StepProps } from "../components/learn/Tasks";
import type { Brush, Shape } from "../components/board/shapes";
import { START_FEN, type Square } from "../lib/chess/types";
import { learnApi, type LessonDetail, type Section } from "../lib/learnApi";
import { Markdown } from "../lib/markdown";
import { play as playSound } from "../lib/sound";
import { speak, speechAvailable, spokenMove, stopSpeech } from "../lib/speech";
import { studyApi, useStudy, type StudyPly } from "../lib/studyApi";
import "./Learn.css";

const TRY_HINT = <p className="faint">Curious about another move? Play it on the board and the engine answers.</p>;
const TASK_TYPES = new Set(["challenge", "quiz"]); // the sections a miss brings back for review

/** The board a step without its own position shows: the nearest position after it, else before it. */
function contextFen(sections: Section[], step: number): string {
  const fenOf = (s: Section) => ("fen" in s && s.fen ? s.fen : s.type === "lecture" ? s.frames[0].fen : null);
  for (let i = step; i < sections.length; i++) { const f = fenOf(sections[i]); if (f) return f; }
  for (let i = step - 1; i >= 0; i--) { const f = fenOf(sections[i]); if (f) return f; }
  return START_FEN;
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

/** A lesson's model game with the engine's study: why every move, why not the others. */
function LessonGame({ lessonId, index, section, header, children }: { lessonId: string; index: number; section: Extract<Section, { type: "game" }>; header: ReactNode; children: ReactNode }) {
  const res = useStudy(() => studyApi.lesson(lessonId, index), `${lessonId}/${index}`);
  const note = !res ? "Loading the engine's study…" : res.status === "running" ? `The engine is studying this game: move ${res.progress.done} of ${res.progress.total}.` : res.status === "failed" ? `The study failed: ${res.error ?? "unknown error"}` : null;
  return <LecturePlayer frames={gameFrames(section, res?.study?.plies)} study={res?.study?.plies} studyNote={note} orientation="white" header={header}>{children}</LecturePlayer>;
}

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
  const missed = Object.entries(results).filter(([i, ok]) => !ok && TASK_TYPES.has(sections[Number(i)]?.type)).length;

  const finish = useCallback(async () => {
    if (!lesson) return;
    const score = tasks ? Math.round((100 * solved) / tasks) : 100;
    setFinished(true);
    playSound("win");
    const reviewable = Object.fromEntries(Object.entries(results).filter(([i]) => TASK_TYPES.has(lesson.sections[Number(i)]?.type)));
    try { await learnApi.progress(lesson.id, true, score, reviewable); } catch { /* offline */ }
  }, [lesson, tasks, solved, results]);

  const next = () => { if (step + 1 < sections.length) setStep(step + 1); else void finish(); };
  const onResult = (ok: boolean) => setResults((r) => ({ ...r, [step]: r[step] ?? ok }));

  if (error) return <div className="chip chip-danger">{error}</div>;
  if (!lesson) return <p className="faint">Loading lesson…</p>;
  if (finished) {
    return (
      <div className="card lesson-done" data-testid="lesson-done">
        <h2>Lesson complete</h2>
        <p className="muted">{tasks ? `${solved} of ${tasks} tasks solved on the first try.` : "Read and understood."}</p>
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
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Link to="/learn" className="muted"><ArrowLeft size={14} /> Learn</Link>
        <div className="row">
          {lesson.prev && <button className="btn btn-sm btn-ghost" onClick={() => navigate(`/learn/${lesson.prev}`)} aria-label="Previous lesson" title="Previous lesson"><ArrowLeft size={14} /></button>}
          {lesson.next && <button className="btn btn-sm btn-ghost" onClick={() => navigate(`/learn/${lesson.next}`)} aria-label="Next lesson" title="Next lesson"><ArrowRight size={14} /></button>}
        </div>
      </div>
      <div className="lesson-kicker">Band {lesson.band} · {lesson.strand}</div>
      <h2>{lesson.title}</h2>
      <p className="muted">{lesson.objective}</p>
      <div className="lesson-progress">
        <span className="progress"><i style={{ width: `${(100 * step) / sections.length}%` }} /></span>
        <span className="faint num">step {step + 1} of {sections.length}{tasks ? ` · ${solved}/${tasks} solved` : ""}</span>
      </div>
    </div>
  );
  return <SectionView key={`${lesson.id}-${step}`} lessonId={lesson.id} index={step} section={section} contextFen={contextFen(sections, step)} header={header} onResult={onResult} onNext={next} isLast={step + 1 >= sections.length} />;
}

function SectionView({ lessonId, index, section, contextFen, header, onResult, onNext, isLast }: { lessonId: string; index: number; section: Section; contextFen: string; header: ReactNode; onResult: (ok: boolean) => void; onNext: () => void; isLast: boolean }) {
  const step = { header, onNext, nextLabel: isLast ? "Finish lesson" : "Continue" };
  const continueButton = <div><button className="btn btn-primary" onClick={onNext} data-testid="continue">{step.nextLabel}</button></div>;
  switch (section.type) {
    case "text":
      return <Reading fen={contextFen} speech={plainText(section.md)} {...step}><Markdown md={section.md} /></Reading>;
    case "position":
      return (
        <Reading fen={section.fen} orientation={section.orientation} speech={section.caption ?? ""} shapes={(section.arrows ?? []).map((a) => ({ orig: a.from, dest: a.to, brush: a.brush }))} highlights={(section.highlights ?? []).map((h) => ({ square: h.square, brush: h.brush }))} {...step}>
          <p>{section.caption}</p>
        </Reading>
      );
    case "lecture":
      return <LecturePlayer frames={section.frames} orientation={section.orientation ?? sideOf(section.frames[0].fen)} header={header}>{continueButton}</LecturePlayer>;
    case "game":
      return <LessonGame lessonId={lessonId} index={index} section={section} header={header}>{continueButton}</LessonGame>;
    case "challenge":
      return <Challenge section={section} onResult={onResult} {...step} />;
    case "quiz":
      return <Quiz section={section} fen={section.fen ?? contextFen} onResult={onResult} {...step} />;
    case "drill":
      return <Drill section={section} onResult={onResult} {...step} />;
  }
}

/** The lesson's Markdown as words to say: no emphasis marks, no list markers. */
const plainText = (md: string) => md.replace(/[*`_]/g, "").replace(/^\s*(\d+\.|[-*])\s+/gm, "").replace(/\n+/g, " ");

/** Reads the step aloud; the narration setting decides whether the browser may speak at all. */
function Listen({ text }: { text: string }) {
  const [on, setOn] = useState(false);
  useEffect(() => () => stopSpeech(), []);
  if (!speechAvailable() || !text.trim()) return null;
  const toggle = () => {
    if (on) { stopSpeech(); setOn(false); return; }
    setOn(true);
    void speak(text).then(() => setOn(false));
  };
  return <button className="btn btn-sm btn-ghost" onClick={toggle} data-testid="listen">{on ? <VolumeX size={14} /> : <Volume2 size={14} />} {on ? "Stop" : "Listen"}</button>;
}

/** Text or a position to study; any move tried on the board is judged by the engine. */
function Reading({ fen, orientation, speech, shapes = [], highlights = [], header, onNext, nextLabel, children }: StepProps & { fen: string; orientation?: "white" | "black"; speech: string; shapes?: Shape[]; highlights?: { square: Square; brush: Brush }[]; children: ReactNode }) {
  const explore = useExplore(fen);
  const board = <Board fen={explore.fen} orientation={orientation ?? sideOf(fen)} movable={{ color: "both", dests: explore.dests }} lastMove={explore.lastMove} check={explore.check} shapes={explore.active ? [] : shapes} highlights={explore.active ? [] : highlights} onMove={explore.onMove} />;
  return (
    <Stage board={board} header={header}>
      {children}
      <div className="row">
        <button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button>
        <Listen text={speech} />
      </div>
      <ExplorePanel explore={explore} idle={TRY_HINT} />
    </Stage>
  );
}

function Drill({ section, onResult, header, onNext, nextLabel }: StepProps & { section: Extract<Section, { type: "drill" }>; onResult: (ok: boolean) => void }) {
  const [outcome, setOutcome] = useState<DrillOutcome | null>(null);
  const [resetToken, setResetToken] = useState(0);
  const board = <DrillBoard fen={section.fen} goal={section.goal} maxMoves={section.max_moves} orientation={section.orientation} resetToken={resetToken} onOutcome={(o) => { setOutcome(o); onResult(o.result === "success"); }} />;
  return (
    <Stage board={board} header={header}>
      <strong data-testid="drill-prompt">{section.prompt}</strong>
      {section.tip && <div className="muted">{section.tip}</div>}
      <div className="row">
        <button className="btn btn-sm" onClick={() => { setOutcome(null); setResetToken((t) => t + 1); }}>Restart</button>
        {outcome && <button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button>}
        {!outcome && <button className="btn btn-sm btn-ghost" onClick={() => { onResult(false); onNext(); }}>Skip</button>}
      </div>
    </Stage>
  );
}
