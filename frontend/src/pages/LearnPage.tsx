import { ArrowRight, CheckCircle2, Circle, Play, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { learnApi, type Band, type LessonSummary, type Level } from "../lib/learnApi";
import "./Learn.css";

function Progress({ done, total }: { done: number; total: number }) {
  return <span className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}><i style={{ width: `${total ? (100 * done) / total : 0}%` }} /></span>;
}

const count = (lessons: LessonSummary[]) => ({ done: lessons.filter((l) => l.completed).length, total: lessons.length });

export function LearnPage() {
  const [bands, setBands] = useState<Band[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [level, setLevel] = useState<Level | null>(null);
  const [reviewDue, setReviewDue] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { learnApi.curriculum().then((r) => { setBands(r.bands); setLevel(r.level); setReviewDue(r.review_due); }).catch((e: Error) => setError(e.message)); }, []);

  const lessons = bands.flatMap((b) => b.modules.flatMap((m) => m.lessons.map((l) => ({ ...l, band: b.band, module: m.title }))));
  // A player who has done nothing yet starts in the band their puzzle rating places them in, not at the rules.
  const started = lessons.some((l) => l.completed);
  const next = (started || !level ? null : lessons.find((l) => l.band === level.band && !l.completed)) ?? lessons.find((l) => !l.completed) ?? null;
  const band = bands.find((b) => b.band === (open ?? next?.band ?? 0)) ?? null;
  const strands = [...new Set(lessons.map((l) => l.strand))].map((s) => ({ strand: s, ...count(lessons.filter((l) => l.strand === s)) }));
  const total = count(lessons);

  return (
    <div className="stack" data-testid="learn">
      <div className="page-head">
        <div>
          <h1>Learn</h1>
          <p>From the rules to master level, one band at a time. Every lesson ends with puzzles that practise it.</p>
        </div>
        <div className="learn-total">
          <span className="faint">lessons done</span>
          <b className="num">{total.done} / {total.total}</b>
          <Progress {...total} />
        </div>
      </div>
      {error && <div className="chip chip-danger">{error}</div>}

      {next && (
        <Link to={`/learn/${next.id}`} className="card learn-next" data-testid="learn-next">
          <div className="grow">
            <div className="lesson-kicker">{total.done ? "Up next" : "Start here"} · band {next.band} · {next.module}</div>
            <h2>{next.title}</h2>
            <p className="muted">{next.objective}</p>
          </div>
          <span className="btn btn-primary">{total.done ? "Continue" : "Start"} <ArrowRight size={16} /></span>
        </Link>
      )}

      {bands.length > 0 && (
        <div className="learn-cards">
          <Link to="/learn/review" className={`card learn-card ${reviewDue ? "due" : ""}`} data-testid="learn-review">
            <RotateCcw size={18} />
            <div>
              <b>{reviewDue ? `${reviewDue} to review` : "Review"}</b>
              <div className="faint">{reviewDue ? "Positions you missed, back for another go." : "What you miss in a lesson comes back the next day."}</div>
            </div>
          </Link>
          <Link to="/puzzles" className="card learn-card" data-testid="learn-level">
            <span className="band-num num">{level ? level.band : "?"}</span>
            <div>
              <b>{level ? `Your level: ${bands[level.band]?.name ?? `band ${level.band}`}` : "Find your level"}</b>
              <div className="faint">{level ? `By your puzzle rating of ${level.puzzle_rating}. Lessons in this band should feel right.` : "Solve about ten rated puzzles and the curriculum places you."}</div>
            </div>
          </Link>
        </div>
      )}

      {strands.length > 0 && (
        <div className="learn-topics" aria-label="Progress by topic">
          {strands.map((s) => (
            <div key={s.strand} className="learn-topic">
              <span className="learn-topic-name">{s.strand}</span>
              <Progress done={s.done} total={s.total} />
              <span className="faint num">{s.done}/{s.total}</span>
            </div>
          ))}
        </div>
      )}

      <div className="band-tabs" role="tablist">
        {bands.map((b) => (
          <button key={b.band} role="tab" aria-selected={band?.band === b.band} className={`band-tab ${band?.band === b.band ? "on" : ""}`} onClick={() => setOpen(b.band)} data-testid={`band-${b.band}`}>
            <span className="band-tab-head"><b className="band-num num">{b.band}</b><b>{b.name}</b></span>
            <span className="faint">{b.rating}</span>
            <Progress done={b.lessons_done} total={b.lessons_total} />
            <span className="faint num">{b.lessons_done}/{b.lessons_total}</span>
          </button>
        ))}
      </div>

      {band && (
        <section className="band-panel" role="tabpanel">
          <div className="band-panel-head">
            <h2>Band {band.band} · {band.name}</h2>
            <span className="muted">{band.subtitle} · {band.rating}</span>
          </div>
          <div className="modules">
            {band.modules.map((m) => {
              const c = count(m.lessons);
              return (
                <div key={m.id} className={`card module ${c.done === c.total ? "complete" : ""}`}>
                  <div className="module-head"><span className="chip">{m.strand}</span><span className="faint num">{c.done}/{c.total}</span></div>
                  <h3>{m.title}</h3>
                  <Progress {...c} />
                  <p className="muted">{m.summary}</p>
                  <ol className="lessons">
                    {m.lessons.map((l) => (
                      <li key={l.id}>
                        <Link to={`/learn/${l.id}`} className={`lesson-row ${l.id === next?.id ? "next" : ""}`} title={l.objective} data-testid={`lesson-${l.id}`}>
                          {l.completed ? <CheckCircle2 size={16} className="ok" /> : <Circle size={16} className="faint" />}
                          <span className="grow">{l.title}</span>
                          {l.watch && <Play size={12} className="faint" aria-label="Narrated walkthrough" />}
                          {l.score !== null && <span className="faint num">{Math.round(l.score)}%</span>}
                          <span className="faint num">{l.minutes} min</span>
                        </Link>
                      </li>
                    ))}
                  </ol>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
