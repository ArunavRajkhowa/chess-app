import { Chess } from "chess.js";
import { Send } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Board } from "../components/board/Board";
import { checkSquare, destsFor, safeMove, soundForMove } from "../lib/chess/game";
import { START_FEN, type PromotionPiece, type Square } from "../lib/chess/types";
import { streamCoach } from "../lib/coach";
import { play as playSound } from "../lib/sound";
import "./Coach.css";

type Level = "beginner" | "intermediate" | "advanced" | "master";
interface Turn { role: "user" | "assistant"; content: string; source?: string }

export function CoachPage() {
  const [chess] = useState(() => new Chess());
  const [fen, setFen] = useState(START_FEN);
  const [level, setLevel] = useState<Level>("intermediate");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [fenInput, setFenInput] = useState("");
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const listRef = useRef<HTMLDivElement>(null);
  const boardChess = useMemo(() => new Chess(fen), [fen]);
  const dests = useMemo(() => destsFor(boardChess), [boardChess]);

  const onMove = (from: Square, to: Square, promotion?: PromotionPiece) => {
    const mv = safeMove(chess, { from, to, promotion });
    if (!mv) return;
    playSound(soundForMove(mv, chess));
    setFen(chess.fen());
  };
  const loadFen = () => {
    try { chess.load(fenInput.trim()); setFen(chess.fen()); } catch { setTurns((t) => [...t, { role: "assistant", content: "That FEN is not valid." }]); }
  };
  const ask = async (q: string) => {
    if (!q.trim() || busy) return;
    setBusy(true);
    setQuestion("");
    const history = turns.map((t) => ({ role: t.role, content: t.content }));
    setTurns((t) => [...t, { role: "user", content: q }, { role: "assistant", content: "" }]);
    try {
      const done = await streamCoach("/api/coach/chat", { fen, question: q, level, history }, (chunk) =>
        setTurns((t) => { const n = t.slice(); n[n.length - 1] = { ...n[n.length - 1], content: n[n.length - 1].content + chunk }; return n; }),
      );
      setTurns((t) => { const n = t.slice(); n[n.length - 1] = { ...n[n.length - 1], source: done.source }; return n; });
    } catch (e) {
      setTurns((t) => { const n = t.slice(); n[n.length - 1] = { role: "assistant", content: `Coach unavailable: ${e instanceof Error ? e.message : String(e)}` }; return n; });
    } finally {
      setBusy(false);
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
    }
  };

  const PRESETS = ["What should I play here and why?", "What is my opponent threatening?", "Explain the pawn structure.", "What plan should I follow?", "Which of my pieces is worst placed?"];

  return (
    <div className="coachpage" data-testid="coachpage">
      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <h2>Ask the coach</h2>
          <div className="row">
            <select className="select" style={{ width: 150 }} value={level} onChange={(e) => setLevel(e.target.value as Level)} data-testid="coach-level">
              {(["beginner", "intermediate", "advanced", "master"] as Level[]).map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
            <button className="btn btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
            <button className="btn btn-sm" onClick={() => { chess.undo(); setFen(chess.fen()); }}>Undo</button>
            <button className="btn btn-sm" onClick={() => { chess.reset(); setFen(chess.fen()); }}>Reset</button>
          </div>
        </div>
        <Board fen={fen} orientation={orientation} movable={{ color: "both", dests }} check={checkSquare(boardChess)} onMove={onMove} />
        <div className="row" style={{ marginTop: 8 }}>
          <input className="input" placeholder="Paste a FEN to set up a position" value={fenInput} onChange={(e) => setFenInput(e.target.value)} />
          <button className="btn btn-sm" onClick={loadFen}>Load</button>
        </div>
      </div>
      <aside className="card coach-chat">
        <div className="coach-turns" ref={listRef} data-testid="coach-turns">
          {turns.length === 0 && (
            <div className="faint">Set up any position on the board, then ask. The coach only talks about facts it can verify with the engine.</div>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`turn ${t.role}`}>
              <div className="turn-body">{t.content || (busy && i === turns.length - 1 ? "…" : "")}</div>
              {t.source === "rules" && <div className="faint" style={{ fontSize: 11 }}>rule-based answer (no API key configured)</div>}
            </div>
          ))}
        </div>
        <div className="presets">
          {PRESETS.map((p) => <button key={p} className="theme-chip" onClick={() => ask(p)} disabled={busy}>{p}</button>)}
        </div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
          <input className="input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about this position…" data-testid="coach-input" />
          <button className="btn btn-primary" type="submit" disabled={busy || !question.trim()} data-testid="coach-send"><Send size={14} /></button>
        </form>
      </aside>
    </div>
  );
}
