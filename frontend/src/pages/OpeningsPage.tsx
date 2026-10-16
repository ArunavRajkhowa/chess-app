import { Chess } from "chess.js";
import { Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Board } from "../components/board/Board";
import { MoveList } from "../components/play/MoveList";
import { checkSquare, destsFor, safeMove, soundForMove } from "../lib/chess/game";
import { START_FEN, type PromotionPiece, type Square } from "../lib/chess/types";
import { play as playSound } from "../lib/sound";
import "./Openings.css";

interface Continuation { san: string; uci: string; eco: string; name: string; ply: number; lines_below: number }
interface Explore { fen: string; opening: { eco: string; name: string; pgn: string; ply: number } | null; continuations: Continuation[] }
interface Family { name: string; eco_from: string; eco_to: string; lines: number; pgn: string }

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

export function OpeningsPage() {
  const [chess] = useState(() => new Chess());
  const [fen, setFen] = useState(START_FEN);
  const [history, setHistory] = useState<{ san: string; fen: string }[]>([]);
  const [explore, setExplore] = useState<Explore | null>(null);
  const [families, setFamilies] = useState<Family[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ eco: string; name: string; pgn: string; ply: number }[]>([]);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [viewPly, setViewPly] = useState(0);

  const refresh = useCallback(async (f: string) => {
    setExplore(await get<Explore>(`/api/openings/explore?fen=${encodeURIComponent(f)}`));
  }, []);

  useEffect(() => { void refresh(START_FEN); get<{ families: Family[] }>("/api/openings/families").then((r) => setFamilies(r.families.slice(0, 40))).catch(() => undefined); }, [refresh]);
  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const t = setTimeout(() => get<{ results: typeof results }>(`/api/openings/search?q=${encodeURIComponent(query)}`).then((r) => setResults(r.results)).catch(() => undefined), 200);
    return () => clearTimeout(t);
  }, [query]);

  const sync = () => {
    const f = chess.fen();
    setFen(f);
    const h = chess.history({ verbose: true }).map((m) => ({ san: m.san, fen: m.after }));
    setHistory(h);
    setViewPly(h.length);
    void refresh(f);
  };

  const playSan = (san: string) => {
    const mv = safeMove(chess, san);
    if (!mv) return;
    playSound(soundForMove(mv, chess));
    sync();
  };
  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    const mv = safeMove(chess, { from, to, promotion });
    if (!mv) return;
    playSound(soundForMove(mv, chess));
    sync();
  };
  const loadLine = async (pgn: string) => {
    chess.reset();
    for (const tok of pgn.split(" ")) {
      if (/^\d/.test(tok)) continue;
      safeMove(chess, tok);
    }
    sync();
    setResults([]);
    setQuery("");
  };
  const goTo = (ply: number) => {
    const target = ply <= 0 ? START_FEN : history[ply - 1].fen;
    setViewPly(ply);
    setFen(target);
    void refresh(target);
  };
  const undo = () => { chess.undo(); sync(); };
  const reset = () => { chess.reset(); sync(); };

  const live = viewPly === history.length;
  const boardChess = useMemo(() => new Chess(fen), [fen]);
  const dests = useMemo(() => (live ? destsFor(boardChess) : new Map()), [boardChess, live]);
  const maxBelow = Math.max(1, ...(explore?.continuations.map((c) => c.lines_below) ?? [1]));

  return (
    <div className="openings" data-testid="openings">
      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <div>
            <h2 data-testid="opening-name">{explore?.opening ? `${explore.opening.eco} · ${explore.opening.name}` : history.length ? "Out of book" : "Starting position"}</h2>
            <div className="faint">{explore?.opening?.pgn ?? "Play moves on the board or pick a line."}</div>
          </div>
          <div className="row">
            <button className="btn btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
            <button className="btn btn-sm" onClick={undo} disabled={!history.length}>Undo</button>
            <button className="btn btn-sm" onClick={reset} disabled={!history.length}>Reset</button>
          </div>
        </div>
        <Board fen={fen} orientation={orientation} movable={{ color: live ? "both" : "none", dests }} lastMove={viewPly > 0 ? null : null} check={checkSquare(boardChess)} onMove={onMove} />
        <div className="card" style={{ marginTop: 12, padding: 0 }}>
          <MoveList moves={history.map((m, i) => ({ ply: i + 1, san: m.san }))} currentPly={viewPly} onSelect={goTo} opening={explore?.opening?.name ?? null} />
        </div>
      </div>
      <aside className="openings-side">
        <div className="card">
          <div className="row input-row">
            <Search size={16} className="faint" />
            <input className="input" placeholder="Search openings (Najdorf, London, C65…)" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="opening-search" />
          </div>
          {results.length > 0 && (
            <ul className="results">
              {results.map((r) => (
                <li key={r.pgn}><button onClick={() => loadLine(r.pgn)}><span className="chip">{r.eco}</span> {r.name} <span className="faint">{r.pgn}</span></button></li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <div className="card-title"><h3>Named continuations</h3><span className="faint">{explore?.continuations.length ?? 0}</span></div>
          {explore && explore.continuations.length === 0 && <p className="faint">No named lines from here. You are on your own: use the engine in Play or Coach.</p>}
          <ul className="conts" data-testid="continuations">
            {explore?.continuations.map((c) => (
              <li key={c.uci}>
                <button onClick={() => playSan(c.san)} disabled={!live}>
                  <b className="conts-san">{c.san}</b>
                  <span className="conts-name"><span className="chip">{c.eco}</span> {c.name}</span>
                  <span className="conts-bar"><i style={{ width: `${Math.max(4, (100 * c.lines_below) / maxBelow)}%` }} /></span>
                  <span className="faint num">{c.lines_below}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        {!history.length && (
          <div className="card">
            <div className="card-title"><h3>Browse families</h3></div>
            <div className="families">
              {families.map((f) => (
                <button key={f.name} className="theme-chip" onClick={() => loadLine(f.pgn)} title={`${f.eco_from}–${f.eco_to}, ${f.lines} lines`}>{f.name} <span className="faint num">{f.lines}</span></button>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
