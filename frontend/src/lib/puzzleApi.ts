export interface Puzzle {
  id: string;
  fen: string;
  moves: string[];
  rating: number;
  themes: string[];
  source: { white?: string; black?: string; year?: string; event?: string };
  solver_color: "white" | "black";
}
export interface PuzzleTheme { key: string; name: string; description: string; count: number }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* no body */ }
    throw new Error(String(detail));
  }
  return (await res.json()) as T;
}

export const puzzleApi = {
  themes: () => req<{ themes: PuzzleTheme[]; total: number }>("/api/puzzles/themes"),
  next: (o: { themes?: string[]; min?: number; max?: number }) => {
    const q = new URLSearchParams();
    if (o.themes?.length) q.set("themes", o.themes.join(","));
    if (o.min !== undefined) q.set("min_rating", String(o.min));
    if (o.max !== undefined) q.set("max_rating", String(o.max));
    return req<{ puzzle: Puzzle; player_rating: number }>(`/api/puzzles/next?${q}`);
  },
  attempt: (id: string, solved: boolean, seconds: number, mode: "rated" | "custom" | "rush" | "daily") =>
    req<{ delta: number; rating_after: number; puzzle_rating: number }>(`/api/puzzles/${id}/attempt`, { method: "POST", body: JSON.stringify({ solved, seconds, mode }) }),
  rushStart: (mode: "3m" | "5m" | "survival") => req<{ mode: string; seconds: number | null; strikes: number; puzzles: Puzzle[] }>(`/api/puzzles/rush/start?mode=${mode}`),
  rushFinish: (mode: string, score: number, wrong: number, seconds: number) => req<{ best: number; new_best: boolean }>("/api/puzzles/rush/finish", { method: "POST", body: JSON.stringify({ mode, score, wrong, seconds }) }),
  stats: () => req<{ rating: number; attempts: number; solved: number; accuracy: number | null; rush_best: Record<string, number> }>("/api/puzzles/stats/me"),
  daily: () => req<{ date: string; puzzle: Puzzle }>("/api/puzzles/daily"),
};
