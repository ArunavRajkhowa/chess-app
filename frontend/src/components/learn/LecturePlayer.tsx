import { Chess } from "chess.js";
import { Pause, Play, SkipForward, StepBack, StepForward, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Board } from "../board/Board";
import type { Shape } from "../board/shapes";
import { AskCoach, ExplorePanel, useExplore } from "../explore/Explore";
import { safeMove, soundForMove } from "../../lib/chess/game";
import type { Square } from "../../lib/chess/types";
import { prefetch, readingTimeMs, speak, stopSpeech } from "../../lib/speech";
import { play as playSound } from "../../lib/sound";
import type { Candidate, StudyPly } from "../../lib/studyApi";
import { useSettings } from "../../store/settings";
import { Assessment } from "../study/Assessment";
import { useVariation, VariationBar, WhyPanel } from "../study/WhyPanel";
import { Stage } from "./Tasks";
import "./Lecture.css";

/** One moment of a narrated walkthrough: the position to show, what to draw, and what to say. */
export interface Frame {
  fen: string;
  /** The move that led here from the previous frame, for the sound and the last-move highlight. */
  uci?: string;
  say: string;
  arrows?: { from: Square; to: Square; brush: Shape["brush"] }[];
  highlights?: { square: Square; brush: Shape["brush"] }[];
}

interface Props {
  frames: Frame[];
  orientation?: "white" | "black";
  header: ReactNode;
  /** Why each move was played and why not the others; `study[i]` belongs to `frames[i + 1]`. */
  study?: StudyPly[];
  studyNote?: string | null;
  /** The lesson this lecture belongs to: a question to the coach then carries it. */
  lessonId?: string;
  /** Starts playing on its own, like a video. */
  autoplay?: boolean;
  /** Called when the last frame has finished playing: the lesson moves on by itself. */
  onEnd?: () => void;
  endLabel?: string;
  /** Shown under the controls: a move list, mode buttons. */
  children?: ReactNode;
}

const PAUSE_AFTER_SPEECH_MS = 500;

/** The video of a chess lesson: the board plays the moves while the narration explains them. Pausing
 * makes the board live, so any move tried is judged by the engine, and the coach can be asked. With a
 * study, every move says why it was played and why not the others, and each alternative plays out. */
