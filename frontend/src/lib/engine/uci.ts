/* Browser Stockfish (WASM, single thread) behind a Web Worker, spoken to in UCI. One search at a
   time; a new `analyse` stops the previous one, and stale `info` lines are dropped by search id. */

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
}

type Resolver = (value: AnalyseResult) => void;

export class Engine {
  private worker: Worker;
  private searchId = 0;
  private lines = new Map<number, EngineLine>();
  private current: { id: number; fen: string; resolve: Resolver; opts: AnalyseOptions } | null = null;
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

  setOption(name: string, value: string | number | boolean): void {
    this.send(`setoption name ${name} value ${value}`);
  }

  async newGame(): Promise<void> {
    this.send("ucinewgame");
    this.send("isready");
    await this.waitFor("readyok");
  }

  private waitFor(token: string): Promise<void> {
    return new Promise((resolve) => this.waiters.push({ token, resolve }));
  }

  /** Stops any running search and resolves it with what it had. */
  stop(): void {
    if (this.current) this.send("stop");
  }

  analyse(fen: string, opts: AnalyseOptions = {}): Promise<AnalyseResult> {
    this.finishCurrent(null);
    const id = ++this.searchId;
    this.lines = new Map();
    const multipv = Math.max(1, opts.multipv ?? 1);
    this.setOption("MultiPV", multipv);
    this.send(`position fen ${fen}`);
    const go = opts.movetimeMs ? `go movetime ${opts.movetimeMs}` : `go depth ${opts.depth ?? 18}`;
    return new Promise<AnalyseResult>((resolve) => {
      this.current = { id, fen, resolve, opts };
      this.send(go);
    });
  }

  private finishCurrent(bestmove: string | null): void {
    const cur = this.current;
    if (!cur) return;
    this.current = null;
    cur.resolve({ lines: this.sortedLines(), bestmove, fen: cur.fen });
    if (bestmove === null) this.send("stop");
  }

  private sortedLines(): EngineLine[] {
    return [...this.lines.values()].sort((a, b) => a.multipv - b.multipv);
  }

  private onLine(line: string): void {
    for (let i = this.waiters.length - 1; i >= 0; i--) {
      if (line.startsWith(this.waiters[i].token)) {
        this.waiters[i].resolve();
        this.waiters.splice(i, 1);
      }
    }
    if (line.startsWith("bestmove")) {
      const bm = line.split(" ")[1] ?? null;
      if (this.current) this.finishCurrent(bm === "(none)" ? null : bm);
      return;
    }
    if (!line.startsWith("info") || !this.current) return;
    if (!line.includes(" pv ") || !line.includes(" score ")) return;
    const parsed = parseInfo(line, this.current.fen);
    if (!parsed) return;
    this.lines.set(parsed.multipv, parsed);
    this.current.opts.onUpdate?.(this.sortedLines());
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
