/* The one door to the backend. Every call is typed here so a renamed field fails to compile. */

export interface BotPublic {
  id: string;
  name: string;
  elo: number;
  tier: "beginner" | "intermediate" | "advanced" | "master" | "special";
  tagline: string;
  avatar: string;
  description: string;
  greeting: string;
  personality: { aggression: number; solidity: number; trade_when_ahead: number; favourite_openings: string[] };
}

export interface MoveRecord {
  ply: number;
  san: string;
  uci: string;
  fen: string;
  by: "player" | "bot";
  source: string | null;
  eval_cp: number | null;
}

export interface GameState {
  id: string;
  fen: string;
  pgn: string;
  moves: MoveRecord[];
  status: "active" | "finished";
  result: string | null;
  termination: string | null;
  player_color: "white" | "black";
  bot: BotPublic | { id: string; name: string; avatar: string; white_name?: string; black_name?: string };
  coach_mode: boolean;
  time_control: string | null;
  start_fen: string | null;
  opening: { eco: string; name: string } | null;
  last_move: [string, string] | null;
  in_check: boolean;
  turn: "w" | "b";
  legal_moves: string[];
  threats: { san: string; uci: string; kind: "capture" | "mate"; gain: number }[];
}

export interface MoveResponse {
  game: GameState;
  player_move: MoveRecord;
  bot_move: MoveRecord | null;
  bot_says: string | null;
  eval_cp: number | null;
  eval_text: string | null;
}

export interface HintResponse {
  move_uci: string;
  move_san: string;
  eval_text: string;
  line_san: string[];
  threats: string[];
}

export type Classification =
  | "brilliant" | "great" | "best" | "excellent" | "good" | "book"
  | "inaccuracy" | "mistake" | "miss" | "blunder" | "forced";

export interface ReviewedMove {
  ply: number;
  move_number: number;
  color: "white" | "black";
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
  classification: Classification;
  accuracy: number;
  win_before: number;
  win_after: number;
  cp_loss: number;
  eval_after_cp: number;
  eval_after_text: string;
  best_move_san: string;
  best_move_uci: string;
  best_line_san: string[];
  best_eval_text: string;
  phase: "opening" | "middlegame" | "endgame";
  is_key_moment: boolean;
  note: string;
}

export interface SideSummary {
  /** null when the side made no move: nothing to judge. */
  accuracy: number | null;
  acpl: number | null;
  estimated_rating: number | null;
  counts: Record<Classification, number>;
  phase_accuracy: Record<string, number | null>;
}

export interface GameReport {
  moves: ReviewedMove[];
  white: SideSummary;
  black: SideSummary;
  opening: { eco: string; name: string; last_book_ply: number } | null;
  depth: number;
  result: string | null;
  eval_graph: number[];
  key_moments: number[];
  phase_boundaries: { middlegame: number | null; endgame: number | null };
}

export interface ReviewJob {
  id: string;
  game_id: string;
  status: "queued" | "running" | "done" | "failed";
  progress: { done: number; total: number };
  error: string | null;
  report: GameReport | null;
}

export interface GameSummary {
  id: string;
  created_at: string;
  updated_at: string;
  player_color: "white" | "black";
  bot_id: string | null;
  bot_name: string;
  bot_avatar: string;
  time_control: string;
  status: string;
  result: string | null;
  termination: string | null;
  opening_eco: string | null;
  opening_name: string | null;
  white_name: string | null;
  black_name: string | null;
  source: string;
  plies: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* no JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<{ ok: boolean; engine: { name: string; kind: string }; openings: number; coach: { llm: boolean; provider: string | null; model: string; problem: string | null } }>("/api/health"),
  bots: () => request<{ bots: BotPublic[] }>("/api/bots"),
  newGame: (bot_id: string, player_color: "white" | "black" | "random", coach_mode = false, time_control: string | null = null, fen: string | null = null) =>
    post<GameState>("/api/play/games", { bot_id, player_color, coach_mode, time_control, fen }),
  flag: (id: string) => post<GameState>(`/api/play/games/${id}/flag`),
  reloadContent: () => post<{ lessons: number; puzzles: number; games: number }>("/api/content/reload"),
  game: (id: string) => request<GameState>(`/api/play/games/${id}`),
  games: () => request<{ games: GameSummary[] }>("/api/play/games"),
  move: (id: string, move: string, want_eval = false) => post<MoveResponse>(`/api/play/games/${id}/move`, { move, want_eval }),
  resign: (id: string) => post<GameState>(`/api/play/games/${id}/resign`),
  takeback: (id: string) => post<GameState>(`/api/play/games/${id}/takeback`),
  hint: (id: string) => request<HintResponse>(`/api/play/games/${id}/hint`),
  startReview: (id: string, mode: "quick" | "full" | "deep" = "full") => post<ReviewJob>(`/api/review/games/${id}`, { mode }),
  importPgn: (pgn: string, mode: "quick" | "full" | "deep" = "full") => post<{ game_id: string; job: ReviewJob; white: string; black: string }>("/api/review/import", { pgn, mode }),
  reviewJob: (jobId: string) => request<ReviewJob>(`/api/review/jobs/${jobId}`),
  review: (gameId: string) => request<{ game_id: string; report: GameReport; game: { moves: MoveRecord[]; pgn: string; player_color: string; bot_id: string | null; white_name: string | null; black_name: string | null; result: string | null } }>(`/api/review/games/${gameId}`),
};
