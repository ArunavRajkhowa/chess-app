import { create } from "zustand";
import { Engine, type AnalyseOptions, type AnalyseResult } from "../lib/engine/uci";

interface EngineState {
  engine: Engine | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  load: () => Promise<Engine | null>;
  /** Evaluate a position; a newer request cancels an older one. */
  evaluate: (fen: string, opts?: AnalyseOptions) => Promise<AnalyseResult | null>;
}

let loading: Promise<Engine | null> | null = null;

export const useEngine = create<EngineState>((set, get) => ({
  engine: null,
  status: "idle",
  error: null,
  load: async () => {
    const { engine } = get();
    if (engine) return engine;
    if (loading) return loading;
    set({ status: "loading" });
    loading = Engine.load()
      .then((e) => {
        set({ engine: e, status: "ready", error: null });
        return e;
      })
      .catch((err: unknown) => {
        set({ status: "error", error: err instanceof Error ? err.message : String(err) });
        return null;
      });
    return loading;
  },
  evaluate: async (fen, opts) => {
    const e = get().engine ?? (await get().load());
    if (!e) return null;
    return e.analyse(fen, opts);
  },
}));
