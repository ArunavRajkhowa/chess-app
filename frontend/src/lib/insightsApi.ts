/* Insights: personal findings from the player's reviewed games. Mirrors backend/insights/. A null is absence (not enough data), never a zero. */
import type { Classification } from "./api";

export type Phase = "opening" | "middlegame" | "endgame";

/** Where a finding sends the player; every id is resolved by the server's content loaders. */
export interface Resource {
  kind: "lesson" | "puzzles" | "course" | "endgame" | "bot" | "game";
  id: string;
  title: string;
  href: string;
  reason?: string;
  theme?: string;
  line_id?: string;
  line?: string;
  rating_min?: number;
  rating_max?: number;
}

/** The player's own position: the move played and the engine's better move. */
export interface Example {
  game_id: string; ply: number; move_number: number; color: "white" | "black"; opponent: string; fen: string;
  played_san: string; played_uci: string; best_san: string; best_uci: string; best_line: string[]; drop: number; classification: Classification; phase: Phase;
}

export interface Record_ { games: number; wins: number; draws: number; losses: number; score: number | null }

export interface OpeningRow extends Record_ {
  name: string; eco: string | null; color: "white" | "black"; accuracy: number | null;
  leave_book: { ply: number; move_number: number; games: number; costly: number; drop_total: number; example: Example | null } | null;
  first_mistake_move: number | null;
  repeated: Repeated | null;
  course: Resource | null;
}
export interface Repeated { times: number; played_san: string; best_san: string; opening: string | null; drop_total: number; example: Example }

export interface Openings {
  rows: OpeningRow[]; repeated: Repeated[];
  needs: number; finding: string | null; action: Resource | null; bot: Resource | null;
}

export interface ImbalanceRow extends Record_ {
  kind: string; mine: boolean; watch: Resource | null;
  example: { game_id: string; ply: number; fen: string; outcome: string; opponent: string };
}
export interface ErrorKind { count: number; drop_per_game: number; example: Example | null }
export interface Middlegame {
  games: number; needs: number; imbalances: ImbalanceRow[]; mobility: { games: number; mean_diff: number | null } | null;
  errors: { tactic: ErrorKind; plan: ErrorKind }; finding: string | null; action: Resource | null; watch: Resource | null; bot: Resource | null;
}

export interface Endgames {
  games: number; needs: number;
  types: (Record_ & { type: string; name: string; accuracy: number | null })[];
  conversion: { games: number; won: number; rate: number; drop_per_game: number; example: Example | null } | null;
  hold: { games: number; held: number; rate: number } | null;
  lose_most: string | null; finding: string | null; action: Resource | null; lesson: Resource | null; bot: Resource | null;
}

export interface Window { games: number; accuracy: number | null; acpl: number | null; blunders_per_game: number; misses_per_game: number }
export interface Quality {
  recent: Window | null;
  trend: { direction: "up" | "down" | "flat" | null; delta: number | null; needs: number };
  phases: Record<Phase, { moves: number; accuracy: number | null; acpl: number; errors: number; drop_per_game: number } | null>;
  weakest_phase: Phase | null;
  clusters: { peak: { from_move: number; to_move: number; blunders: number; moves: number; drop_total: number; example: Example } | null };
  time_controls: (Window & { time_control: string })[] | null;
  band: { acpl: number; expected_low: number; expected_high: number; verdict: "better" | "worse" | "as expected"; source: string } | null;
  finding: string | null; action: Resource | null; bot: Resource | null;
}

export interface Motif { theme: string; name: string; found: number; missed: number; seen: number; drop_per_game: number; example: Example | null }
export interface Tactics { motifs: Motif[]; most_missed: string | null; finding: string | null; action: Resource | null; lesson: Resource | null; bot: Resource | null; needs: number }

export interface Strength { area: string; text: string; example: ImbalanceRow["example"] | null }

export interface PlanItem {
  rank: number; area: string; gain_per_game: number; goal: string; plan_goal: string; why: string;
  action: Resource; also: Resource[]; example: Example | null;
}

export interface Insights {
  games: number;
  message?: string;
  accuracy?: { mean: number; best: number; worst: number; timeline: { at: string; accuracy: number; game_id: string }[] } | null;
  level?: { band: number; name: string; rating: number; range: string; source: "puzzle rating" | "review estimate" } | null;
  level_hint?: string | null;
  trend?: Quality["trend"];
  focus?: PlanItem | null;
  plan?: PlanItem[];
  sections?: { openings: Openings; middlegame: Middlegame; endgames: Endgames; quality: Quality; tactics: Tactics; strengths: Strength[] };
}

export const insightsApi = {
  me: async (): Promise<Insights> => {
    const res = await fetch("/api/insights/me");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return (await res.json()) as Insights;
  },
};
