import { Chess } from "chess.js";
import { ArrowLeftRight, ChevronFirst, ChevronLast, ChevronLeft, ChevronRight, Flag, Lightbulb, RotateCcw, Sparkles, UserRound } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type BotPublic, type Classification, type GameState, type HintResponse } from "../../lib/api";
import { BotAvatar } from "../art";
import { checkSquare, destsFor, safeMove, soundForMove } from "../../lib/chess/game";
import { capturedFromFen } from "../../lib/chess/material";
import type { PromotionPiece, Square } from "../../lib/chess/types";
import { winPercent, type EngineLine } from "../../lib/engine/uci";
import { CLASS_LABEL, classifyDrop } from "../../lib/review/classify";
import { play as playSound } from "../../lib/sound";
import { useEngine } from "../../store/engine";
import { useSettings } from "../../store/settings";
import { Board } from "../board/Board";
import type { Shape } from "../board/shapes";
import { Clock } from "./Clock";
import { Confetti } from "./Confetti";
import { EvalBar } from "./EvalBar";
import { MoveList, type MoveListItem } from "./MoveList";
import { PlayerCard } from "./PlayerCard";
import "./GameView.css";

interface Props {
  initial: GameState;
  /** Guide me: after each move the server sends a grounded note in the bot's domain (book idea, imbalance and plan, endgame verdict). */
  guide?: boolean;
  onGuide?: (on: boolean) => void;
  onNewGame: () => void;
  onRematch: () => void;
}

interface Feedback {
  ply: number;
  classification: Classification;
  text: string;
  bestSan?: string;
}

const LIVE_EVAL_MS = 700;
const BOT_THINK_MS: [number, number] = [350, 1100];
const LOW_TIME_MS = 10_000;
// Height under a width-limited board that the nav row needs, and that the nav plus a useful move list need.
const UNDER_NAV_PX = 40;
const UNDER_LIST_PX = 120;
// Made once, so React skips them on every render; drawing them again cost each move about 6 ms at 4x CPU.
const ICON = {
  first: <ChevronFirst size={16} />, prev: <ChevronLeft size={16} />, next: <ChevronRight size={16} />, last: <ChevronLast size={16} />,
  hint: <Lightbulb size={14} />, takeback: <RotateCcw size={14} />, resign: <Flag size={14} />, review: <Sparkles size={16} />,
  rematch: <ArrowLeftRight size={14} />, you: <UserRound size={22} strokeWidth={1.75} />,
};

function parseTimeControl(tc: string | null): { baseMs: number; incMs: number } | null {
  if (!tc) return null;
  const [m, inc] = tc.split("+").map(Number);
  return { baseMs: m * 60_000, incMs: inc * 1000 };
}

/** Clocks saved at the last move, so a reload does not give the player back their time. */
function savedClocks(game: GameState): { w: number; b: number } | null {
  try {
    const raw = localStorage.getItem(`play-clock:${game.id}`);
    if (!raw) return null;
    const { w, b, savedAt } = JSON.parse(raw) as { w: number; b: number; savedAt: number };
    const clocks = { w, b };
    if (game.status === "active" && game.moves.length > 0) clocks[game.turn] = Math.max(0, clocks[game.turn] - (Date.now() - savedAt));
    return clocks;
  } catch {
    return null;
  }
}

function fenAtPly(game: GameState, ply: number): string {
  if (ply <= 0) return game.start_fen ?? new Chess().fen();
  return game.moves[ply - 1]?.fen ?? game.fen;
}

