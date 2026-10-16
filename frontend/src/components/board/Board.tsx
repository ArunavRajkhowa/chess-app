import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  FILES, RANKS, fileIndex, piecesFromFen, rankIndex, squareAt, turnFromFen,
  type Color, type PromotionPiece, type Square,
} from "../../lib/chess/types";
import { PromotionDialog } from "./PromotionDialog";
import { reconcilePieces, type BoardPiece } from "./reconcile";
import { shapeKey, toggleShape, type Brush, type Shape } from "./shapes";
import "./Board.css";

export type Orientation = "white" | "black";

export interface Movable {
  /** Which colour the user may move. "both" for free analysis, "none" to view only. */
  color: Color | "both" | "none";
  /** Legal destinations per origin square. */
  dests: Map<Square, Square[]>;
}

export interface BoardProps {
  fen: string;
  orientation?: Orientation;
  movable?: Movable;
  lastMove?: [Square, Square] | null;
  /** Square of the king in check, if any. */
  check?: Square | null;
  shapes?: Shape[];
  /** Programmatic highlight squares (e.g. a lesson's target). */
  highlights?: { square: Square; brush: Brush }[];
  onMove?: (from: Square, to: Square, promotion?: PromotionPiece) => void;
  onSelect?: (square: Square | null) => void;
  onUserShapes?: (shapes: Shape[]) => void;
  /** Premove: allowed when it is not the user's turn; reported, not executed. */
  premovable?: boolean;
  premove?: [Square, Square] | null;
  onPremove?: (pm: [Square, Square] | null) => void;
  showCoordinates?: boolean;
  showDests?: boolean;
  autoQueen?: boolean;
  animate?: boolean;
  className?: string;
}

interface DragState {
  id: number;
  from: Square;
  x: number;
  y: number;
  moved: boolean;
  pointerId: number;
}

const BRUSH_FOR_MOD = (e: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean }): Brush =>
  e.shiftKey ? "red" : e.altKey ? "blue" : e.ctrlKey || e.metaKey ? "yellow" : "green";

