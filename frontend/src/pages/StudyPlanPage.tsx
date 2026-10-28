import { Check, Circle, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { GoalBar } from "../components/plan/GoalBar";
import { planApi, STEP_GROUPS, type Plan, type PlanStep, type PlanSummary } from "../lib/planApi";
import "./StudyPlan.css";

export function StudyPlanPage() {
  const { planId } = useParams();
  return (
    <div className="stack" data-testid="studyplan">
      <div className="page-head">
        <div>
          <h1>Study plan</h1>
          {!planId && <p>Say what you want to learn. The plan is built from the lessons, courses, puzzles, master games, endgames and specialist bots the app has, nothing invented.</p>}
        </div>
      </div>
      <GoalBar autoFocus={!planId} examples={!planId} />
      {planId ? <PlanView planId={planId} /> : <PlanList />}
    </div>
  );
}

function PlanList() {
  const [plans, setPlans] = useState<PlanSummary[] | null>(null);
  useEffect(() => { planApi.list().then((r) => setPlans(r.plans)).catch(() => setPlans([])); }, []);
  if (plans === null) return <p className="faint">Loading plans…</p>;
  if (plans.length === 0) return <p className="faint" data-testid="plans-empty">No plans yet. Type a goal above or pick an example.</p>;
  return (
    <section className="card">
      <div className="card-title"><h3>Your plans</h3></div>
      <ul className="plan-list" data-testid="plan-list">
        {plans.map((p) => (
          <li key={p.id}>
            <Link to={`/plan/${p.id}`} className="grow"><strong>{p.title}</strong> <span className="faint">“{p.goal}”</span></Link>
            <span className="num faint">{p.done}/{p.total}</span>
            <div className="progress plan-list-progress"><i style={{ width: `${p.total ? (100 * p.done) / p.total : 0}%` }} /></div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PlanView({ planId }: { planId: string }) {
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { planApi.get(planId).then((r) => setPlan(r.plan)).catch((e: Error) => setError(e.message)); }, [planId]);
  if (error) return <div className="chip chip-danger">{error}</div>;
  if (!plan) return <p className="faint">Loading plan…</p>;

  const tick = async (step: PlanStep) => {
    try { setPlan((await planApi.tick(plan.id, step.n, !step.done)).plan); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };
  const remove = async () => {
    if (!window.confirm("Delete this plan?")) return;
    await planApi.remove(plan.id);
    navigate("/plan");
  };
  const pct = plan.total ? Math.round((100 * plan.done) / plan.total) : 0;

  return (
    <div className="stack" data-testid="plan">
      <section className="card">
        <div className="card-title">
          <h2 data-testid="plan-title">{plan.title}</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={remove} title="Delete this plan" data-testid="plan-delete"><Trash2 size={14} /></button>
        </div>
        <p className="muted">“{plan.goal}”</p>
        <div className="row"><div className="progress grow"><i style={{ width: `${pct}%` }} /></div><span className="num faint" data-testid="plan-progress">{plan.done} of {plan.total} done</span></div>
        {plan.key_points.length > 0 && (
          <details className="plan-points" data-testid="plan-points">
            <summary>Key points ({plan.key_points.length})</summary>
            <ul>
              {plan.key_points.map((k, i) => <li key={i}>{k.text} <span className="faint">— {k.source.title}</span></li>)}
            </ul>
          </details>
        )}
      </section>
      <div className="plan-groups">
        {STEP_GROUPS.map(({ kind, label }) => {
          const steps = plan.steps.filter((s) => s.kind === kind);
          if (!steps.length) return null;
          return (
            <section key={kind} className="card plan-group" data-testid={`plan-group-${kind}`}>
              <div className="card-title"><h3>{label}</h3><span className="faint num">{steps.filter((s) => s.done).length}/{steps.length}</span></div>
              <ol className="plan-steps">
                {steps.map((s) => (
                  <li key={s.n} className={`plan-step ${s.done ? "done" : ""}`} data-testid="plan-step">
                    {s.tracked
                      ? <span className={`plan-mark ${s.done ? "on" : ""}`} title={s.done ? "Done" : "Progress comes from your records"}>{s.done ? <Check size={14} /> : <Circle size={14} />}</span>
                      : <button type="button" className={`plan-mark tick ${s.done ? "on" : ""}`} onClick={() => tick(s)} title={s.done ? "Mark as not done" : "Mark as done"} data-testid="step-tick">{s.done ? <Check size={14} /> : <Circle size={14} />}</button>}
                    <div className="plan-step-body">
                      <Link to={s.url} className="plan-step-title" data-testid={`step-${s.kind}`}>{s.n}. {s.title}{s.watch ? <span className="chip">narrated</span> : null}</Link>
                      <div className="muted plan-step-reason">{s.reason}</div>
                      {s.groups && (
                        <details className="plan-points" data-testid="step-groups">
                          <summary>{s.groups.length} groups</summary>
                          <ul>
                            {s.groups.map((grp) => <li key={grp.pgn}><Link to={grp.url}>{grp.name}</Link> <span className="faint num">{grp.lines} line{grp.lines === 1 ? "" : "s"}, ECO {grp.ecos}</span></li>)}
                          </ul>
                        </details>
                      )}
                      {s.progress && <div className="faint num">{s.progress}</div>}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          );
        })}
      </div>
    </div>
  );
}
