import { Chess } from "chess.js";
import { Lightbulb } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Board } from "../board/Board";
import type { Shape } from "../board/shapes";
import { ExplorePanel, useExplore } from "../explore/Explore";
import { checkSquare, destsFor, numberedSan, safeMove, soundForMove } from "../../lib/chess/game";
import { tryMove, type JudgedMove } from "../../lib/coach";
import type { PromotionPiece, Square } from "../../lib/chess/types";
import type { Section } from "../../lib/learnApi";
import { CLASS_LABEL } from "../../lib/review/classify";
import { play as playSound } from "../../lib/sound";

export type ChallengeSection = Extract<Section, { type: "challenge" }>;
export type QuizSection = Extract<Section, { type: "quiz" }>;
export interface StepProps { header: ReactNode; onNext: () => void; nextLabel: string }

export const sideOf = (fen: string): "white" | "black" => (new Chess(fen).turn() === "w" ? "white" : "black");

/** Board on the left, the lesson and the current step on the right, on every step. */
export function Stage({ board, header, children }: { board: ReactNode; header: ReactNode; children: ReactNode }) {
  return (
    <div className="lesson" data-testid="lesson">
      <div className="lesson-board">{board}</div>
      <aside className="lesson-side">
        {header}
        <div className="card stack">{children}</div>
      </aside>
    </div>
  );
}

type Status = "idle" | "bad" | "done" | "revealed";
/** A wrong move judged by the engine: what it is called, and the answer that punishes it. */
type Refutation = { san: string; judged: JudgedMove | null; fenAfter: string };

// The hint ladder a coach climbs: a nudge in words, then the piece, then its square. Each rung costs an attempt.
const HINT_RUNGS = 3;

/** Find the move: the learner plays it on the board. A wrong move is judged by the engine, which shows the reply that punishes it. */
export function Challenge({ section, onResult, header, onNext, nextLabel }: StepProps & { section: ChallengeSection; onResult: (ok: boolean) => void }) {
  const [fen, setFen] = useState(section.fen);
  const [index, setIndex] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [text, setText] = useState("");
  const [attempts, setAttempts] = useState(0);
  const [hints, setHints] = useState(0);
  const [refuted, setRefuted] = useState<Refutation | null>(null);
  const [last, setLast] = useState<[Square, Square] | null>(null);
  const [trying, setTrying] = useState(false);
  const explore = useExplore(section.fen, section.solution[0]); // after the task: why another first move is worse
  const chess = useMemo(() => new Chess(fen), [fen]);
  const solverColor = new Chess(section.fen).turn();
  const over = status === "done" || status === "revealed";
  const expected = section.solution[index];

  const finish = (c: Chess, i: number, note: string) => {
    setFen(c.fen()); setIndex(i); setStatus("done"); setText(note); setRefuted(null);
    playSound("correct");
    onResult(attempts === 0);
  };

  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (over) return;
    const c = new Chess(fen);
    const mv = safeMove(c, { from, to, promotion });
    if (!mv) return;
    const uci = from + to + (promotion ?? "");
    if (index === 0 && section.also?.includes(uci)) {
      playSound(soundForMove(mv, c));
      setLast([from, to]);
      finish(c, 1, `${mv.san} is just as good as the lesson's move. ${section.explanation ?? ""}`);
      return;
    }
    const ok = section.accept_any_legal || (section.accept_any_check && c.inCheck()) || uci === expected || c.isCheckmate();
    if (!ok) {
      playSound("wrong");
      setAttempts(attempts + 1);
      setStatus("bad");
      setText(`${mv.san} is not it.`);
      // A real coach does not stop at "wrong": the engine shows what the move runs into.
      const asked: Refutation = { san: mv.san, judged: null, fenAfter: c.fen() };
      setRefuted(asked);
      tryMove(fen, uci).then((v) => setRefuted((r) => (r?.san === mv.san && r.fenAfter === c.fen() ? { ...r, judged: v.tried } : r))).catch(() => undefined);
      return;
    }
    playSound(soundForMove(mv, c));
    setLast([from, to]);
    const i = index + 1;
    if (i >= section.solution.length || c.isCheckmate() || section.accept_any_legal || section.accept_any_check) {
      finish(c, i, section.explanation ?? "Correct.");
      return;
    }
    const reply = section.solution[i];
    setFen(c.fen()); setIndex(i); setRefuted(null); setStatus("idle"); setText("");
    setTimeout(() => { const c2 = new Chess(c.fen()); const rm = safeMove(c2, reply); if (rm) playSound(soundForMove(rm, c2)); setFen(c2.fen()); setIndex(i + 1); setLast([reply.slice(0, 2), reply.slice(2, 4)]); }, 350);
  };

  const hint = () => {
    const rung = hints + 1;
    setHints(rung); setAttempts(attempts + 1); setRefuted(null);
    if (status === "idle") setStatus("bad");
    setText(rung === 1 ? (section.hint ?? "Look at the piece that lights up.") : rung === 2 ? "The piece to move is marked." : "The piece and its square are marked.");
  };

  // Giving up plays the rest of the solution on the board and does not count as solved.
  const reveal = () => {
    setStatus("revealed"); setText(section.explanation ?? ""); setRefuted(null);
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
  const shapes: Shape[] = [];
  const highlights: { square: Square; brush: Shape["brush"] }[] = [];
  if (!over && hints >= 2) highlights.push({ square: expected.slice(0, 2), brush: "yellow" });
  if (!over && hints >= 3) highlights.push({ square: expected.slice(2, 4), brush: "yellow" });
  if (refuted?.judged) {
    shapes.push({ orig: refuted.judged.uci.slice(0, 2), dest: refuted.judged.uci.slice(2, 4), brush: "red" });
    const replyMove = safeMove(new Chess(refuted.fenAfter), refuted.judged.reply_line[0] ?? "");
    if (replyMove) shapes.push({ orig: replyMove.from, dest: replyMove.to, brush: "blue" });
  }
  const orientation = section.orientation ?? (solverColor === "w" ? "white" : "black");
  const board = trying
    ? <Board fen={explore.fen} orientation={orientation} movable={{ color: "both", dests: explore.dests }} lastMove={explore.lastMove} check={explore.check} onMove={explore.onMove} />
    : <Board fen={fen} orientation={orientation} movable={{ color: chess.turn(), dests }} lastMove={last} check={checkSquare(chess)} shapes={shapes} highlights={highlights} onMove={onMove} />;
  return (
    <Stage board={board} header={header}>
      <strong data-testid="challenge-prompt">{section.prompt}</strong>
      {status === "bad" && (
        <div className="task-banner bad" data-testid="task-bad">
          {text}
          {refuted && !refuted.judged && <span className="faint"> The engine is looking at it…</span>}
          {refuted?.judged && <RefutationText fen={fen} r={refuted.judged} />}
        </div>
      )}
      {status === "done" && <div className="task-banner ok" data-testid="task-ok">Correct! {text} Solution: {section.solution_san.join(" ")}</div>}
      {status === "revealed" && <div className="task-banner" data-testid="task-revealed">The solution: {section.solution_san.join(" ")}. {text}</div>}
      <div className="row" style={{ flexWrap: "wrap" }}>
        {!over && hints < HINT_RUNGS && <button className="btn btn-sm" onClick={hint} data-testid="hint"><Lightbulb size={14} /> Hint{hints ? ` ${hints + 1}` : ""}</button>}
        {!over && <button className="btn btn-sm btn-ghost" onClick={reveal}>Show solution</button>}
        {over && <button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button>}
        {over && !trying && <button className="btn btn-sm btn-ghost" onClick={() => setTrying(true)} data-testid="try-other">Try another first move</button>}
      </div>
      {trying && <ExplorePanel explore={explore} compareLabel="The lesson's move" idle={<p className="faint">Play any first move from the start position: the engine compares it with {section.solution_san[0]}.</p>} />}
    </Stage>
  );
}

