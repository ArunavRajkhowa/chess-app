/* Study plans: a goal in the player's words becomes ordered steps over the app's own content. Mirrors backend/plans/plan.py. */

export type StepKind = "course" | "lesson" | "course_line" | "course_trap" | "book_line" | "master_game" | "puzzles" | "endgame" | "play";

/** A book variation group listed inside a "know the variations" step. */
export interface BookGroup { name: string; pgn: string; url: string; lines: number; ecos: string }
export interface PlanStep { n: number; kind: StepKind; id: string; title: string; url: string; reason: string; tracked: boolean; done: boolean; progress: string | null; watch?: boolean; side?: "white" | "black"; groups?: BookGroup[] }
export interface KeyPoint { text: string; source: { kind: StepKind; id: string; title: string } }
export interface Plan { id: string; created_at: string; goal: string; title: string; sides: string[]; key_points: KeyPoint[]; steps: PlanStep[]; done: number; total: number }
export interface PlanSummary { id: string; created_at: string; goal: string; title: string; done: number; total: number }
export interface ClosestFamily { name: string; eco_from: string; eco_to: string; lines: number }
/** `plan` is null when nothing in the catalog matches; `closest` then names the nearest opening families. */
export interface PlanResponse { plan: Plan | null; closest: ClosestFamily[]; message: string | null }

export const STEP_GROUPS: { kind: StepKind; label: string }[] = [
  { kind: "course", label: "Course" }, { kind: "lesson", label: "Lessons" }, { kind: "course_line", label: "Main lines" }, { kind: "course_trap", label: "Traps" },
  { kind: "book_line", label: "Book lines" }, { kind: "master_game", label: "Master games" }, { kind: "puzzles", label: "Puzzles" }, { kind: "endgame", label: "Endgame positions" },
  { kind: "play", label: "Play with Guide me on" },
];

export const EXAMPLE_GOALS = ["Sicilian for both sides", "Rook endgames", "Attacking a castled king", "Najdorf as black", "Queen's Gambit and all its variations"];

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const planApi = {
  create: (goal: string) => req<PlanResponse>("/api/plans", { method: "POST", body: JSON.stringify({ goal }) }),
  list: () => req<{ plans: PlanSummary[] }>("/api/plans"),
  get: (id: string) => req<{ plan: Plan }>(`/api/plans/${id}`),
  /** Only a step the store cannot see (a line, a game) takes a tick; tracked steps come from the records. */
  tick: (id: string, n: number, done: boolean) => req<{ plan: Plan }>(`/api/plans/${id}/steps/${n}`, { method: "POST", body: JSON.stringify({ done }) }),
  remove: (id: string) => req<{ deleted: boolean }>(`/api/plans/${id}`, { method: "DELETE" }),
};
