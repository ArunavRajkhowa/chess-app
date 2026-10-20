import { BarChart3, BookOpen, Brain, Eye, Flag, GraduationCap, Home, Library, Microscope, Puzzle, Settings, Swords, TrendingUp } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
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
    { to: "/games", label: "Master games", icon: Library },
  ] },
  { group: "Improve", items: [
    { to: "/review", label: "Game review", icon: TrendingUp },
    { to: "/insights", label: "Insights", icon: BarChart3 },
    { to: "/analysis", label: "Analysis", icon: Microscope },
    { to: "/coach", label: "Coach", icon: Brain },
  ] },
];

export function Shell() {
  const boardTheme = useSettings((s) => s.boardTheme);
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
              {items.map(({ to, label, icon: Icon, end }) => (
                <li key={to}>
                  <NavLink to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
                    <Icon size={17} strokeWidth={1.75} />
                    <span>{label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <NavLink to="/settings" className={({ isActive }) => `shell-settings ${isActive ? "active" : ""}`}>
          <Settings size={17} strokeWidth={1.75} />
          <span>Settings</span>
        </NavLink>
      </nav>
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  );
}
