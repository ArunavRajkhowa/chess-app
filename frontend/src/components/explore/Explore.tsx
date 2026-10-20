import { Chess } from "chess.js";
import { Send, Undo2 } from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { streamCoach, tryMove, type JudgedMove } from "../../lib/coach";
import { checkSquare, destsFor, numberedSan, safeMove, soundForMove } from "../../lib/chess/game";
import { Markdown } from "../../lib/markdown";
import type { PromotionPiece, Square } from "../../lib/chess/types";
import { CLASS_LABEL } from "../../lib/review/classify";
import { play as playSound } from "../../lib/sound";
import { CLASS_GLYPH } from "../play/MoveList";
import "./Explore.css";

type Verdict = { tried: JudgedMove; compare: JudgedMove | null };
interface State { base: string; line: string[]; judged: number; verdict: Verdict | null; busy: boolean; error: string | null }

const fresh = (base: string): State => ({ base, line: [], judged: 0, verdict: null, busy: false, error: null });

export interface Explore {
  active: boolean;
  /** The position to show: the base position, or the end of the tried line. */
  fen: string;
  lastMove: [Square, Square] | null;
  check: Square | null;
  dests: Map<Square, Square[]>;
  onMove: (from: Square, to: Square, promotion?: PromotionPiece) => void;
  reset: () => void;
  verdict: Verdict | null;
  /** The position the judged move was played from. */
  judgedFen: string;
  busy: boolean;
  error: string | null;
  /** The next move of the engine's answer that is not on the board yet. */
  nextReply: string | null;
  playReply: () => void;
}

/** "Why not this move?": a move tried from `baseFen` is judged by the engine, which then shows its answer.
 * `compare` (UCI) is judged too when the first move is tried: the game move or the lesson's move. */
export function useExplore(baseFen: string, compare?: string): Explore {
  const [state, setState] = useState<State>(() => fresh(baseFen));
  const request = useRef(0);
  const s = state.base === baseFen ? state : fresh(baseFen);
  if (state.base !== baseFen) setState(s); // a new base position ends the exploration

  const fens = useMemo(() => {
    const c = new Chess(s.base);
    return [c.fen(), ...s.line.map((uci) => { safeMove(c, uci); return c.fen(); })];
  }, [s.base, s.line]);
  const fen = fens[fens.length - 1];
  const chess = useMemo(() => new Chess(fen), [fen]);
  const dests = useMemo(() => destsFor(chess), [chess]);
  const last = s.line[s.line.length - 1];

  const push = (uci: string) => {
    const c = new Chess(fen);
    const mv = safeMove(c, uci);
    if (mv) playSound(soundForMove(mv, c));
    return mv?.lan ?? null;
  };

  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    const c = new Chess(fen);
    const mv = safeMove(c, { from, to, promotion });
    if (!mv) return;
    playSound(soundForMove(mv, c));
    const line = [...s.line, mv.lan];
    const id = ++request.current;
    setState({ ...s, line, judged: line.length, verdict: null, busy: true, error: null });
    tryMove(fen, mv.lan, s.line.length === 0 ? compare : undefined)
      .then((verdict) => { if (id === request.current) setState((cur) => ({ ...cur, verdict, busy: false })); })
      .catch((e: Error) => { if (id === request.current) setState((cur) => ({ ...cur, busy: false, error: e.message })); });
  };

  const replyIndex = s.line.length - s.judged;
  const nextReply = s.verdict?.tried.reply_line[replyIndex] ?? null;
  const playReply = () => {
    if (!nextReply) return;
    const lan = push(nextReply);
    if (lan) setState({ ...s, line: [...s.line, lan] });
  };

  return {
    active: s.line.length > 0, fen, check: checkSquare(chess), dests,
    lastMove: last ? [last.slice(0, 2) as Square, last.slice(2, 4) as Square] : null,
    onMove, reset: () => { request.current++; setState(fresh(baseFen)); },
    verdict: s.verdict, judgedFen: fens[Math.max(0, s.judged - 1)], busy: s.busy, error: s.error, nextReply, playReply,
  };
}

const materialWords = (balance: number) =>
  balance === 0 ? "material is level" : `${balance > 0 ? "White" : "Black"} is ${Math.abs(balance)} pawn${Math.abs(balance) === 1 ? "" : "s"} ahead`;

function Judged({ j, fen }: { j: JudgedMove; fen: string }) {
  return (
    <span className={`explore-judged cls-${j.classification}`}>
      <i className="cls-badge">{CLASS_GLYPH[j.classification]}</i>
      <b>{numberedSan(fen, [j.san])}</b>
      <span>{CLASS_LABEL[j.classification].toLowerCase()}</span>
      <span className="chip num">{j.eval_after}</span>
    </span>
  );
}

/** The verdict on the tried move. `idle` shows while nothing is being tried. */
export function ExplorePanel({ explore, compareLabel = "The game move", idle }: { explore: Explore; compareLabel?: string; idle?: ReactNode }) {
  if (!explore.active) return <>{idle}</>;
  const v = explore.verdict;
  return (
    <div className="explore" data-testid="explore">
      <div className="row explore-head">
        <span className="faint">Your try</span>
        <button className="btn btn-sm btn-ghost" onClick={explore.reset} data-testid="explore-back"><Undo2 size={14} /> Back</button>
      </div>
      {explore.busy && <p className="faint">The engine is looking…</p>}
      {explore.error && <span className="chip chip-danger">{explore.error}</span>}
      {v && (
        <>
          <Judged j={v.tried} fen={explore.judgedFen} />
          <p className="muted" data-testid="explore-verdict">{v.tried.explanation}</p>
          {v.tried.opening && <p className="faint">Book: {v.tried.opening.eco} {v.tried.opening.name}</p>}
          {v.tried.reply_text && <p className="faint">The engine's answer: {v.tried.reply_text}. After it {materialWords(v.tried.material_after_reply)}.</p>}
          {explore.nextReply && <div><button className="btn btn-sm" onClick={explore.playReply} data-testid="explore-reply">Play {explore.nextReply}</button></div>}
          {v.compare && <div className="explore-compare"><span className="faint">{compareLabel}</span><Judged j={v.compare} fen={explore.judgedFen} /></div>}
        </>
      )}
    </div>
  );
}

/** A free question about the position on the board, answered by the coach from the engine's facts. */
export function AskCoach({ fen }: { fen: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ fen: string; text: string; busy: boolean } | null>(null);
  const ask = async () => {
    const q = question.trim();
    if (!q || answer?.busy) return;
    setAnswer({ fen, text: "", busy: true });
    try {
      await streamCoach("/api/coach/chat", { fen, question: q }, (chunk) => setAnswer((a) => (a ? { ...a, text: a.text + chunk } : a)));
      setAnswer((a) => (a ? { ...a, busy: false } : a));
    } catch (e) {
      setAnswer({ fen, text: `The coach is not available: ${e instanceof Error ? e.message : String(e)}`, busy: false });
    }
  };
  return (
    <div className="ask-coach">
      <form className="row" onSubmit={(e) => { e.preventDefault(); void ask(); }}>
        <input className="input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about this position, e.g. why not Nxe4?" data-testid="ask-coach-input" />
        <button className="btn btn-sm" type="submit" disabled={!question.trim() || answer?.busy} aria-label="Ask"><Send size={14} /></button>
      </form>
      {answer && answer.fen === fen && <div className="ask-coach-answer" data-testid="ask-coach-answer">{answer.text ? <Markdown md={answer.text} /> : "Thinking…"}</div>}
    </div>
  );
}