export function LecturePlayer({ frames, orientation = "white", header, study, studyNote, lessonId, autoplay = false, onEnd, endLabel = "Continue", children }: Props) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(autoplay);
  const [ended, setEnded] = useState(false);
  const narration = useSettings((s) => s.narration);
  const setSettings = useSettings((s) => s.set);
  const frame = frames[Math.min(index, frames.length - 1)];
  const ply = index > 0 ? study?.[index - 1] : undefined;
  const explore = useExplore(frame.fen);
  const variation = useVariation();
  const timer = useRef<number | undefined>(undefined);
  const last = index > 0 ? frames[index - 1] : null;

  // Play the frame: its move sound, then its narration; when the narration ends, the next frame.
  useEffect(() => {
    if (frame.uci && last) {
      const c = new Chess(last.fen);
      const mv = safeMove(c, frame.uci);
      if (mv) playSound(soundForMove(mv, c));
    }
    if (!playing) return;
    let live = true;
    if (index + 1 < frames.length) prefetch(frames[index + 1].say);
    void speak(frame.say).then((spoken) => {
      if (!live) return;
      const wait = spoken ? PAUSE_AFTER_SPEECH_MS : readingTimeMs(frame.say);
      timer.current = window.setTimeout(() => {
        if (!live) return;
        if (index + 1 < frames.length) setIndex(index + 1);
        else { setPlaying(false); setEnded(true); onEnd?.(); }
      }, wait);
    });
    return () => { live = false; window.clearTimeout(timer.current); stopSpeech(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a frame change or a play/pause is the whole trigger
  }, [index, playing]);

  useEffect(() => () => stopSpeech(), []);

  const go = (i: number) => { variation.stop(); setIndex(Math.max(0, Math.min(frames.length - 1, i))); };
  const toggle = () => {
    variation.stop();
    if (!playing && index === frames.length - 1) go(0);
    setPlaying((p) => !p);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement | null)?.tagName === "INPUT") return;
      if (e.key === " ") { e.preventDefault(); toggle(); }
      else if (e.key === "ArrowLeft") go(index - 1);
      else if (e.key === "ArrowRight") go(index + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const startVariation = (c: Candidate) => {
    if (!ply) return;
    setPlaying(false);
    explore.reset();
    variation.start(ply, c);
  };

  // A piece moved on the board pauses the lecture: the learner is asking "why not this?".
  const onMove: typeof explore.onMove = (from, to, promotion) => { setPlaying(false); variation.stop(); explore.onMove(from, to, promotion); };
  const inVariation = variation.variation !== null;
  const boardFen = variation.fen ?? explore.fen;
  const shapes: Shape[] = explore.active || inVariation ? [] : (frame.arrows ?? []).map((a) => ({ orig: a.from, dest: a.to, brush: a.brush }));
  const lastMove: [Square, Square] | null = inVariation ? variation.lastMove : explore.active ? explore.lastMove : frame.uci ? [frame.uci.slice(0, 2), frame.uci.slice(2, 4)] : null;
  const board = <Board fen={boardFen} orientation={orientation} movable={inVariation ? { color: "none", dests: new Map() } : { color: "both", dests: explore.dests }} lastMove={lastMove} check={inVariation ? null : explore.check} shapes={shapes} highlights={explore.active || inVariation ? [] : frame.highlights ?? []} onMove={onMove} />;

  return (
    <Stage board={board} header={header}>
      <div className="lecture" data-testid="lecture">
        <p className="lecture-caption" data-testid="lecture-caption" aria-live="polite">{frame.say}</p>
        <div className="row lecture-progress">
          <div className="lecture-bar grow" role="progressbar" aria-valuemin={1} aria-valuemax={frames.length} aria-valuenow={index + 1}>
            {frames.map((_, i) => <i key={i} className={i < index ? "seen" : i === index ? "now" : ""} onClick={() => go(i)} />)}
          </div>
          <span className="faint num">{index + 1} / {frames.length}</span>
        </div>
        <div className="row lecture-controls">
          <button className="btn btn-sm btn-ghost" onClick={() => go(index - 1)} disabled={index === 0} aria-label="Previous" title="Previous (←)"><StepBack size={15} /></button>
          <button className="btn btn-primary lecture-play" onClick={toggle} data-testid="lecture-play" aria-label={playing ? "Pause" : "Play"} title="Play or pause (space)">
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <button className="btn btn-sm btn-ghost" onClick={() => go(index + 1)} disabled={index + 1 >= frames.length} aria-label="Next" title="Next (→)" data-testid="lecture-next"><StepForward size={15} /></button>
          <button className="btn btn-sm btn-ghost" onClick={() => { setPlaying(false); go(frames.length - 1); }} aria-label="Skip to the end" title="Skip to the end" data-testid="lecture-end"><SkipForward size={15} /></button>
          <span className="grow" />
          <button className="btn btn-sm btn-ghost" onClick={() => setSettings({ narration: !narration })} aria-label={narration ? "Mute narration" : "Narration on"} title={narration ? "Mute narration" : "Narration on"}>
            {narration ? <Volume2 size={15} /> : <VolumeX size={15} />}
          </button>
        </div>
        {onEnd && !playing && (index + 1 >= frames.length || ended) && <div><button className="btn btn-primary" onClick={onEnd} data-testid="continue">{endLabel} <StepForward size={14} /></button></div>}
        {children}
        {variation.variation && <VariationBar v={variation.variation} onStep={variation.step} onBack={variation.stop} />}
        {ply && !inVariation && <WhyPanel ply={ply} onVariation={startVariation} />}
        {!ply && index > 0 && studyNote && <p className="faint" data-testid="study-note">{studyNote}</p>}
        <ExplorePanel explore={explore} compareLabel="The lecture's move" idle={<p className="faint">Wondering about another move? Pause and play it on the board: the engine answers. Or ask the coach below.</p>} />
        <AskCoach fen={explore.fen} lessonId={lessonId} />
        <Assessment fen={boardFen} />
      </div>
    </Stage>
  );
}
