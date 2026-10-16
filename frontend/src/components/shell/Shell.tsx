import { BarChart3, BookOpen, Brain, Crown, GraduationCap, Home, Library, Puzzle, Settings, Swords, TrendingUp } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useSettings } from "../../store/settings";
import "./Shell.css";

const NAV = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/play", label: "Play", icon: Swords },
  { to: "/puzzles", label: "Puzzles", icon: Puzzle },
  { to: "/learn", label: "Learn", icon: GraduationCap },
  { to: "/openings", label: "Openings", icon: BookOpen },
  { to: "/games", label: "Master games", icon: Library },
  { to: "/review", label: "Game review", icon: TrendingUp },
  { to: "/coach", label: "Coach", icon: Brain },
  { to: "/insights", label: "Insights", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Shell() {
  const boardTheme = useSettings((s) => s.boardTheme);
  return (
    <div className="shell" data-board={boardTheme}>
      <nav className="shell-nav" aria-label="Main">
        <NavLink to="/" className="shell-brand">
          <Crown size={22} />
          <span>Chess Coach</span>
        </NavLink>
        <ul>
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <li key={to}>
              <NavLink to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
                <Icon size={18} />
                <span>{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  );
}
