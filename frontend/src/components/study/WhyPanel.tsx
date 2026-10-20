import { Chess } from "chess.js";
import { StepBack, StepForward, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { safeMove, soundForMove } from "../../lib/chess/game";
import type { Square } from "../../lib/chess/types";
import { CLASS_LABEL } from "../../lib/review/classify";
import { readingTimeMs, speak, stopSpeech } from "../../lib/speech";
import { play as playSound } from "../../lib/sound";
import { spokenMove } from "../../lib/speech";
import type { Candidate, StudyPly } from "../../lib/studyApi";
import { CLASS_GLYPH } from "../play/MoveList";
import "./Study.css";

/** An alternative line played out on the board: the position before it, then one position per move. */
export interface Variation { label: string; fens: string[]; moves: [Square, Square][]; sans: string[]; at: number }

const VARIATION_STEP_MS = 900;

function variationOf(ply: StudyPly, c: Candidate): Variation {
  const chess = new Chess(ply.fen_before);
  const fens = [chess.fen()];
  const moves: [Square, Square][] = [];
  const sans: string[] = [];
  for (const san of c.line) {
    const mv = safeMove(chess, san);
    if (!mv) break;
    fens.push(chess.fen());
    moves.push([mv.from, mv.to]);
    sans.push(mv.san);
  }
  const better = !c.played && c.why_not === null;
  const label = better
    ? `Better was ${spokenMove(c.san)}${c.reasons[0] ? `, which ${c.reasons[0]}` : ""}.`
    : `If instead ${spokenMove(c.san)}: ${c.why_not ?? ""}.`;
  return { label, fens, moves, sans, at: 0 };
}

/** A variation that steps through its moves on its own, spoken once at the start; the caller shows its position. */
export function useVariation() {
  const [variation, setVariation] = useState<Variation | null>(null);
  useEffect(() => {
    if (!variation) return;
    if (variation.at === 0) void speak(variation.label);
    if (variation.at >= variation.moves.length) return;
    const t = window.setTimeout(() => {
      setVariation((v) => {
        if (!v) return v;
        const c = new Chess(v.fens[v.at]);
        const mv = safeMove(c, v.sans[v.at]);
        if (mv) playSound(soundForMove(mv, c));
        return { ...v, at: v.at + 1 };
      });
    }, variation.at === 0 ? Math.max(VARIATION_STEP_MS, readingTimeMs(variation.label) * 0.6) : VARIATION_STEP_MS);
    return () => window.clearTimeout(t);
  }, [variation]);
  const stop = () => { stopSpeech(); setVariation(null); };
  return {
    variation,
    fen: variation ? variation.fens[variation.at] : null,
    lastMove: (variation && variation.at > 0 ? variation.moves[variation.at - 1] : null) as [Square, Square] | null,
    start: (ply: StudyPly, c: Candidate) => { stopSpeech(); setVariation(variationOf(ply, c)); },
    step: (d: number) => setVariation((v) => (v ? { ...v, at: Math.max(0, Math.min(v.moves.length, v.at + d)) } : v)),
    stop,
  };
}

export function VariationBar({ v, onStep, onBack }: { v: Variation; onStep: (d: number) => void; onBack: () => void }) {
  return (
    <div className="why-variation" data-testid="variation">
      <p>{v.label}</p>
      <div className="why-variation-line">{v.sans.map((s, i) => <span key={i} className={i === v.at - 1 ? "now" : ""}>{s} </span>)}</div>
      <div className="row">
        <button className="btn btn-sm" onClick={() => onStep(-1)} disabled={v.at === 0}><StepBack size={14} /></button>
        <button className="btn btn-sm" onClick={() => onStep(1)} disabled={v.at >= v.moves.length}><StepForward size={14} /></button>
        <button className="btn btn-sm btn-ghost" onClick={onBack} data-testid="variation-back"><Undo2 size={14} /> Back to the game</button>
      </div>
    </div>
  );
}

const PROBLEM_LABEL: Partial<Record<StudyPly["classification"], string>> = { inaccuracy: "An inaccuracy", mistake: "A mistake", miss: "A missed chance", blunder: "A blunder" };

/** Why this move, why not the others: the engine's candidates with their stories, each one playable. */
export function WhyPanel({ ply, onVariation }: { ply: StudyPly; onVariation: (c: Candidate) => void }) {
  const alternatives = ply.candidates.filter((c) => !c.played);
  return (
    <div className={`why cls-${ply.classification}`} data-testid="why">
      <div className="why-head">
        <b>Why {ply.san}</b>
        <span className="cls-badge" title={CLASS_LABEL[ply.classification]}>{CLASS_GLYPH[ply.classification]}</span>
        <span className="faint">{CLASS_LABEL[ply.classification].toLowerCase()} · {ply.eval_after}</span>
        {ply.opening && <span className="faint">· {ply.opening}</span>}
      </div>
      <p data-testid="why-reasons">{ply.reasons.length ? ply.reasons.map((r) => r[0].toUpperCase() + r.slice(1)).join(". ") + "." : "A move the rules have no name for; the engine's lines below say what it is worth."}{ply.only_move ? " The only move." : ""}</p>
      {ply.problem && <p className="why-problem">{PROBLEM_LABEL[ply.classification] ?? "The problem"}: {ply.problem}.</p>}
      {ply.threat && <p className="why-threat">The threat was {ply.threat.san}{ply.threat.reason ? ` (${ply.threat.reason})` : ""}{ply.threat.line.length > 1 ? `: ${ply.threat.line.join(" ")}` : ""}.</p>}
      {alternatives.length > 0 && (
        <div className="why-alts">
          <span className="why-alts-title">Why not…</span>
          {alternatives.map((c) => {
            const better = c.why_not === null;
            return (
              <button key={c.uci} className={`why-alt ${better ? "better" : ""}`} onClick={() => onVariation(c)} data-testid="why-alt" title="Play this line on the board">
                <b>{c.san}</b>
                <span className="num faint">{c.eval}</span>
                <span className="faint">{better ? "better" : ""}</span>
                <span className="why-alt-text">{better ? `The engine prefers it${c.reasons[0] ? `: ${c.reasons[0]}` : ""}.` : c.why_not![0].toUpperCase() + c.why_not!.slice(1) + "."}</span>
                <span className="why-alt-line">{c.line.join(" ")}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
