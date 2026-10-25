import { BarChart3, BookOpen, Brain, Eye, Flag, GraduationCap, Home, Library, Microscope, MoreHorizontal, Puzzle, Settings, Swords, Target, TrendingUp, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useSettings } from "../../store/settings";
import "./Shell.css";

interface NavItem { to: string; label: string; icon: typeof Home; end?: boolean }

// Grouped by what the player is doing: the group names are the navigation's own information.
const NAV: { group: string | null; items: NavItem[] }[] = [
  { group: null, items: [{ to: "/", label: "Home", icon: Home, end: true }] },
  { group: "Train", items: [
    { to: "/play", label: "Play", icon: Swords },
    { to: "/puzzles", label: "Puzzles", icon: Puzzle },
    { to: "/endgames", label: "Endgames", icon: Flag },
    { to: "/openings", label: "Openings", icon: BookOpen },
    { to: "/vision", label: "Vision", icon: Eye },
  ] },
  { group: "Study", items: [
    { to: "/learn", label: "Learn", icon: GraduationCap },
    { to: "/plan", label: "Study plan", icon: Target },
    { to: "/games", label: "Master games", icon: Library },
  ] },
  { group: "Improve", items: [
    { to: "/review", label: "Game review", icon: TrendingUp },
    { to: "/insights", label: "Insights", icon: BarChart3 },
    { to: "/analysis", label: "Analysis", icon: Microscope },
    { to: "/coach", label: "Coach", icon: Brain },
  ] },
];
const SETTINGS: NavItem = { to: "/settings", label: "Settings", icon: Settings };
// On a phone the bar holds the four places a session starts; everything else is one tap away under More.
const PHONE_BAR = new Set(["/", "/play", "/puzzles", "/learn"]);
const ALL = [...NAV.flatMap((g) => g.items), SETTINGS];

function Item({ to, label, icon: Icon, end, className = "" }: NavItem & { className?: string }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `${className} ${isActive ? "active" : ""}`}>
      <Icon size={17} strokeWidth={1.75} />
      <span>{label}</span>
    </NavLink>
  );
}

export function Shell() {
  const boardTheme = useSettings((s) => s.boardTheme);
  const theme = useSettings((s) => s.theme);
  const [more, setMore] = useState(false);
  const moreButton = useRef<HTMLButtonElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  const location = useLocation();
  useEffect(() => setMore(false), [location]);

  // The More sheet is a disclosure: focus moves into it and Escape closes it, back on the button.
  useEffect(() => {
    if (!more) return;
    sheet.current?.querySelector("a")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setMore(false); moreButton.current?.focus(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [more]);

  // The theme lives on <html> so the page background and the colour scheme change together;
  // index.html sets it once before first paint, this keeps it and the browser bar in step.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const apply = () => {
      const root = document.documentElement;
      root.dataset.theme = theme === "system" ? (mq.matches ? "light" : "dark") : theme;
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", getComputedStyle(root).getPropertyValue("--bg").trim());
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  return (
    <div className="shell" data-board={boardTheme}>
      <nav className="shell-nav" aria-label="Main">
        <NavLink to="/" className="shell-brand">
          <img src="/pieces/cburnett/wN.svg" alt="" width={26} height={26} />
          <span>Chess Coach</span>
        </NavLink>
        {NAV.map(({ group, items }) => (
          <div className="shell-group" key={group ?? "home"}>
            {group && <span className="shell-group-name">{group}</span>}
            <ul>
              {items.map((it) => <li key={it.to} className={PHONE_BAR.has(it.to) ? "phone-bar" : ""}><Item {...it} /></li>)}
            </ul>
          </div>
        ))}
        <Item {...SETTINGS} className="shell-settings" />
        <button type="button" ref={moreButton} className={`shell-more ${more ? "active" : ""}`} onClick={() => setMore((m) => !m)} aria-expanded={more} aria-controls="shell-more-sheet">
          {more ? <X size={17} strokeWidth={1.75} /> : <MoreHorizontal size={17} strokeWidth={1.75} />}
          <span>More</span>
        </button>
      </nav>
      {more && (
        <div className="shell-sheet" id="shell-more-sheet" ref={sheet}>
          <ul>
            {ALL.filter((it) => !PHONE_BAR.has(it.to)).map((it) => <li key={it.to}><Item {...it} /></li>)}
          </ul>
        </div>
      )}
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  );
}
