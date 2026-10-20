/* Server-sent events from the coach endpoints. The body is JSON; each event is `data: {...}`. */
import type { Classification } from "./api";
export interface CoachDone {
  source: "llm" | "rules";
  unverified_moves?: string[];
  model?: string;
}

export async function streamCoach(path: string, body: unknown, onText: (chunk: string) => void): Promise<CoachDone> {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: CoachDone = { source: "rules" };
  for (;;) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = raw.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const evt = JSON.parse(line.slice(5).trim()) as { type: string; text?: string } & Partial<CoachDone>;
      if (evt.type === "text" && evt.text) onText(evt.text);
      else if (evt.type === "done") done = { source: evt.source ?? "rules", unverified_moves: evt.unverified_moves, model: evt.model };
      else if (evt.type === "error") throw new Error(evt.text ?? "coach error");
    }
  }
  return done;
}

/** One move judged by the engine as the review judges it (POST /api/coach/try). */
export interface JudgedMove {
  san: string;
  uci: string;
  classification: Classification;
  eval_after: string;
  win_before: number;
  win_after: number;
  best_san: string;
  best_uci: string;
  best_eval: string;
  /** The engine's best answer to the move, SAN from the position after it. */
  reply_line: string[];
  /** The same answer with move numbers: "6.d4 b5 7.Bb3". */
  reply_text: string;
  /** White's material minus Black's, in pawns, at the end of the answer. */
  material_after_reply: number;
  opening: { eco: string; name: string } | null;
  explanation: string;
}

export async function tryMove(fen: string, move: string, compare?: string): Promise<{ tried: JudgedMove; compare: JudgedMove | null }> {
  const res = await fetch("/api/coach/try", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fen, move, compare }) });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as { tried: JudgedMove; compare: JudgedMove | null };
}
