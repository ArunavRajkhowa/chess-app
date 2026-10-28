import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyArt } from "../components/art";
import { Challenge, Quiz } from "../components/learn/Tasks";
import { learnApi, type ReviewItem } from "../lib/learnApi";
import { puzzleApi } from "../lib/puzzleApi";
import { play as playSound } from "../lib/sound";
import "./Learn.css";

/** The tasks missed in lessons, back for another go on the spaced ladder: a day, then three, a week, and on. */
export function LearnReviewPage() {
  const [queue, setQueue] = useState<{ items: ReviewItem[]; later: number; next_due_at: string | null } | null>(null);
  const [puzzles, setPuzzles] = useState<{ due: number; later: number } | null>(null);
  const [at, setAt] = useState(0);
  const [solved, setSolved] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    learnApi.review().then(setQueue).catch((e: Error) => setError(e.message));
    puzzleApi.review().then((r) => setPuzzles({ due: r.due, later: r.later })).catch(() => undefined);
  }, []);

  if (error) return <div className="chip chip-danger">{error}</div>;
  if (!queue) return <p className="faint">Loading your review…</p>;
  const item = queue.items[at];
  if (!item) {
    const done = queue.items.length;
    return (
      <div className="card lesson-done" data-testid="review-done">
        {!done && <EmptyArt kind="puzzles" className="lesson-done-art" />}
        <h2>{done ? "Review done" : "Nothing due"}</h2>
        <p className="muted">
          {done
            ? `${solved} of ${done} solved. Each one you solve comes back after a longer gap; a miss brings it back tomorrow.`
            : queue.later
              ? `${queue.later} position${queue.later === 1 ? "" : "s"} waiting; the next is due ${new Date(queue.next_due_at + "Z").toLocaleDateString()}.`
              : "A challenge or quiz you miss in a lesson comes back here the next day. Nothing is queued yet."}
        </p>
        {puzzles && puzzles.due > 0 && (
          <p className="muted" data-testid="review-puzzles">{puzzles.due} puzzle{puzzles.due === 1 ? "" : "s"} you missed before {puzzles.due === 1 ? "is" : "are"} due as well.</p>
        )}
        <div className="row" style={{ justifyContent: "center", marginTop: 16 }}>
          {puzzles && puzzles.due > 0 && <Link to="/puzzles?review=1" className="btn btn-primary">Review the puzzles <ArrowRight size={14} /></Link>}
          <Link to="/learn" className={`btn ${puzzles && puzzles.due > 0 ? "" : "btn-primary"}`}>Back to Learn <ArrowRight size={14} /></Link>
        </div>
      </div>
    );
  }
  const onResult = (ok: boolean) => {
    if (ok) setSolved((n) => n + 1);
    learnApi.reviewResult(item.lesson_id, item.section_index, ok).catch(() => undefined);
  };
  const next = () => { if (at + 1 >= queue.items.length) playSound("win"); setAt(at + 1); };
  const header = (
    <div className="lesson-head">
      <Link to="/learn" className="muted"><ArrowLeft size={14} /> Learn</Link>
      <div className="lesson-kicker">Review · from <Link to={`/learn/${item.lesson_id}`}>{item.lesson_title}</Link></div>
      <h2>Missed before. Again?</h2>
      <div className="lesson-progress">
        <span className="progress"><i style={{ width: `${(100 * at) / queue.items.length}%` }} /></span>
        <span className="faint num">{at + 1} of {queue.items.length}</span>
      </div>
    </div>
  );
  const step = { header, onNext: next, nextLabel: at + 1 >= queue.items.length ? "Finish review" : "Next" };
  const key = `${item.lesson_id}-${item.section_index}`;
  return item.section.type === "quiz"
    ? <Quiz key={key} section={item.section} fen={item.section.fen} onResult={onResult} {...step} />
    : <Challenge key={key} section={item.section} onResult={onResult} {...step} />;
}
