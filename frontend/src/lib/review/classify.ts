import type { Classification } from "../api";

/* Live move feedback in the browser: the same win% drop ladder as the backend
   (backend/review/classify.py). Brilliant/great/miss need deeper context and stay server-side. */
export const EXCELLENT_MAX_DROP = 2;
export const GOOD_MAX_DROP = 5;
export const INACCURACY_MAX_DROP = 10;
export const MISTAKE_MAX_DROP = 20;

export function classifyDrop(winBefore: number, winAfter: number, isBest: boolean): Classification {
  if (isBest) return "best";
  const drop = Math.max(0, winBefore - winAfter);
  if (drop <= EXCELLENT_MAX_DROP) return "excellent";
  if (drop <= GOOD_MAX_DROP) return "good";
  if (drop <= INACCURACY_MAX_DROP) return "inaccuracy";
  if (drop <= MISTAKE_MAX_DROP) return "mistake";
  return "blunder";
}

export const CLASS_LABEL: Record<Classification, string> = {
  brilliant: "Brilliant", great: "Great move", best: "Best move", excellent: "Excellent", good: "Good",
  book: "Book move", inaccuracy: "Inaccuracy", mistake: "Mistake", miss: "Missed win", blunder: "Blunder", forced: "Forced",
};