export function Board({
  fen,
  orientation = "white",
  movable,
  lastMove = null,
  check = null,
  shapes = [],
  highlights = [],
  onMove,
  onSelect,
  onUserShapes,
  premovable = false,
  premove = null,
  onPremove,
  showCoordinates = true,
  showDests = true,
  autoQueen = false,
  animate = true,
  className = "",
}: BoardProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [pieces, setPieces] = useState<BoardPiece[]>(() => reconcilePieces([], piecesFromFen(fen)));
  const [selected, setSelected] = useState<Square | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [hover, setHover] = useState<Square | null>(null);
  const [promo, setPromo] = useState<{ from: Square; to: Square; color: Color } | null>(null);
  const [userShapes, setUserShapes] = useState<Shape[]>([]);
  const [drawing, setDrawing] = useState<{ orig: Square; brush: Brush } | null>(null);
  const [noAnim, setNoAnim] = useState(false);
  const prevOrientation = useRef(orientation);

  const turn = turnFromFen(fen);
  const pieceAt = useMemo(() => new Map(pieces.map((p) => [p.square, p])), [pieces]);

  useLayoutEffect(() => {
    setPieces((prev) => reconcilePieces(prev, piecesFromFen(fen)));
    setSelected(null);
    setPromo(null);
  }, [fen]);

  useLayoutEffect(() => {
    if (prevOrientation.current !== orientation) {
      prevOrientation.current = orientation;
      setNoAnim(true);
      const t = requestAnimationFrame(() => setNoAnim(false));
      return () => cancelAnimationFrame(t);
    }
  }, [orientation]);

  useEffect(() => {
    onSelect?.(selected);
  }, [selected, onSelect]);

  const canMoveColor = useCallback(
    (color: Color) => {
      if (!movable || movable.color === "none") return false;
      if (movable.color === "both") return true;
      return movable.color === color;
    },
    [movable],
  );

  const isUsersTurn = movable ? movable.color === "both" || movable.color === turn : false;

  // Geometry ------------------------------------------------------------------------------
  const toCoords = useCallback(
    (sq: Square) => {
      const f = fileIndex(sq);
      const r = rankIndex(sq);
      return orientation === "white" ? { col: f, row: 7 - r } : { col: 7 - f, row: r };
    },
    [orientation],
  );

  const squareFromPointer = useCallback(
    (clientX: number, clientY: number): Square | null => {
      const el = rootRef.current;
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      const x = (clientX - rect.left) / rect.width;
      const y = (clientY - rect.top) / rect.height;
      if (x < 0 || x >= 1 || y < 0 || y >= 1) return null;
      const col = Math.floor(x * 8);
      const row = Math.floor(y * 8);
      return orientation === "white" ? squareAt(col, 7 - row) : squareAt(7 - col, row);
    },
    [orientation],
  );

  // Moves ----------------------------------------------------------------------------------
  const dests = movable?.dests;
  const destsOf = useCallback((sq: Square | null) => (sq && dests ? dests.get(sq) ?? [] : []), [dests]);

  const tryMove = useCallback(
    (from: Square, to: Square): boolean => {
      const piece = pieceAt.get(from);
      if (!piece) return false;
      if (!isUsersTurn) {
        if (premovable && canMoveColor(piece.color) && from !== to) {
          onPremove?.([from, to]);
          return true;
        }
        return false;
      }
      if (!destsOf(from).includes(to)) return false;
      const lastRank = piece.color === "w" ? "8" : "1";
      if (piece.type === "p" && to[1] === lastRank) {
        if (autoQueen) onMove?.(from, to, "q");
        else setPromo({ from, to, color: piece.color });
        return true;
      }
      onMove?.(from, to);
      return true;
    },
    [pieceAt, isUsersTurn, premovable, canMoveColor, destsOf, autoQueen, onMove, onPremove],
  );

  // Pointer handling -----------------------------------------------------------------------
  const onPointerDown = (e: React.PointerEvent) => {
    const sq = squareFromPointer(e.clientX, e.clientY);
    if (!sq) return;
    if (e.button === 2) {
      setDrawing({ orig: sq, brush: BRUSH_FOR_MOD(e) });
      return;
    }
    if (e.button !== 0) return;
    if (premove && onPremove) onPremove(null);
    const piece = pieceAt.get(sq);
    const selectable = piece && canMoveColor(piece.color) && (isUsersTurn || premovable);

    if (selected && selected !== sq && (destsOf(selected).includes(sq) || (!isUsersTurn && premovable))) {
      if (tryMove(selected, sq)) {
        setSelected(null);
        return;
      }
    }
    if (selectable && piece) {
      setSelected(sq);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      const rect = rootRef.current!.getBoundingClientRect();
      setDrag({ id: piece.id, from: sq, x: e.clientX - rect.left, y: e.clientY - rect.top, moved: false, pointerId: e.pointerId });
      setHover(sq);
    } else {
      setSelected(null);
    }
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (drawing) return;
    if (!drag) return;
    const rect = rootRef.current!.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const moved = drag.moved || Math.hypot(x - drag.x, y - drag.y) > 4;
    setDrag({ ...drag, x, y, moved });
    setHover(squareFromPointer(e.clientX, e.clientY));
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (drawing) {
      const sq = squareFromPointer(e.clientX, e.clientY);
      const shape: Shape = sq && sq !== drawing.orig ? { orig: drawing.orig, dest: sq, brush: drawing.brush } : { orig: drawing.orig, brush: drawing.brush };
      const next = toggleShape(userShapes, shape);
      setUserShapes(next);
      onUserShapes?.(next);
      setDrawing(null);
      return;
    }
    if (!drag) return;
    const target = squareFromPointer(e.clientX, e.clientY);
    const wasDrag = drag.moved;
    setDrag(null);
    setHover(null);
    if (!target) return;
    if (target === drag.from) {
      // Click without moving keeps the selection; a second click on the same piece deselects.
      if (wasDrag) return;
      return;
    }
    if (tryMove(drag.from, target)) {
      setSelected(null);
    } else if (wasDrag) {
      // Illegal drop: snap back. Keep selection so a click-click still works.
    }
  };

  const onPointerCancel = () => {
    setDrag(null);
    setHover(null);
    setDrawing(null);
  };

  const onContextMenu = (e: React.MouseEvent) => e.preventDefault();

  useEffect(() => {
    if (!drag && !drawing) return;
    const stop = () => { setDrag(null); setDrawing(null); setHover(null); };
    window.addEventListener("blur", stop);
    return () => window.removeEventListener("blur", stop);
  }, [drag, drawing]);

  // Render helpers --------------------------------------------------------------------------
  const squareClasses = useMemo(() => {
    const m = new Map<Square, string[]>();
    const add = (sq: Square | null | undefined, cls: string) => {
      if (!sq) return;
      m.set(sq, [...(m.get(sq) ?? []), cls]);
    };
    if (lastMove) { add(lastMove[0], "last-move"); add(lastMove[1], "last-move"); }
    if (premove) { add(premove[0], "premove"); add(premove[1], "premove"); }
    add(selected, "selected");
    add(check, "check");
    if (showDests && selected && isUsersTurn) {
      for (const d of destsOf(selected)) add(d, pieceAt.has(d) ? "dest occupied" : "dest");
    }
    if (drag?.moved && hover) add(hover, "drag-over");
    for (const h of highlights) add(h.square, `hl-${h.brush}`);
    return m;
  }, [lastMove, premove, selected, check, showDests, isUsersTurn, destsOf, pieceAt, drag, hover, highlights]);

  const squares = useMemo(() => {
    const out: { sq: Square; col: number; row: number; light: boolean }[] = [];
    for (let row = 0; row < 8; row++) {
      for (let col = 0; col < 8; col++) {
        const sq = orientation === "white" ? squareAt(col, 7 - row) : squareAt(7 - col, row);
        out.push({ sq, col, row, light: (fileIndex(sq) + rankIndex(sq)) % 2 === 1 });
      }
    }
    return out;
  }, [orientation]);

  const allShapes = useMemo(() => {
    const live: Shape[] = drawing && hover && hover !== drawing.orig ? [{ orig: drawing.orig, dest: hover, brush: drawing.brush }] : [];
    return [...shapes, ...userShapes, ...live];
  }, [shapes, userShapes, drawing, hover]);

  return (
    <div
      ref={rootRef}
      className={`board ${noAnim || !animate ? "no-anim" : ""} ${drag ? "is-dragging" : ""} ${className}`}
      data-testid="board"
      data-fen={fen}
      data-orientation={orientation}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onContextMenu={onContextMenu}
    >
      <div className="board-squares">
        {squares.map(({ sq, col, row, light }) => (
          <div
            key={sq}
            className={`sq ${light ? "light" : "dark"} ${(squareClasses.get(sq) ?? []).join(" ")}`}
            data-square={sq}
          >
            {showCoordinates && col === 0 && <span className="coord rank">{sq[1]}</span>}
            {showCoordinates && row === 7 && <span className="coord file">{sq[0]}</span>}
          </div>
        ))}
      </div>

      <div className="board-pieces">
        {pieces.map((p) => {
          const { col, row } = toCoords(p.square);
          const isDrag = drag?.id === p.id && drag.moved;
          const size = rootRef.current?.clientWidth ?? 0;
          const style = isDrag
            ? { transform: `translate(${drag.x - size / 16}px, ${drag.y - size / 16}px)` }
            : { transform: `translate(${col * 100}%, ${row * 100}%)` };
          return (
            <div
              key={p.id}
              className={`piece ${p.color}${p.type.toUpperCase()} ${isDrag ? "dragging" : ""} ${selected === p.square ? "selected" : ""}`}
              style={style}
              data-piece={`${p.color}${p.type}`}
              data-square={p.square}
            />
          );
        })}
      </div>

      <svg className="board-shapes" viewBox="0 0 8 8" aria-hidden="true">
        <defs>
          {(["green", "red", "blue", "yellow"] as Brush[]).map((b) => (
            <marker key={b} id={`arrowhead-${b}`} orient="auto" markerWidth="4" markerHeight="4" refX="2.05" refY="2" markerUnits="strokeWidth">
              <path d="M0,0 V4 L3,2 Z" className={`arrow-fill ${b}`} />
            </marker>
          ))}
        </defs>
        {allShapes.map((s) => {
          const a = toCoords(s.orig);
          if (!s.dest) {
            return <circle key={shapeKey(s)} className={`shape-circle ${s.brush}`} cx={a.col + 0.5} cy={a.row + 0.5} r={0.44} />;
          }
          const b = toCoords(s.dest);
          const dx = b.col - a.col;
          const dy = b.row - a.row;
          const len = Math.hypot(dx, dy);
          const ux = dx / len;
          const uy = dy / len;
          const x1 = a.col + 0.5 + ux * 0.33;
          const y1 = a.row + 0.5 + uy * 0.33;
          const x2 = b.col + 0.5 - ux * 0.36;
          const y2 = b.row + 0.5 - uy * 0.36;
          return (
            <g key={shapeKey(s)}>
              <line className={`shape-arrow ${s.brush}`} x1={x1} y1={y1} x2={x2} y2={y2} markerEnd={`url(#arrowhead-${s.brush})`} />
              {s.label && <text className="shape-label" x={b.col + 0.5} y={b.row + 0.5}>{s.label}</text>}
            </g>
          );
        })}
      </svg>

      {promo && (
        <PromotionDialog
          color={promo.color}
          square={promo.to}
          orientation={orientation}
          onPick={(p) => { const { from, to } = promo; setPromo(null); onMove?.(from, to, p); }}
          onCancel={() => setPromo(null)}
        />
      )}
    </div>
  );
}

export { FILES, RANKS };
