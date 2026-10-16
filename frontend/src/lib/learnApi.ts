import type { Brush } from "../components/board/shapes";

export interface LessonSummary { id: string; title: string; objective: string; minutes: number; challenges: number; strand: string; band: number; completed: boolean; score: number | null }
export interface ModuleSummary { id: string; title: string; strand: string; summary: string; source: string; lessons: LessonSummary[] }
export interface Band { band: number; name: string; subtitle: string; rating: string; modules: ModuleSummary[]; lessons_total: number; lessons_done: number }

export type Section =
  | { type: "text"; md: string }
  | { type: "position"; fen: string; orientation?: "white" | "black"; arrows?: { from: string; to: string; brush: Brush }[]; highlights?: { square: string; brush: Brush }[]; caption?: string }
  | { type: "challenge"; fen: string; prompt: string; solution: string[]; solution_san: string[]; hint?: string; explanation?: string; accept_any_legal?: boolean; orientation?: "white" | "black" }
  | { type: "quiz"; question: string; options: string[]; answer: number; explanation?: string; fen?: string }
  | { type: "drill"; fen: string; goal: "mate" | "promote" | "draw" | "survive" | "win_material"; max_moves?: number; prompt: string; tip?: string; orientation?: "white" | "black" }
  | { type: "game"; pgn: string; title?: string; mode?: "guess" | "replay"; notes?: Record<string, string>; plies: { ply: number; san: string; uci: string; fen: string }[]; headers: Record<string, string> };

export interface LessonDetail { id: string; title: string; objective: string; minutes: number; band: number; strand: string; module_id: string; sections: Section[]; prev: string | null; next: string | null }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const learnApi = {
  curriculum: () => req<{ bands: Band[] }>("/api/learn/curriculum"),
  lesson: (id: string) => req<LessonDetail>(`/api/learn/lessons/${id}`),
  progress: (lesson_id: string, completed: boolean, score: number | null, state: Record<string, unknown> = {}) =>
    req<{ ok: boolean }>("/api/learn/progress", { method: "POST", body: JSON.stringify({ lesson_id, completed, score, state }) }),
  drillMove: (fen: string, move: string, goal: string) =>
    req<{ fen: string; played: string; reply: { san: string; uci: string } | null; outcome: { result: "success" | "fail"; reason: string } | null }>("/api/learn/drill/move", { method: "POST", body: JSON.stringify({ fen, move, goal }) }),
};
