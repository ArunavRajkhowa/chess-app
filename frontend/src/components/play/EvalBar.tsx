import { lineScoreText, winPercent } from "../../lib/engine/uci";
import "./EvalBar.css";

interface Props {
  cp?: number;
  mate?: number;
  /** The game is over: the bar goes to the winner and shows the result. */
  result?: "1-0" | "0-1" | "1/2-1/2";
  orientation: "white" | "black";
  loading?: boolean;
}

/** Vertical evaluation bar; white's share grows from the bottom when white is at the bottom. */
export function EvalBar({ cp, mate, result, orientation, loading }: Props) {
  const has = cp !== undefined || mate !== undefined;
  const white = result ? { "1-0": 100, "0-1": 0, "1/2-1/2": 50 }[result] : has ? winPercent({ cp, mate }) : 50;
  const text = result ? (result === "1/2-1/2" ? "½-½" : result) : has ? lineScoreText({ cp, mate }) : "";
  const label = text.length > 4 ? text.replace(/\.\d$/, "") : text; // the bar fits four characters: "+10.5" shows "+10"
  const whiteOnTop = orientation === "black";
  return (
    <div className={`evalbar ${whiteOnTop ? "flipped" : ""} ${loading ? "loading" : ""}`} data-testid="evalbar" title={text}>
      <div className="evalbar-white" style={{ height: `${white}%` }} />
      <span className={`evalbar-text ${white >= 50 ? "on-white" : "on-black"}`}>{label}</span>
    </div>
  );
}
