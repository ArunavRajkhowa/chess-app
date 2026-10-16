import { lineScoreText, winPercent } from "../../lib/engine/uci";
import "./EvalBar.css";

interface Props {
  cp?: number;
  mate?: number;
  orientation: "white" | "black";
  loading?: boolean;
}

/** Vertical evaluation bar; white's share grows from the bottom when white is at the bottom. */
export function EvalBar({ cp, mate, orientation, loading }: Props) {
  const has = cp !== undefined || mate !== undefined;
  const white = has ? winPercent({ cp, mate }) : 50;
  const text = has ? lineScoreText({ cp, mate }) : "";
  const whiteOnTop = orientation === "black";
  return (
    <div className={`evalbar ${whiteOnTop ? "flipped" : ""} ${loading ? "loading" : ""}`} data-testid="evalbar" title={text}>
      <div className="evalbar-white" style={{ height: `${white}%` }} />
      <span className={`evalbar-text ${white >= 50 ? "on-white" : "on-black"}`}>{text}</span>
    </div>
  );
}
