import { CheckCircle2, Circle, Clock } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { learnApi, type Band } from "../lib/learnApi";
import "./Learn.css";

const BAND_ICON = ["♙", "♘", "♗", "♖", "♕", "♔", "👑", "🎖️", "🏆"];

export function LearnPage() {
  const [bands, setBands] = useState<Band[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    learnApi.curriculum().then((r) => { setBands(r.bands); setOpen(r.bands.find((b) => b.lessons_total > b.lessons_done)?.band ?? 0); }).catch((e: Error) => setError(e.message));
  }, []);
  const total = bands.reduce((a, b) => a + b.lessons_total, 0);
  const done = bands.reduce((a, b) => a + b.lessons_done, 0);
  return (
    <div className="stack" data-testid="learn">
      <div className="page-head">
        <div>
          <h1>Learn</h1>
          <p>A spiral curriculum from the rules to master level, built from the Steps Method, Yusupov, Silman, Dvoretsky and the lichess practice sets.</p>
        </div>
        <div className="learn-total"><div className="faint">lessons done</div><b className="num">{done} / {total}</b></div>
      </div>
      {error && <div className="chip chip-danger">{error}</div>}
      <div className="row" style={{ flexWrap: "wrap" }}>
        <Link to="/vision" className="btn">👁 Board vision trainer</Link>
        <Link to="/endgames" className="btn">🏁 Endgame trainer</Link>
        <Link to="/games" className="btn">📚 Master games</Link>
      </div>
      <div className="bands">
        {bands.map((b) => (
          <section key={b.band} className={`band card ${open === b.band ? "open" : ""} ${b.lessons_total === 0 ? "empty" : ""}`}>
            <button className="band-head" onClick={() => setOpen(open === b.band ? null : b.band)} data-testid={`band-${b.band}`}>
              <span className="band-icon" aria-hidden="true">{BAND_ICON[b.band]}</span>
              <span className="band-title"><b>Band {b.band} · {b.name}</b> <span className="muted">{b.subtitle} · {b.rating}</span></span>
              {b.lessons_total === 0 ? (
                <span className="band-progress faint">no lessons yet</span>
              ) : (
                <span className="band-progress">
                  <span className="progress"><i style={{ width: `${(100 * b.lessons_done) / b.lessons_total}%` }} /></span>
                  <span className="faint num">{b.lessons_done}/{b.lessons_total}</span>
                </span>
              )}
            </button>
            {open === b.band && (
              <div className="band-body">
                {b.modules.length === 0 && <p className="faint">Content for this band is being written.</p>}
                {b.modules.map((m) => (
                  <div key={m.id} className="module">
                    <div className="module-head">
                      <h3>{m.title}</h3>
                      <span className="chip">{m.strand}</span>
                    </div>
                    <p className="muted">{m.summary}</p>
                    {m.source && <p className="faint" style={{ fontSize: 12 }}>Sources: {m.source}</p>}
                    <ul className="lessons">
                      {m.lessons.map((l) => (
                        <li key={l.id}>
                          <Link to={`/learn/${l.id}`} className="lesson-row" data-testid={`lesson-${l.id}`}>
                            {l.completed ? <CheckCircle2 size={18} className="ok" /> : <Circle size={18} className="faint" />}
                            <span className="grow"><b>{l.title}</b><span className="faint"> — {l.objective}</span></span>
                            <span className="faint"><Clock size={12} /> {l.minutes} min · {l.challenges} tasks{l.score !== null ? ` · ${l.score}%` : ""}</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
