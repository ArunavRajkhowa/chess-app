import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Board } from "../components/board/Board";
import { CLASS_GLYPH } from "../components/play/MoveList";
import type { Square } from "../lib/chess/types";
import { insightsApi, type Example, type Insights, type PlanItem, type Resource } from "../lib/insightsApi";
import { planApi } from "../lib/planApi";
import "./Insights.css";

const VIEW_ONLY = { color: "none" as const, dests: new Map() };
const ARROW = { up: "↑", down: "↓", flat: "→" } as const;
const sq = (uci: string) => [uci.slice(0, 2) as Square, uci.slice(2, 4) as Square] as const;

/** The player's own position on a small board: the move played in red, the better move in green. */
function Worked({ ex }: { ex: Example }) {
  const [pf, pt] = sq(ex.played_uci);
  const [bf, bt] = sq(ex.best_uci);
  const same = ex.played_uci === ex.best_uci;
  return (
    <div className="worked">
      <div className="worked-board">
        <Board fen={ex.fen} orientation={ex.color} movable={VIEW_ONLY} showCoordinates={false} animate={false}
               shapes={same ? [{ orig: bf, dest: bt, brush: "green" }] : [{ orig: pf, dest: pt, brush: "red" }, { orig: bf, dest: bt, brush: "green" }]} />
      </div>
      <div className="worked-text">
        <div className="faint">Your game against {ex.opponent}, move {ex.move_number}</div>
        <div><i className={`cls-badge cls-${ex.classification}`}>{CLASS_GLYPH[ex.classification]}</i> You played <b>{ex.played_san}</b>{!same && <> · better was <b>{ex.best_san}</b></>}</div>
        {ex.drop > 0 && <div className="faint">−{ex.drop}% win chance · line {ex.best_line.slice(0, 4).join(" ")}</div>}
        <Link to={`/review/${ex.game_id}`} className="faint">Open the review</Link>
      </div>
    </div>
  );
}

function Go({ r, primary = false }: { r: Resource | null | undefined; primary?: boolean }) {
  if (!r) return null;
  const range = r.rating_min !== undefined ? ` · ${r.rating_min}–${r.rating_max}` : "";
  return <Link to={r.href} className={`btn btn-sm ${primary ? "btn-primary" : ""}`} title={r.reason}>{r.title}{r.line ? ` · ${r.line}` : ""}{range}</Link>;
}

/** One section: the finding, its worked example, the actions; or what would unlock it. */
function Section({ title, finding, absent, ex, actions, children }: { title: string; finding: string | null; absent: string | null; ex?: Example | null; actions: (Resource | null | undefined)[]; children?: React.ReactNode }) {
  return (
    <section className="card ins-section">
      <div className="card-title"><h3>{title}</h3></div>
      {finding ? <p className="ins-finding">{finding}</p> : <p className="faint">{absent ?? "Nothing stands out here yet."}</p>}
      {ex && <Worked ex={ex} />}
      {children}
      {actions.some(Boolean) && <div className="ins-actions">{actions.map((a, i) => <Go key={i} r={a} primary={i === 0} />)}</div>}
    </section>
  );
}

const more = (n: number, what: string) => (n > 0 ? `${n} more ${what} will show this.` : null);

