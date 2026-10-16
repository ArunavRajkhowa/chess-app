import type { ReviewedMove } from "../../lib/api";
import { CLASS_LABEL } from "../../lib/review/classify";
import { CLASS_GLYPH } from "../play/MoveList";

interface Props {
  move: ReviewedMove | null;
  summary: string | null;
  explanation: string | null;
  explaining: boolean;
  onExplain: () => void;
  onRetry: () => void;
  onShowBest: () => void;
  onNext: () => void;
  canRetry: boolean;
  hasNext: boolean;
}

/** The coach's speech bubble for the current move, chess.com style. */
export function CoachPanel({ move, summary, explanation, explaining, onExplain, onRetry, onShowBest, onNext, canRetry, hasNext }: Props) {
  return (
    <div className="coachpanel" data-testid="coachpanel">
      <div className="coachpanel-avatar" aria-hidden="true">🎓</div>
      <div className="coachpanel-bubble">
        {move ? (
          <>
            <div className={`coachpanel-pill`}>
              <i className={`cls-badge cls-${move.classification}`}>{CLASS_GLYPH[move.classification]}</i>
              <span>{move.san} is {articleFor(move.classification)} {CLASS_LABEL[move.classification].toLowerCase()}</span>
            </div>
            <span>{move.note}</span>
            {move.classification !== "best" && move.classification !== "book" && move.classification !== "forced" && move.best_line_san.length > 0 && (
              <span className="muted">Best was <b>{move.best_move_san}</b> ({move.best_eval_text}): {move.best_line_san.join(" ")}</span>
            )}
            {explanation && <p className="coach-explanation" data-testid="explanation">{explanation}</p>}
            <div className="row" style={{ flexWrap: "wrap" }}>
              <button className="btn btn-sm" onClick={onExplain} disabled={explaining} data-testid="explain-btn">{explaining ? "Thinking…" : "Explain"}</button>
              {canRetry && <button className="btn btn-sm" onClick={onRetry} data-testid="retry-btn">Retry</button>}
              <button className="btn btn-sm btn-ghost" onClick={onShowBest}>Show best</button>
              {hasNext && <button className="btn btn-sm btn-primary" onClick={onNext} data-testid="next-key">Next key moment</button>}
            </div>
          </>
        ) : (
          <>
            <span>{summary ?? "Start of the game. Step through the moves or jump to a key moment."}</span>
            {hasNext && <div><button className="btn btn-sm btn-primary" onClick={onNext} data-testid="next-key">Start review</button></div>}
          </>
        )}
      </div>
    </div>
  );
}

function articleFor(c: string): string {
  return ["inaccuracy", "excellent"].includes(c) ? "an" : c === "best" || c === "great" || c === "book" || c === "good" || c === "forced" ? "the" : "a";
}
