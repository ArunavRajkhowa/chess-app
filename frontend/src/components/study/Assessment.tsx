import { useState } from "react";
import { studyApi, type Assessment as AssessmentData } from "../../lib/studyApi";
import "./Study.css";

/** A grandmaster's look at the position on the board: what differs between the sides, and the plan each side gets from it. */
export function Assessment({ fen }: { fen: string }) {
  const [data, setData] = useState<{ fen: string; a: AssessmentData | null; busy: boolean; error: string | null } | null>(null);
  const current = data?.fen === fen ? data : null;
  const run = () => {
    setData({ fen, a: null, busy: true, error: null });
    studyApi.assess(fen).then((a) => setData((d) => (d?.fen === fen ? { ...d, a, busy: false } : d))).catch((e: Error) => setData((d) => (d?.fen === fen ? { ...d, busy: false, error: e.message } : d)));
  };
  if (!current) return <button className="btn btn-sm" onClick={run} data-testid="assess">Assess the position</button>;
  if (current.busy) return <p className="faint">Looking at the position…</p>;
  if (current.error) return <span className="chip chip-danger">{current.error}</span>;
  const a = current.a!;
  return (
    <div className="assess" data-testid="assessment">
      <p className="assess-verdict">{a.verdict}</p>
      {a.imbalances.length > 0 && (
        <ul className="assess-items">
          {a.imbalances.map((i, k) => <li key={k}>{i.text} <span className={`assess-side ${i.side.toLowerCase()}`}>{i.side === "both" ? "for both" : `for ${i.side}`}</span></li>)}
        </ul>
      )}
      <div className="assess-plans">
        {(["White", "Black"] as const).map((side) => (
          <div key={side}>
            <b>{side}'s plan</b>
            <ul>{a.plans[side].map((p, k) => <li key={k}>{p}</li>)}</ul>
          </div>
        ))}
      </div>
      <button className="btn btn-sm btn-ghost" onClick={run}>Refresh</button>
    </div>
  );
}