function RefutationText({ fen, r }: { fen: string; r: JudgedMove }) {
  const label = CLASS_LABEL[r.classification].toLowerCase();
  const reply = r.reply_line.length ? ` After ${numberedSan(fen, [r.san])} the engine answers ${r.reply_text}.` : "";
  return <span data-testid="refutation"> The engine calls it {["a", "e", "i", "o", "u"].includes(label[0]) ? "an" : "a"} {label} ({r.eval_after}).{reply}</span>;
}

/** One question, several answers; the board shows the position it is about. */
export function Quiz({ section, fen, onResult, header, onNext, nextLabel }: StepProps & { section: QuizSection; fen: string; onResult: (ok: boolean) => void }) {
  const [picked, setPicked] = useState<number | null>(null);
  const right = picked === section.answer;
  return (
    <Stage board={<Board fen={fen} orientation={sideOf(fen)} />} header={header}>
      <strong data-testid="quiz-question">{section.question}</strong>
      <div className="quiz-options">
        {section.options.map((o, i) => (
          <button key={i} className={`btn ${picked !== null && i === section.answer ? "right" : picked === i ? "wrong" : ""}`} disabled={picked !== null} onClick={() => { setPicked(i); onResult(i === section.answer); playSound(i === section.answer ? "correct" : "wrong"); }} data-testid={`quiz-option-${i}`}>{o}</button>
        ))}
      </div>
      {picked !== null && <div className={`task-banner ${right ? "ok" : "bad"}`} data-testid={right ? "task-ok" : "task-bad"}>{right ? "Correct. " : "Not quite. "}{section.explanation}</div>}
      {picked !== null && <div><button className="btn btn-primary" onClick={onNext} data-testid="continue">{nextLabel}</button></div>}
    </Stage>
  );
}
