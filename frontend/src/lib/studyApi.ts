import { useEffect, useState } from "react";
import type { Classification } from "./api";

/** One engine candidate at a position: what it does, and (when it was not played) why not. */
export interface Candidate { san: string; uci: string; eval: string; win: number; line: string[]; played: boolean; reasons: string[]; why_not: string | null }
export interface Threat { san: string; line: string[]; swing: number; kind: "mate" | "capture" | "engine"; reason?: string | null }
/** Why one move of a game was played and why the alternatives were not. */
export interface StudyPly {
  ply: number; san: string; uci: string; fen_before: string; fen_after: string;
  classification: Classification; eval_before: string; eval_after: string; win_before: number; win_after: number;
  rank: number | null; reasons: string[]; problem: string | null; only_move: boolean;
  /** The narration for a move nobody annotated, without the move's name. */
  say: string;
  candidates: Candidate[]; threat: Threat | null; opening: string | null;
}
export interface Study { depth: number; candidates: number; start_fen: string; plies: StudyPly[] }
export interface StudyResponse { status: "done" | "running" | "failed"; progress: { done: number; total: number }; study: Study | null; error?: string }

export interface Imbalance { side: "White" | "Black" | "both"; kind: string; text: string; plan_for: string; plan_against: string }
export interface Assessment { fen: string; eval_cp: number; phase: string; verdict: string; imbalances: Imbalance[]; plans: { White: string[]; Black: string[] }; material: { White: number; Black: number } }

async function req<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const studyApi = {
  game: (gameId: string) => req<StudyResponse>(`/api/study/game/${gameId}`),
  lesson: (lessonId: string, index: number) => req<StudyResponse>(`/api/study/lesson/${lessonId}/${index}`),
  mine: (gameId: string) => req<StudyResponse>(`/api/study/mine/${gameId}`),
  assess: (fen: string) => req<Assessment>(`/api/study/assess?fen=${encodeURIComponent(fen)}`),
};

const POLL_MS = 2000;

/** The study of a game: cached it arrives at once, otherwise the page polls while the engine works through the moves. */
export function useStudy(load: (() => Promise<StudyResponse>) | null, key: string): StudyResponse | null {
  const [state, setState] = useState<{ key: string; res: StudyResponse | null }>({ key, res: null });
  useEffect(() => {
    if (!load) return;
    let live = true;
    let timer: number | undefined;
    const tick = () => {
      load().then((res) => {
        if (!live) return;
        setState({ key, res });
        if (res.status === "running") timer = window.setTimeout(tick, POLL_MS);
      }).catch((e: Error) => { if (live) setState({ key, res: { status: "failed", progress: { done: 0, total: 0 }, study: null, error: e.message } }); });
    };
    tick();
    return () => { live = false; window.clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the key names the game; the loader is rebuilt with it
  }, [key]);
  return state.key === key ? state.res : null;
}
