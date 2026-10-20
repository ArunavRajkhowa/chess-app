import type { Brush } from "../components/board/shapes";

export interface LessonSummary { id: string; title: string; objective: string; minutes: number; challenges: number; strand: string; band: number; completed: boolean; score: number | null; watch: boolean }
export interface ModuleSummary { id: string; title: string; strand: string; summary: string; source: string; lessons: LessonSummary[] }
export interface Band { band: number; name: string; subtitle: string; rating: string; modules: ModuleSummary[]; lessons_total: number; lessons_done: number }

export type Section =
  | { type: "text"; md: string }
  | { type: "position"; fen: string; orientation?: "white" | "black"; arrows?: { from: string; to: string; brush: Brush }[]; highlights?: { square: string; brush: Brush }[]; caption?: string }
  | { type: "challenge"; fen: string; prompt: string; solution: string[]; solution_san: string[]; hint?: string; explanation?: string; accept_any_legal?: boolean; accept_any_check?: boolean; also?: string[]; also_san?: string[]; orientation?: "white" | "black" }
  | { type: "quiz"; question: string; options: string[]; answer: number; explanation?: string; fen?: string }
  | { type: "drill"; fen: string; goal: "mate" | "promote" | "draw" | "survive" | "win_material"; max_moves?: number; prompt: string; tip?: string; orientation?: "white" | "black" }
  | { type: "game"; pgn: string; title?: string; mode?: "guess" | "replay"; notes?: Record<string, string>; plies: { ply: number; san: string; uci: string; fen: string }[]; start_fen: string; headers: Record<string, string> }
  | { type: "lecture"; title?: string; orientation?: "white" | "black"; frames: LectureFrame[] };

/** One moment of a narrated walkthrough; the server fills in `fen`, `san` and `uci` from the move. */
export interface LectureFrame { fen: string; move?: string; san?: string; uci?: string; say: string; arrows?: { from: string; to: string; brush: Brush }[]; highlights?: { square: string; brush: Brush }[] }

/** The player's band by puzzle rating; null until enough rated puzzles have settled the rating. */
export interface Level { puzzle_rating: number; band: number }
export interface ReviewItem { lesson_id: string; lesson_title: string; section_index: number; interval_days: number; section: Extract<Section, { type: "challenge" | "quiz" }> }

export interface LessonDetail { id: string; title: string; objective: string; minutes: number; band: number; strand: string; module_id: string; sections: Section[]; prev: string | null; next: string | null; practice: { key: string; name: string; count: number }[] }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const learnApi = {
  curriculum: () => req<{ bands: Band[]; review_due: number; level: Level | null }>("/api/learn/curriculum"),
  lesson: (id: string) => req<LessonDetail>(`/api/learn/lessons/${id}`),
  /** `results` says, per challenge or quiz section index, whether it was solved on the first try: a miss joins the review queue. */
  progress: (lesson_id: string, completed: boolean, score: number | null, results: Record<number, boolean> = {}) =>
    req<{ ok: boolean }>("/api/learn/progress", { method: "POST", body: JSON.stringify({ lesson_id, completed, score, results }) }),
  review: () => req<{ items: ReviewItem[]; later: number; next_due_at: string | null }>("/api/learn/review"),
  reviewResult: (lesson_id: string, section_index: number, solved: boolean) =>
    req<{ interval_days: number }>(`/api/learn/review/${lesson_id}/${section_index}`, { method: "POST", body: JSON.stringify({ solved }) }),
  /** `history` is every move since `start_fen`, so the server can see a threefold repetition. */
  drillMove: (fen: string, move: string, goal: string, start_fen?: string, history: string[] = []) =>
    req<{ fen: string; played: string; reply: { san: string; uci: string } | null; outcome: { result: "success" | "fail"; reason: string } | null }>("/api/learn/drill/move", { method: "POST", body: JSON.stringify({ fen, move, goal, start_fen, history }) }),
};
