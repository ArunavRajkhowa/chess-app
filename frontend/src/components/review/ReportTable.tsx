import type { Classification, SideSummary } from "../../lib/api";
import { CLASS_GLYPH } from "../play/MoveList";

const ROWS: Classification[] = ["brilliant", "great", "best", "excellent", "good", "book", "inaccuracy", "mistake", "miss", "blunder"];
const LABEL: Record<Classification, string> = {
  brilliant: "Brilliant", great: "Great", best: "Best", excellent: "Excellent", good: "Good", book: "Book",
  inaccuracy: "Inaccuracy", mistake: "Mistake", miss: "Miss", blunder: "Blunder", forced: "Forced",
};

export function ReportTable({ white, black, whiteName, blackName }: { white: SideSummary; black: SideSummary; whiteName: string; blackName: string }) {
  return (
    <table className="report" data-testid="report-table">
      <thead>
        <tr><th className="num">{whiteName}</th><th /><th className="num">{blackName}</th></tr>
      </thead>
      <tbody>
        {ROWS.map((c) => (
          <tr key={c} className={white.counts[c] + black.counts[c] === 0 ? "zero" : ""}>
            <td className="num">{white.counts[c]}</td>
            <td><i className={`cls-badge cls-${c}`}>{CLASS_GLYPH[c]}</i> {LABEL[c]}</td>
            <td className="num">{black.counts[c]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
