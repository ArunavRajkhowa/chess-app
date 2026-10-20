import { ArrowRight, CheckCircle2, Circle, Play, RotateCcw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { learnApi, type Band, type LessonSummary, type Level } from "../lib/learnApi";
import "./Learn.css";

function Progress({ done, total }: { done: number; total: number }) {
  return <span className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}><i style={{ width: `${total ? (100 * done) / total : 0}%` }} /></span>;
}

const count = (lessons: LessonSummary[]) => ({ done: lessons.filter((l) => l.completed).length, total: lessons.length });
type Status = "all" | "todo" | "done";
type Sort = "order" | "short" | "tasks" | "title";
const SORTS: { key: Sort; label: string }[] = [{ key: "order", label: "Curriculum order" }, { key: "short", label: "Shortest first" }, { key: "tasks", label: "Most tasks" }, { key: "title", label: "Title A–Z" }];

export function LearnPage() {
  const [bands, setBands] = useState<Band[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [level, setLevel] = useState<Level | null>(null);
  const [reviewDue, setReviewDue] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [strand, setStrand] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("all");
  const [watchOnly, setWatchOnly] = useState(false);
  const [sort, setSort] = useState<Sort>("order");
  useEffect(() => { learnApi.curriculum().then((r) => { setBands(r.bands); setLevel(r.level); setReviewDue(r.review_due); }).catch((e: Error) => setError(e.message)); }, []);

  const lessons = useMemo(() => bands.flatMap((b) => b.modules.flatMap((m) => m.lessons.map((l) => ({ ...l, band: b.band, bandName: b.name, module: m.title })))), [bands]);
  // A player who has done nothing yet starts in the band their puzzle rating places them in, not at the rules.
  const started = lessons.some((l) => l.completed);
  const next = (started || !level ? null : lessons.find((l) => l.band === level.band && !l.completed)) ?? lessons.find((l) => !l.completed) ?? null;
  const band = bands.find((b) => b.band === (open ?? next?.band ?? 0)) ?? null;
  const strands = [...new Set(lessons.map((l) => l.strand))].map((s) => ({ strand: s, ...count(lessons.filter((l) => l.strand === s)) }));
  const total = count(lessons);

  // Filters and a sort turn the band tabs into one flat list of what was asked for.
  const filtering = q.trim() !== "" || strand !== null || status !== "all" || watchOnly || sort !== "order";
  const found = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = lessons.filter((l) =>
      (!needle || `${l.title} ${l.objective} ${l.module}`.toLowerCase().includes(needle))
      && (!strand || l.strand === strand)
      && (status === "all" || (status === "done") === l.completed)
      && (!watchOnly || l.watch));
    const by: Record<Sort, (a: typeof list[number], b: typeof list[number]) => number> = {
      order: () => 0, short: (a, b) => a.minutes - b.minutes, tasks: (a, b) => b.challenges - a.challenges, title: (a, b) => a.title.localeCompare(b.title),
    };
    return sort === "order" ? list : list.slice().sort(by[sort]);
  }, [lessons, q, strand, status, watchOnly, sort]);

  const row = (l: typeof lessons[number], withBand: boolean) => (
    <li key={l.id}>
      <Link to={`/learn/${l.id}`} className={`lesson-row ${l.id === next?.id ? "next" : ""}`} title={l.objective} data-testid={`lesson-${l.id}`}>
        {l.completed ? <CheckCircle2 size={16} className="ok" /> : <Circle size={16} className="faint" />}
        <span className="grow">{l.title}{withBand && <span className="faint"> · band {l.band} · {l.module}</span>}</span>
        {l.watch && <Play size={12} className="faint" aria-label="Narrated walkthrough" />}
        {l.score !== null && <span className="faint num">{Math.round(l.score)}%</span>}
        <span className="faint num">{l.minutes} min</span>
      </Link>
    </li>
  );

  return (
    <div className="stack" data-testid="learn">
      <div className="page-head">
        <div>
          <h1>Learn</h1>
          <p>From the rules to master level, one band at a time. Every lesson plays as a narrated video and stops only when it is your move.</p>
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
              <div className="faint">{reviewDue ? "Positions you missed, back for another go." : "What you miss in a lesson or a puzzle comes back the next day."}</div>
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

      {lessons.length > 0 && (
        <div className="learn-filters" data-testid="learn-filters">
          <label className="learn-search"><Search size={14} /><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search lessons: fork, opposition, castling…" data-testid="learn-search" /></label>
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value as Status)} aria-label="Status" data-testid="learn-status">
            <option value="all">All lessons</option><option value="todo">Not done yet</option><option value="done">Done</option>
          </select>
          <select className="select" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort" data-testid="learn-sort">
            {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <label className="row faint"><input type="checkbox" checked={watchOnly} onChange={(e) => setWatchOnly(e.target.checked)} /> narrated only</label>
          {filtering && <button className="btn btn-sm btn-ghost" onClick={() => { setQ(""); setStrand(null); setStatus("all"); setWatchOnly(false); setSort("order"); }} data-testid="learn-clear">Clear</button>}
        </div>
      )}

      {strands.length > 0 && (
        <div className="learn-topics" aria-label="Progress by topic">
          {strands.map((s) => (
            <button key={s.strand} className={`learn-topic ${strand === s.strand ? "on" : ""}`} onClick={() => setStrand(strand === s.strand ? null : s.strand)} data-testid={`strand-${s.strand.replace(/\s+/g, "-")}`}>
              <span className="learn-topic-name">{s.strand}</span>
              <Progress done={s.done} total={s.total} />
              <span className="faint num">{s.done}/{s.total}</span>
            </button>
          ))}
        </div>
      )}

      {filtering ? (
        <section className="card" data-testid="learn-results">
          <div className="card-title"><h3>{found.length} lesson{found.length === 1 ? "" : "s"}</h3><span className="faint">{strand ?? "all topics"} · {status === "all" ? "any status" : status === "done" ? "done" : "not done"}</span></div>
          {found.length ? <ol className="lessons">{found.map((l) => row(l, true))}</ol> : <p className="faint">Nothing matches. Clear a filter.</p>}
        </section>
      ) : (
        <>
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
                      <ol className="lessons">{m.lessons.map((l) => row({ ...l, band: band.band, bandName: band.name, module: m.title }, false))}</ol>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
