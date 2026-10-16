/* Browser Stockfish (WASM, single thread) behind a Web Worker, spoken to in UCI. Searches are
   serialised: a new `analyse` stops the running one, waits for its `bestmove`, then starts. A
   search that was superseded while still queued resolves empty without touching the engine. */

export interface EngineLine {
  multipv: number;
  depth: number;
  /** Score from White's view. Exactly one of cp / mate is set. */
  cp?: number;
  mate?: number;
  pv: string[];
  nodes?: number;
  nps?: number;
  timeMs?: number;
}

export interface AnalyseOptions {
  depth?: number;
  movetimeMs?: number;
  multipv?: number;
  /** Called on every depth update with the lines so far (sorted by multipv). */
  onUpdate?: (lines: EngineLine[]) => void;
}

export interface AnalyseResult {
  lines: EngineLine[];
  bestmove: string | null;
  fen: string;
  /** True when the search was cancelled by a newer request before it ran. */
  skipped?: boolean;
}

interface Search {
  id: number;
  fen: string;
  opts: AnalyseOptions;
  resolve: (r: AnalyseResult) => void;
  lines: Map<number, EngineLine>;
}

export class Engine {
  private worker: Worker;
  private nextId = 0;
  private latestId = 0;
  private current: Search | null = null;
  private queue: Promise<void> = Promise.resolve();
  private waiters: { token: string; resolve: () => void }[] = [];
  readonly name: string;

  private constructor(worker: Worker, name: string) {
    this.worker = worker;
    this.name = name;
    this.worker.onmessage = (ev: MessageEvent) => this.onLine(String(ev.data));
  }

  static async load(): Promise<Engine> {
    const res = await fetch("/engine/manifest.json");
    if (!res.ok) throw new Error(`engine manifest missing (${res.status}); run npm install in frontend/`);
    const manifest = (await res.json()) as { worker: string };
    const worker = new Worker(manifest.worker);
    const engine = new Engine(worker, "Stockfish");
    engine.send("uci");
    await engine.waitFor("uciok");
    engine.send("setoption name UCI_ShowWDL value false");
    engine.send("isready");
    await engine.waitFor("readyok");
    return engine;
  }

  send(cmd: string): void {
    this.worker.postMessage(cmd);
  }

  private waitFor(token: string): Promise<void> {
    return new Promise((resolve) => this.waiters.push({ token, resolve }));
  }

  /** Asks the running search to finish now; its promise resolves with the lines found so far. */
  stop(): void {
    if (this.current) this.send("stop");
  }

  analyse(fen: string, opts: AnalyseOptions = {}): Promise<AnalyseResult> {
    const id = ++this.nextId;
    this.latestId = id;
    const run = new Promise<AnalyseResult>((resolve) => {
      this.queue = this.queue.then(() => this.runSearch({ id, fen, opts, resolve, lines: new Map() }));
    });
    this.stop();
    return run;
  }

  private runSearch(search: Search): Promise<void> {
    if (search.id !== this.latestId) {
      search.resolve({ lines: [], bestmove: null, fen: search.fen, skipped: true });
      return Promise.resolve();
    }
    this.current = search;
    const multipv = Math.max(1, search.opts.multipv ?? 1);
    this.send(`setoption name MultiPV value ${multipv}`);
    this.send(`position fen ${search.fen}`);
    const go = search.opts.movetimeMs ? `go movetime ${search.opts.movetimeMs}` : `go depth ${search.opts.depth ?? 18}`;
    this.send(go);
    return new Promise<void>((done) => {
      const original = search.resolve;
      search.resolve = (r) => { original(r); done(); };
    });
  }

  private sortedLines(s: Search): EngineLine[] {
    return [...s.lines.values()].sort((a, b) => a.multipv - b.multipv);
  }

  private onLine(line: string): void {
    for (let i = this.waiters.length - 1; i >= 0; i--) {
      if (line.startsWith(this.waiters[i].token)) {
        this.waiters[i].resolve();
        this.waiters.splice(i, 1);
      }
    }
    const cur = this.current;
    if (!cur) return;
    if (line.startsWith("bestmove")) {
      const bm = line.split(" ")[1] ?? null;
      this.current = null;
      cur.resolve({ lines: this.sortedLines(cur), bestmove: bm === "(none)" ? null : bm, fen: cur.fen });
      return;
    }
    if (!line.startsWith("info") || !line.includes(" pv ") || !line.includes(" score ")) return;
    const parsed = parseInfo(line, cur.fen);
    if (!parsed) return;
    cur.lines.set(parsed.multipv, parsed);
    cur.opts.onUpdate?.(this.sortedLines(cur));
  }

  terminate(): void {
    this.worker.terminate();
  }
}

/** Parses one `info ... score ... pv ...` line into a White-perspective EngineLine. */
export function parseInfo(line: string, fen: string): EngineLine | null {
  const t = line.split(" ");
  const out: EngineLine = { multipv: 1, depth: 0, pv: [] };
  const blackToMove = fen.split(" ")[1] === "b";
  for (let i = 1; i < t.length; i++) {
    switch (t[i]) {
      case "depth": out.depth = Number(t[++i]); break;
      case "multipv": out.multipv = Number(t[++i]); break;
      case "nodes": out.nodes = Number(t[++i]); break;
      case "nps": out.nps = Number(t[++i]); break;
      case "time": out.timeMs = Number(t[++i]); break;
      case "score": {
        const kind = t[++i];
        const v = Number(t[++i]);
        const sign = blackToMove ? -1 : 1;
        if (kind === "cp") out.cp = v * sign;
        else if (kind === "mate") out.mate = v * sign;
        if (t[i + 1] === "lowerbound" || t[i + 1] === "upperbound") i++;
        break;
      }
      case "pv": out.pv = t.slice(i + 1); i = t.length; break;
      default: break;
    }
  }
  if (out.cp === undefined && out.mate === undefined) return null;
  return out;
}

export function lineScoreText(l: Pick<EngineLine, "cp" | "mate">): string {
  if (l.mate !== undefined) return l.mate > 0 ? `M${l.mate}` : `-M${Math.abs(l.mate)}`;
  const cp = l.cp ?? 0;
  return `${cp >= 0 ? "+" : ""}${(cp / 100).toFixed(1)}`;
}

/** lichess win% curve, White's view, 0..100. */
export function winPercent(l: Pick<EngineLine, "cp" | "mate">): number {
  if (l.mate !== undefined) return l.mate > 0 ? 100 : 0;
  const cp = Math.max(-10000, Math.min(10000, l.cp ?? 0));
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
}
