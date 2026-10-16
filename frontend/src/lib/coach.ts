/* Server-sent events from the coach endpoints. The body is JSON; each event is `data: {...}`. */
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