export function GameView({ initial, onNewGame, onRematch, guide = false, onGuide }: Props) {
  const navigate = useNavigate();
  const settings = useSettings();
  const evaluate = useEngine((s) => s.evaluate);
  const engineStatus = useEngine((s) => s.status);

  const [game, setGame] = useState<GameState>(initial);
  const [viewPly, setViewPly] = useState<number>(initial.moves.length);
  const [botThinking, setBotThinking] = useState(false);
  const [pending, setPending] = useState<GameState | null>(null); // bot reply held back for a natural delay
  // The lines carry their position, so a stale result is never read as the current one.
  const [evalLines, setEvalLines] = useState<{ fen: string; lines: EngineLine[] } | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [hint, setHint] = useState<HintResponse | null>(null);
  const [botSays, setBotSays] = useState<string | null>(initial.bot && "greeting" in initial.bot ? (initial.bot as { greeting: string }).greeting : null);
  const [showEval, setShowEval] = useState(true);
  const [showThreats, setShowThreats] = useState(initial.coach_mode);
  const [guideNote, setGuideNote] = useState<string | null>(null);
  const [showFeedback, setShowFeedback] = useState(initial.coach_mode);
  const [error, setError] = useState<string | null>(null);
  const [helpUsed, setHelpUsed] = useState(0);
  const lastEvalBefore = useRef<{ fen: string; win: number; best: string | null } | null>(null);
  const tc = useMemo(() => parseTimeControl(initial.time_control), [initial.time_control]);
  const [clocks, setClocks] = useState<{ w: number; b: number }>(() => (tc && savedClocks(initial)) || { w: tc?.baseMs ?? 0, b: tc?.baseMs ?? 0 });
  const lowWarned = useRef(false);
  const viewRef = useRef<HTMLDivElement>(null);
  const boardColRef = useRef<HTMLDivElement>(null);
  // What goes under a width-limited board (side by side only): nothing, the nav row, or the move list and the nav.
  const [under, setUnder] = useState<"none" | "nav" | "list">("none");
  const flagged = useRef(false);

  const live = viewPly === game.moves.length;
  const fen = fenAtPly(game, viewPly);
  const chess = useMemo(() => new Chess(fen), [fen]);
  const dests = useMemo(() => (live && game.status === "active" && !botThinking ? destsFor(chess, true) : new Map()), [chess, live, game.status, botThinking]);
  const myColor = game.player_color === "white" ? "w" : "b";
  const orientation = game.player_color;
  const captured = useMemo(() => capturedFromFen(fen), [fen]);
  const lastMove = viewPly > 0 ? ([game.moves[viewPly - 1].uci.slice(0, 2), game.moves[viewPly - 1].uci.slice(2, 4)] as [Square, Square]) : null;
  const botName = game.bot.name;

  // Live evaluation of the displayed position with the browser engine.
  useEffect(() => {
    if (!showEval && !showFeedback) return;
    let cancelled = false;
    // The final lines only: each depth update re-rendered the whole game view during the move animation.
    evaluate(fen, { movetimeMs: LIVE_EVAL_MS, multipv: 1 })
      .then((r) => { if (!cancelled && r) setEvalLines({ fen, lines: r.lines }); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [fen, evaluate, showEval, showFeedback]);

  const topLine = evalLines?.fen === fen ? evalLines.lines[0] : undefined;

  // Remember the eval before the player's move so we can judge it when the next eval arrives.
  useEffect(() => {
    if (!topLine || !live) return;
    const turn = chess.turn();
    if (turn === myColor && game.status === "active") {
      lastEvalBefore.current = { fen, win: winPercent(topLine), best: topLine.pv[0] ?? null };
    }
  }, [topLine, live, chess, myColor, fen, game.status]);

  const judgePlayerMove = useCallback((uci: string, winAfterLine: EngineLine | undefined, ply: number, san: string, fenBefore: string) => {
    const before = lastEvalBefore.current;
    // A fast reply can beat the live eval: then the saved eval is of an older position, so say nothing.
    if (!before || !winAfterLine || before.fen !== fenBefore) return;
    const wb = myColor === "w" ? before.win : 100 - before.win;
    const wa = myColor === "w" ? winPercent(winAfterLine) : 100 - winPercent(winAfterLine);
    const cls = classifyDrop(wb, wa, before.best === uci);
    const bestSan = before.best && before.best !== uci ? sanOf(before.fen, before.best) : undefined;
    const text = cls === "best" ? `${san} is the best move.` : cls === "excellent" ? `${san} is excellent.` : cls === "good" ? `${san} is a good move.` : `${san} is ${cls === "inaccuracy" ? "an inaccuracy" : "a " + cls}.${bestSan ? ` ${bestSan} was better.` : ""}`;
    setFeedback({ ply, classification: cls, text, bestSan });
  }, [myColor]);

  const applyServerState = useCallback((next: GameState, playerPly: number, playerUci: string, playerSan: string) => {
    // Judge the player's move with a quick engine look at the position right after it.
    if (showFeedback) {
      const after = next.moves[playerPly - 1]?.fen;
      if (after) {
        evaluate(after, { movetimeMs: 500, multipv: 1 }).then((r) => judgePlayerMove(playerUci, r?.lines[0], playerPly, playerSan, fenAtPly(next, playerPly - 1))).catch(() => undefined);
      }
    }
  }, [evaluate, judgePlayerMove, showFeedback]);

  // Release the bot's reply after a short, human-feeling pause.
  useEffect(() => {
    if (!pending) return;
    const ms = BOT_THINK_MS[0] + Math.random() * (BOT_THINK_MS[1] - BOT_THINK_MS[0]);
    const t = setTimeout(() => {
      const botMove = pending.moves[pending.moves.length - 1];
      setGame(pending);
      setViewPly(pending.moves.length);
      setPending(null);
      setBotThinking(false);
      if (tc?.incMs) setClocks((c) => ({ ...c, [myColor === "w" ? "b" : "w"]: c[myColor === "w" ? "b" : "w"] + tc.incMs }));
      if (botMove?.by === "bot") {
        const c = new Chess(pending.moves.length >= 2 ? pending.moves[pending.moves.length - 2].fen : pending.start_fen ?? new Chess().fen());
        const mv = safeMove(c, botMove.uci);
        if (mv) playSound(soundForMove(mv, c));
      }
      if (pending.status === "finished") finishSound(pending);
    }, ms);
    return () => clearTimeout(t);
  }, [pending]);

  const finishSound = (g: GameState) => {
    if (g.result === "1/2-1/2") playSound("draw");
    else if ((g.result === "1-0") === (g.player_color === "white")) playSound("win");
    else playSound("lose");
  };

  const onMove = async (from: Square, to: Square, promotion?: PromotionPiece) => {
    if (!live || game.status !== "active" || botThinking) return;
    const c = new Chess(fen);
    const mv = safeMove(c, { from, to, promotion });
    if (!mv) { playSound("illegal"); return; }
    playSound(soundForMove(mv, c));
    setHint(null);
    setFeedback(null);
    setError(null);
    // Optimistic local update so the piece lands immediately.
    const optimistic: GameState = {
      ...game,
      fen: c.fen(),
      moves: [...game.moves, { ply: game.moves.length + 1, san: mv.san, uci: mv.lan, fen: c.fen(), by: "player", source: null, eval_cp: null }],
      last_move: [mv.from, mv.to],
      turn: c.turn(),
      in_check: c.inCheck(),
      legal_moves: [],
      threats: [],
    };
    setGame(optimistic);
    setViewPly(optimistic.moves.length);
    setBotThinking(true);
    addIncrement(myColor);
    try {
      const res = await api.move(game.id, mv.lan, false, guide);
      setGuideNote(res.guide);
      applyServerState(res.game, optimistic.moves.length, res.player_move.uci, res.player_move.san);
      if (res.bot_says) setBotSays(res.bot_says);
      if (res.bot_move) {
        setPending(res.game);
      } else {
        setGame(res.game);
        setViewPly(res.game.moves.length);
        setBotThinking(false);
        if (res.game.status === "finished") finishSound(res.game);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setGame(game);
      setViewPly(game.moves.length);
      setBotThinking(false);
    }
  };

  const doHint = async () => {
    try {
      const h = await api.hint(game.id);
      setHint(h);
      setHelpUsed((n) => n + 1);
      playSound("notify");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };
  const doTakeback = async () => {
    try {
      const g = await api.takeback(game.id);
      setGame(g); setViewPly(g.moves.length); setHint(null); setFeedback(null); setHelpUsed((n) => n + 1);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };
  const doResign = async () => {
    if (settings.confirmResign && !window.confirm("Resign this game?")) return;
    try { const g = await api.resign(game.id); setGame(g); setViewPly(g.moves.length); playSound("lose"); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  // The page is as tall as the window (min-height); the band is that height less the board column.
  useLayoutEffect(() => {
    const view = viewRef.current, col = boardColRef.current;
    if (!view || !col) return;
    const measure = () => {
      const css = getComputedStyle(view);
      const band = parseFloat(css.minHeight) - col.offsetHeight - parseFloat(css.rowGap);
      setUnder(band >= UNDER_LIST_PX ? "list" : band >= UNDER_NAV_PX ? "nav" : "none");
    };
    const ro = new ResizeObserver(measure);
    ro.observe(view);
    ro.observe(col);
    return () => ro.disconnect();
  }, []);

  // Keyboard navigation through the move list.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") setViewPly((p) => Math.max(0, p - 1));
      else if (e.key === "ArrowRight") setViewPly((p) => Math.min(game.moves.length, p + 1));
      else if (e.key === "ArrowUp") setViewPly(0);
      else if (e.key === "ArrowDown") setViewPly(game.moves.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [game.moves.length]);

  // Clocks: the side to move loses time; the player's clock can run out, the bot's never does.
  const clockSide = game.status === "active" && game.moves.length >= (tc ? 1 : 0) ? (botThinking ? (myColor === "w" ? "b" : "w") : (chess.turn() as "w" | "b")) : null;
  useEffect(() => {
    if (!tc || !clockSide || game.status !== "active") return;
    // Take off the real time passed: a hidden tab runs timers once a second or less.
    let last = performance.now();
    const t = setInterval(() => {
      const now = performance.now();
      const spent = now - last;
      last = now;
      setClocks((c) => {
        const next = { ...c, [clockSide]: Math.max(0, c[clockSide] - spent) };
        if (clockSide === myColor && next[clockSide] <= LOW_TIME_MS && !lowWarned.current) { lowWarned.current = true; playSound("lowTime"); }
        return next;
      });
    }, 100);
    return () => clearInterval(t);
  }, [tc, clockSide, game.status, myColor]);
  useEffect(() => {
    if (!tc || game.status !== "active" || flagged.current) return;
    if (clocks[myColor] <= 0 && clockSide === myColor) {
      flagged.current = true;
      api.flag(game.id).then((g) => { setGame(g); setViewPly(g.moves.length); playSound("lose"); }).catch(() => undefined);
    }
  }, [clocks, tc, game.status, game.id, myColor, clockSide]);
  const addIncrement = (side: "w" | "b") => { if (tc?.incMs) setClocks((c) => ({ ...c, [side]: c[side] + tc.incMs })); };
  useEffect(() => {
    if (!tc) return;
    try { localStorage.setItem(`play-clock:${game.id}`, JSON.stringify({ ...clocks, savedAt: Date.now() })); } catch { /* no storage: a reload restarts the clocks */ }
  }, [game.moves.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const shapes: Shape[] = [];
  if (hint && live) shapes.push({ orig: hint.move_uci.slice(0, 2), dest: hint.move_uci.slice(2, 4), brush: "green" });
  if (showThreats && live && game.status === "active" && chess.turn() === myColor) {
    for (const t of game.threats.slice(0, 3)) shapes.push({ orig: t.uci.slice(0, 2), dest: t.uci.slice(2, 4), brush: "red" });
  }

  const moveItems: MoveListItem[] = game.moves.map((m, i) => ({ ply: i + 1, san: m.san, classification: feedback && feedback.ply === i + 1 && showFeedback ? feedback.classification : undefined }));
  const playerWon = game.status === "finished" && game.result !== "1/2-1/2" && (game.result === "1-0") === (game.player_color === "white");
  const resultTitle = game.status !== "finished" ? "" : game.result === "1/2-1/2" ? "Draw" : playerWon ? "You won!" : `${botName} won`;

  const clockFor = (side: "w" | "b") => (tc ? <Clock ms={clocks[side]} active={clockSide === side} low={clocks[side] <= LOW_TIME_MS} /> : null);
  const botFace = <BotAvatar id={game.bot.id} tier={(game.bot as { tier?: BotPublic["tier"] }).tier} size={30} />;
  const youFace = ICON.you;
  const whiteCard = (
    <PlayerCard name={game.player_color === "white" ? settings.playerName : botName} subtitle={game.player_color === "white" ? "" : `${(game.bot as { elo?: number }).elo ?? ""}`} avatar={game.player_color === "white" ? youFace : botFace} color="white" captured={captured.byWhite} materialEdge={captured.balance} active={chess.turn() === "w" && game.status === "active"} thinking={botThinking && game.player_color === "black"} says={game.player_color === "black" ? botSays : null} clock={clockFor("w")} />
  );
  const blackCard = (
    <PlayerCard name={game.player_color === "black" ? settings.playerName : botName} subtitle={game.player_color === "black" ? "" : `${(game.bot as { elo?: number }).elo ?? ""}`} avatar={game.player_color === "black" ? youFace : botFace} color="black" captured={captured.byBlack} materialEdge={-captured.balance} active={chess.turn() === "b" && game.status === "active"} thinking={botThinking && game.player_color === "white"} says={game.player_color === "white" ? botSays : null} clock={clockFor("b")} />
  );

  const moveList = <MoveList moves={moveItems} currentPly={viewPly} onSelect={setViewPly} opening={null} startFen={game.start_fen} />;
  const nav = (
    <div className="gameview-nav">
      <button className="btn btn-ghost btn-sm" onClick={() => setViewPly(0)} title="First move">{ICON.first}</button>
      <button className="btn btn-ghost btn-sm" onClick={() => setViewPly((p) => Math.max(0, p - 1))} title="Previous">{ICON.prev}</button>
      <button className="btn btn-ghost btn-sm" onClick={() => setViewPly((p) => Math.min(game.moves.length, p + 1))} title="Next">{ICON.next}</button>
      <button className="btn btn-ghost btn-sm" onClick={() => setViewPly(game.moves.length)} title="Last move">{ICON.last}</button>
      {!live && <span className="chip chip-warn">viewing move {viewPly}</span>}
    </div>
  );

  return (
    <div ref={viewRef} className="gameview board-page" data-testid="gameview" data-status={game.status}>
      <Confetti show={playerWon} />
      <div ref={boardColRef} className="board-col gameview-board-col">
        {orientation === "white" ? blackCard : whiteCard}
        <div className="gameview-board-row">
          {showEval && <EvalBar cp={topLine?.cp} mate={topLine?.mate} orientation={orientation} loading={engineStatus !== "ready"} />}
          <Board
            fen={fen}
            orientation={orientation}
            movable={{ color: live && game.status === "active" ? myColor : "none", dests }}
            lastMove={lastMove}
            check={checkSquare(chess)}
            shapes={shapes}
            onMove={onMove}
            showCoordinates={settings.showCoordinates}
            showDests={settings.showLegalMoves}
            autoQueen={settings.autoQueen}
            animate={settings.animation}
          />
        </div>
        {orientation === "white" ? whiteCard : blackCard}
      </div>

      {under !== "none" && (
        <div className="board-under gameview-under">
          {under === "list" && moveList}
          {nav}
        </div>
      )}

      <aside className="side-col gameview-side card">
        <div className="gameview-status">
          {game.status === "finished" ? (
            <div className={`gameview-result pop ${playerWon ? "won" : game.result === "1/2-1/2" ? "draw" : "lost"}`} data-testid="result">
              <h2>{resultTitle}</h2>
              <div className="muted">{game.result} · {game.termination}</div>
            </div>
          ) : (
            <div className="row">
              <span className={`chip ${chess.turn() === myColor ? "chip-ok" : "chip-info"}`}>{botThinking ? `${botName} is thinking` : chess.turn() === myColor ? "Your move" : `${botName} to move`}</span>
              {game.in_check && live && <span className="chip chip-danger">Check</span>}
              {helpUsed > 0 && <span className="chip" title="Hints and takebacks used">help ×{helpUsed}</span>}
            </div>
          )}
          {game.opening && <div className="faint" style={{ marginTop: 4 }}>{game.opening.eco} · {game.opening.name}</div>}
        </div>

        {game.status === "active" ? (
          <div className="gameview-actions">
            <button className="btn btn-sm" onClick={doHint} disabled={!live || botThinking || chess.turn() !== myColor} data-testid="hint-btn">{ICON.hint} Hint</button>
            <button className="btn btn-sm" onClick={doTakeback} disabled={botThinking || !game.moves.some((m) => m.by === "player")} data-testid="takeback-btn">{ICON.takeback} Takeback</button>
            <button className="btn btn-sm btn-danger" onClick={doResign} data-testid="resign-btn">{ICON.resign} Resign</button>
          </div>
        ) : (
          <div className="gameview-actions">
            <button className="btn btn-primary" onClick={() => navigate(`/review/${game.id}`)} data-testid="review-btn">{ICON.review} Game review</button>
            <button className="btn" onClick={onRematch}>{ICON.rematch} Rematch</button>
            <button className="btn" onClick={onNewGame}>New bot</button>
          </div>
        )}

        {feedback && showFeedback && (
          <div className={`feedback cls-${feedback.classification}`} data-testid="feedback">
            <strong>{CLASS_LABEL[feedback.classification]}</strong>
            <span>{feedback.text}</span>
          </div>
        )}
        {hint && live && (
          <div className="feedback cls-book" data-testid="hint">
            <strong>Hint</strong>
            <span>Consider <b>{hint.move_san}</b> ({hint.eval_text}). Line: {hint.line_san.join(" ")}</span>
            {hint.threats.length > 0 && <span className="faint">Threats against you: {hint.threats.join(", ")}</span>}
          </div>
        )}
        {guideNote && guide && (
          <div className="feedback cls-book" data-testid="guide">
            <strong>Guide</strong>
            <span>{guideNote}</span>
          </div>
        )}
        {error && <div className="chip chip-danger">{error}</div>}

        {under !== "list" && moveList}
        {under === "none" && nav}

        <div className="gameview-toggles">
          <label><input type="checkbox" checked={guide} onChange={(e) => onGuide?.(e.target.checked)} data-testid="guide-toggle" /> Guide me</label>
          <label><input type="checkbox" checked={showEval} onChange={(e) => setShowEval(e.target.checked)} /> Eval bar</label>
          <label><input type="checkbox" checked={showFeedback} onChange={(e) => setShowFeedback(e.target.checked)} /> Move feedback</label>
          <label><input type="checkbox" checked={showThreats} onChange={(e) => setShowThreats(e.target.checked)} /> Threat arrows</label>
          {engineStatus === "error" && <span className="chip chip-warn">browser engine unavailable</span>}
        </div>
      </aside>
    </div>
  );
}

function sanOf(fen: string, uci: string): string | undefined {
  try {
    const c = new Chess(fen);
    const mv = c.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: (uci[4] as PromotionPiece | undefined) });
    return mv?.san;
  } catch {
    return undefined;
  }
}