export function InsightsPage() {
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const navigate = useNavigate();
  useEffect(() => { insightsApi.me().then(setData).catch((e: Error) => setError(e.message)); }, []);
  if (error) return <p className="faint">Insights could not load: {error}</p>;
  if (!data) return <p className="faint">Loading…</p>;
  if (!data.games || !data.sections) return <div className="stack"><div className="page-head"><div><h1>Insights</h1><p>{data.message}</p></div></div><Link to="/play" className="btn btn-primary" style={{ width: "fit-content" }}>Play a game</Link></div>;

  const { openings: op, middlegame: mg, endgames: eg, quality: q, tactics: tc, strengths } = data.sections;
  const focus = data.focus;
  const trend = data.trend;
  const makePlan = async (item: PlanItem) => {
    setPlanning(true);
    setPlanError(null);
    try {
      const r = await planApi.create(item.plan_goal);
      if (r.plan) navigate(`/plan/${r.plan.id}`);
      else setPlanError(r.message ?? "No plan matches that goal.");
    } catch (e) {
      setPlanError(`The plan could not be made: ${(e as Error).message}`);
    } finally {
      setPlanning(false);
    }
  };
  const acc = data.accuracy;
  const w = 600, h = 100;
  const pts = (acc?.timeline ?? []).map((t, i, all) => `${(i / Math.max(1, all.length - 1)) * w},${h - (t.accuracy / 100) * h}`).join(" ");

  return (
    <div className="stack" data-testid="insights">
      <div className="page-head"><div><h1>Insights</h1><p>{data.games} reviewed games against bots. Every finding below is one of your own positions.</p></div></div>

      <section className="card ins-headline">
        <div className="ins-stats">
          <div><div className="faint">Level</div><b>{data.level ? `${data.level.name} · ${data.level.rating}` : "–"}</b><div className="faint">{data.level ? `from your ${data.level.source}` : data.level_hint}</div></div>
          <div><div className="faint">Accuracy, last {q.recent?.games ?? 0}</div><b className="num">{q.recent?.accuracy ?? "–"} {trend?.direction && <span className={`trend-${trend.direction}`}>{ARROW[trend.direction]} {trend.delta}</span>}</b><div className="faint">{trend?.direction ? "against the ten games before" : more(trend?.needs ?? 0, "reviewed games")}</div></div>
          <div><div className="faint">Blunders per game</div><b className="num">{q.recent?.blunders_per_game ?? "–"}</b><div className="faint">misses {q.recent?.misses_per_game ?? "–"}</div></div>
        </div>
        {focus ? (
          <div className="ins-focus">
            <div className="faint">This week, fix one thing</div>
            <h2>{focus.goal}</h2>
            <p className="muted">{focus.why}</p>
            {focus.example && <Worked ex={focus.example} />}
            <div className="ins-actions"><Go r={focus.action} primary />{focus.also.map((a) => <Go key={a.id} r={a} />)}
              <button className="btn btn-sm" disabled={planning} onClick={() => void makePlan(focus)}>Make this my plan</button></div>
            {planError && <p className="faint">{planError}</p>}
          </div>
        ) : <p className="faint">No weakness costs you a measurable share of games yet. Keep reviewing games.</p>}
      </section>

      {data.plan && data.plan.length > 1 && (
        <section className="card">
          <div className="card-title"><h3>Your week</h3><span className="faint">biggest win-chance loss per game first</span></div>
          <ol className="ins-plan">
            {data.plan.map((p) => (
              <li key={p.rank}><div><b>{p.goal}</b> <span className="faint">−{p.gain_per_game}% per game</span><div className="muted">{p.why}</div></div><Go r={p.action} /></li>
            ))}
          </ol>
        </section>
      )}

      <Section title="Openings" finding={op.finding} absent={more(op.needs, "games in one opening")} ex={op.repeated[0]?.example ?? op.rows[0]?.leave_book?.example} actions={[op.action, op.bot]}>
        {op.rows.length > 0 && (
          <table className="games-table">
            <thead><tr><th>Opening</th><th>Games</th><th>Score</th><th>Accuracy</th><th>Leave book</th><th>First mistake</th></tr></thead>
            <tbody>{op.rows.map((o) => (
              <tr key={`${o.name}-${o.color}`}>
                <td>{o.eco && <span className="chip">{o.eco}</span>} {o.name} <span className="faint">as {o.color}</span>{o.course && <> · <Link to={o.course.href}>course</Link></>}</td>
                <td className="num">{o.games}</td><td className="num">{o.score}%</td><td className="num">{o.accuracy ?? "–"}</td>
                <td className="num">{o.leave_book ? `move ${Math.round(o.leave_book.move_number)}${o.leave_book.costly ? ` · ${o.leave_book.costly} costly` : ""}` : "–"}</td>
                <td className="num">{o.first_mistake_move !== null ? `move ${o.first_mistake_move}` : "–"}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </Section>

      <Section title="Middlegame" finding={mg.finding} absent={more(mg.needs, "games that reach the middlegame")} ex={mg.errors.plan.example ?? mg.errors.tactic.example} actions={[mg.action, mg.watch, mg.bot]}>
        {mg.imbalances.length > 0 && (
          <ul className="ins-list">{mg.imbalances.map((r) => <li key={`${r.kind}-${r.mine}`}><span>{r.mine ? "You have" : "Opponent has"} <b>{r.kind}</b></span><span className="num">{r.score}% over {r.games}</span>{r.watch && <Link to={r.watch.href} className="faint">watch {r.watch.title}</Link>}</li>)}</ul>
        )}
        {mg.mobility && mg.mobility.mean_diff !== null && <p className="faint">At move 20 your pieces have {Math.abs(mg.mobility.mean_diff)} {mg.mobility.mean_diff >= 0 ? "more" : "fewer"} legal moves than the opponent's, on average over {mg.mobility.games} games.</p>}
      </Section>

      <Section title="Endgames" finding={eg.finding} absent={more(eg.needs, "games that reach an endgame")} ex={eg.conversion?.example} actions={[eg.action, eg.lesson, eg.bot]}>
        {(eg.conversion || eg.hold) && (
          <div className="ins-stats">
            <div><div className="faint">Winning endgames converted</div><b className="num">{eg.conversion ? `${eg.conversion.won} / ${eg.conversion.games}` : "–"}</b></div>
            <div><div className="faint">Worse endgames held</div><b className="num">{eg.hold ? `${eg.hold.held} / ${eg.hold.games}` : "–"}</b></div>
          </div>
        )}
        {eg.types.length > 0 && <ul className="ins-list">{eg.types.map((t) => <li key={t.type}><span>{t.name}</span><span className="num">{t.wins} / {t.draws} / {t.losses}</span><span className="faint">accuracy {t.accuracy ?? "–"}</span></li>)}</ul>}
      </Section>

      <Section title="Move quality" finding={q.finding} absent="Not enough judged moves in one phase yet." ex={q.clusters.peak?.example} actions={[q.action, q.bot]}>
        {acc && <svg viewBox={`0 0 ${w} ${h}`} className="spark" preserveAspectRatio="none"><polyline points={pts} fill="none" stroke="var(--brand)" strokeWidth={2} /></svg>}
        <div className="ins-stats">
          {(["opening", "middlegame", "endgame"] as const).map((p) => <div key={p}><div className="faint">{p}</div><b className="num">{q.phases[p]?.accuracy ?? "–"}</b><div className="faint">{q.phases[p] ? `${q.phases[p]!.errors} mistakes` : "no moves"}</div></div>)}
        </div>
        {q.band && <p className="muted">Your average centipawn loss is {q.band.acpl}; your band plays at {q.band.expected_low}–{q.band.expected_high} ({q.band.verdict}). <span className="faint">Source: {q.band.source}.</span></p>}
        {q.time_controls && <ul className="ins-list">{q.time_controls.map((t) => <li key={t.time_control}><span>{t.time_control}</span><span className="num">accuracy {t.accuracy}</span><span className="faint">{t.blunders_per_game} blunders per game</span></li>)}</ul>}
      </Section>

      <Section title="Tactics" finding={tc.finding} absent={more(tc.needs, "missed tactics of one kind")} ex={tc.motifs.find((m) => m.theme === tc.most_missed)?.example} actions={[tc.action, tc.lesson, tc.bot]}>
        {tc.motifs.some((m) => m.seen) && <ul className="ins-list">{tc.motifs.filter((m) => m.seen).map((m) => <li key={m.theme}><span>{m.name}</span><span className="num">found {m.found} · missed {m.missed}</span><span className="faint">−{m.drop_per_game}% per game</span></li>)}</ul>}
      </Section>

      <section className="card ins-section">
        <div className="card-title"><h3>Strengths</h3></div>
        {strengths.length ? <ul className="ins-list">{strengths.map((s, i) => <li key={i}><span className="chip chip-ok">{s.area}</span><span>{s.text}</span></li>)}</ul>
          : <p className="faint">No area is clearly better than your band yet: strengths show once a rate is high over five chances or more.</p>}
      </section>
    </div>
  );
}
