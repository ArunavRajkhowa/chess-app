import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AwardMark, BotAvatar, EmptyArt, Hero } from "../components/art";
import { Board } from "../components/board/Board";
import { GoalBar } from "../components/plan/GoalBar";
import { api, type GameSummary } from "../lib/api";
import { learnApi, nextLesson } from "../lib/learnApi";
import { puzzleApi, type Puzzle } from "../lib/puzzleApi";
import { play as playSound } from "../lib/sound";
import "./Home.css";

interface Awards { awards: { key: string; name: string; how: string; earned: boolean }[]; earned: number; total: number }
const AWARDS_SEEN = "awards-earned-keys"; // the awards earned the last time Home was open: a new key means the award sound

export function HomePage() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [daily, setDaily] = useState<{ date: string; puzzle: Puzzle; solved_today: boolean; streak: number } | null>(null);
  const [awards, setAwards] = useState<Awards | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [stats, setStats] = useState<{ rating: number; attempts: number } | null>(null);
  const [learn, setLearn] = useState<{ due: number; next: { id: string; title: string } | null } | null>(null);
  const [puzzlesDue, setPuzzlesDue] = useState(0);
  useEffect(() => {
    api.games().then((r) => setGames(r.games.slice(0, 6))).catch(() => undefined);
    puzzleApi.daily().then(setDaily).catch(() => undefined);
    puzzleApi.stats().then(setStats).catch(() => undefined);
    puzzleApi.review().then((r) => setPuzzlesDue(r.due)).catch(() => undefined);
    learnApi.curriculum().then((r) => {
      const next = nextLesson(r.bands.flatMap((b) => b.modules.flatMap((m) => m.lessons)), r.level);
      setLearn({ due: r.review_due, next: next && { id: next.id, title: next.title } });
    }).catch(() => undefined);
    fetch("/api/awards").then((r) => r.json()).then((a: Awards) => {
      setAwards(a);
      const earned = a.awards.filter((x) => x.earned).map((x) => x.key);
      let prev: string[] | null = null; // null: first visit in this browser, so nothing counts as new
      try { const raw = localStorage.getItem(AWARDS_SEEN); prev = raw ? JSON.parse(raw) : null; localStorage.setItem(AWARDS_SEEN, JSON.stringify(earned)); } catch { /* storage off */ }
      const seen = prev;
      const added = seen ? earned.filter((k) => !seen.includes(k)) : [];
      if (added.length) { setFresh(new Set(added)); playSound("award"); }
    }).catch(() => undefined);
  }, []);

  // The one next step, in the order a coach would pick: what is due, what is unfinished, today's puzzle, the next lesson.
  const due = (learn?.due ?? 0) + puzzlesDue;
  const active = games.find((g) => g.status === "active");
  const next = due > 0 ? { to: "/learn/review", label: `Review ${due} position${due === 1 ? "" : "s"}` }
    : active ? { to: `/play/${active.id}`, label: `Resume your game against ${active.bot_name}` }
    : daily && !daily.solved_today ? { to: "/puzzles?daily=1", label: "Solve today's puzzle" }
    : learn?.next ? { to: `/learn/${learn.next.id}`, label: `Next lesson: ${learn.next.title}` }
    : { to: "/play", label: "Play a bot" };
  const facts = [
    !stats ? null : stats.attempts > 0 ? `Your puzzle rating is ${stats.rating.toLocaleString()}.` : "No rated puzzles yet.",
    due > 0 ? `${due} position${due === 1 ? " is" : "s are"} due for review.` : null,
    daily && daily.streak > 0 ? `Day ${daily.streak} of your daily-puzzle streak.` : null,
  ].filter(Boolean).join(" ");
  const earned = awards?.awards.filter((a) => a.earned) ?? [];
  const notYet = awards?.awards.filter((a) => !a.earned) ?? [];
  const nextAward = notYet[0];
  const award = (a: Awards["awards"][number]) => (
    <span key={a.key} className={`award ${a.earned ? "earned" : ""} ${fresh.has(a.key) ? "new" : ""}`} title={a.how}>
      <AwardMark earned={a.earned} size={30} />
      <span className="faint">{a.name}</span>
    </span>
  );

  return (
    <div className="stack">
      <section className="home-hero">
        <div>
          <h1>Welcome back</h1>
          <p>{facts}</p>
          <Link to={next.to} className="btn btn-primary btn-lg home-next" data-testid="home-next">{next.label} <ArrowRight size={18} /></Link>
        </div>
        <Hero width={200} />
      </section>
      <GoalBar primary={false} />
      <div className="home-two">
        {daily && (
          <section className="card home-daily" data-testid="daily-card">
            <div className="card-title"><h3>Daily puzzle</h3><span className="faint">rating {daily.puzzle.rating}</span></div>
            <div className="home-daily-body">
              <div className="home-daily-board"><Board fen={daily.puzzle.fen} orientation={daily.puzzle.solver_color} showCoordinates={false} /></div>
              <div className="col">
                <p className="muted">{daily.puzzle.solver_color === "white" ? "White" : "Black"} to play after the opponent's move. One puzzle a day, five hearts.</p>
                {daily.solved_today ? <span className="chip chip-ok">Solved today</span> : <Link to="/puzzles?daily=1" className="btn" style={{ width: "fit-content" }}>Solve it</Link>}
              </div>
            </div>
          </section>
        )}
        <div className="stack">
          <section className="card">
            <div className="card-title"><h3>Recent games</h3><Link to="/review" className="muted">All games</Link></div>
            {games.length === 0 ? (
              <div className="empty"><EmptyArt kind="games" size={56} /><p>No games yet. Your first one gets a full review.</p><Link to="/play" className="btn">Play a bot</Link></div>
            ) : (
              <ul className="home-games">
                {games.map((g) => (
                  <li key={g.id}>
                    {g.bot_id && <BotAvatar id={g.bot_id} size={26} />}
                    <Link to={g.status === "active" ? `/play/${g.id}` : `/review/${g.id}`} className="grow"><strong>{g.bot_name}</strong> <span className="faint">{g.opening_name ?? ""}</span></Link>
                    <span className={`chip ${g.status === "active" ? "chip-info" : ""}`}>{g.status === "active" ? "in progress" : g.result}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {awards && (
            <section className="card" data-testid="awards">
              <div className="card-title"><h3>Awards</h3><span className="faint">{awards.earned} of {awards.total}</span></div>
              {earned.length > 0 ? <div className="awards-row">{earned.map(award)}</div> : <p className="faint">None yet.</p>}
              {notYet.length > 0 && (
                <details className="fold">
                  <summary>Not yet earned ({notYet.length})</summary>
                  <div className="awards-row">{notYet.map(award)}</div>
                </details>
              )}
              {nextAward && <p className="faint" style={{ marginTop: 8 }}>Next: {nextAward.name}. {nextAward.how}.</p>}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
