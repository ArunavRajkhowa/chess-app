import { Target } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { EXAMPLE_GOALS, planApi, type ClosestFamily } from "../../lib/planApi";
import "./GoalBar.css";

/** "What do you want to learn?": a goal in the player's words becomes a study plan, or the closest openings when nothing matches.
    `primary={false}` where another action is the page's one brass button; `examples={false}` hides the example goals. */
export function GoalBar({ autoFocus = false, primary = true, examples = true }: { autoFocus?: boolean; primary?: boolean; examples?: boolean }) {
  const navigate = useNavigate();
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [miss, setMiss] = useState<{ message: string; closest: ClosestFamily[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (text: string) => {
    const g = text.trim();
    if (g.length < 2 || busy) return;
    setBusy(true);
    setError(null);
    setMiss(null);
    try {
      const r = await planApi.create(g);
      if (r.plan) navigate(`/plan/${r.plan.id}`);
      else setMiss({ message: r.message ?? "Nothing matches that goal.", closest: r.closest });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="goalbar card" data-testid="goalbar">
      <form className="goalbar-form" onSubmit={(e) => { e.preventDefault(); void submit(goal); }}>
        <Target size={18} className="goalbar-icon" aria-hidden="true" />
        <input className="input grow" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="What do you want to learn? e.g. the Sicilian and all its variations, for both sides" autoFocus={autoFocus} data-testid="goal-input" />
        <button type="submit" className={primary ? "btn btn-primary" : "btn"} disabled={busy || goal.trim().length < 2} data-testid="goal-submit">{busy ? "Building…" : "Build my plan"}</button>
      </form>
      {examples && <div className="goalbar-chips">
        {EXAMPLE_GOALS.map((g) => <button key={g} type="button" className="chip goalbar-chip" onClick={() => { setGoal(g); void submit(g); }} disabled={busy} data-testid="goal-example">{g}</button>)}
      </div>}
      {error && <div className="chip chip-danger">{error}</div>}
      {miss && (
        <div className="goalbar-miss" data-testid="plan-none">
          <p className="muted">{miss.message}</p>
          {miss.closest.length > 0 && (
            <div className="goalbar-chips">
              <span className="faint">Closest openings:</span>
              {miss.closest.map((f) => <button key={f.name} type="button" className="chip goalbar-chip" onClick={() => { setGoal(f.name); void submit(f.name); }} title={`${f.eco_from}–${f.eco_to}, ${f.lines} lines`} data-testid="closest-family">{f.name}</button>)}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
