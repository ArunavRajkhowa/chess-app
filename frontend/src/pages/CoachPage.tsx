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
  const [level, setLevel] = useState<Level | "">("");  // "": the server picks it from the puzzle rating
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
      const done = await streamCoach("/api/coach/chat", { fen, question: q, level: level || undefined, history }, (chunk) =>
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
    <div className="board-page coachpage" data-testid="coachpage">
      <div className="board-col">
        <Board fen={fen} orientation={orientation} movable={{ color: "both", dests }} check={checkSquare(boardChess)} onMove={onMove} />
        <div className="row coach-tools">
          <button className="btn btn-sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>Flip</button>
          <button className="btn btn-sm" onClick={() => { chess.undo(); setFen(chess.fen()); }}>Undo</button>
          <button className="btn btn-sm" onClick={() => { chess.reset(); setFen(chess.fen()); }}>Reset</button>
          <input className="input" placeholder="Paste a FEN" value={fenInput} onChange={(e) => setFenInput(e.target.value)} />
          <button className="btn btn-sm" onClick={loadFen}>Load</button>
        </div>
      </div>
      <aside className="side-col">
        <div className="row coach-head">
          <h2 className="grow">Ask the coach</h2>
          <select className="select" value={level} onChange={(e) => setLevel(e.target.value as Level | "")} data-testid="coach-level">
            <option value="">my level</option>
            {(["beginner", "intermediate", "advanced", "master"] as Level[]).map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <div className="card coach-chat">
          <div className="coach-turns" ref={listRef} data-testid="coach-turns">
            {turns.length === 0 && (
              <div className="faint">Set up any position on the board, then ask. The coach only talks about facts it can verify with the engine.</div>
            )}
            {turns.map((t, i) => (
              <div key={i} className={`turn ${t.role}`}>
                <div className="turn-body">{t.content || (busy && i === turns.length - 1 ? "…" : "")}</div>
                {t.source === "rules" && <div className="faint coach-source">rule-based answer (no API key configured)</div>}
              </div>
            ))}
          </div>
          {turns.length === 0 && (
            <div className="presets">
              {PRESETS.map((p) => <button key={p} className="btn btn-sm" onClick={() => ask(p)} disabled={busy}>{p}</button>)}
            </div>
          )}
          <form className="row coach-ask" onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
            <input className="input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question" data-testid="coach-input" />
            <button className="btn btn-primary" type="submit" disabled={busy || !question.trim()} data-testid="coach-send"><Send size={14} /></button>
          </form>
        </div>
      </aside>
    </div>
  );
}
