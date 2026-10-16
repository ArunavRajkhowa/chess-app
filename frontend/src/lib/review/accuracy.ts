/* Game accuracy in the browser, the same formula as backend/review/classify.py, so the retry
   flow can say "your accuracy would have been N%" without a round trip. */
export function gameAccuracy(winPercents: number[], moveAccuracies: number[]): number {
  if (!moveAccuracies.length) return 100;
  const n = winPercents.length;
  const window = Math.max(2, Math.min(8, Math.floor(n / 10)));
  const weights = moveAccuracies.map((_, i) => {
    const lo = Math.max(0, i + 1 - window);
    const w = winPercents.slice(lo, i + 2);
    const mean = w.reduce((a, b) => a + b, 0) / w.length;
    const variance = w.reduce((a, b) => a + (b - mean) ** 2, 0) / w.length;
    return Math.max(0.5, Math.min(12, Math.sqrt(variance)));
  });
  const weighted = moveAccuracies.reduce((a, acc, i) => a + acc * weights[i], 0) / weights.reduce((a, b) => a + b, 0);
  const harmonic = moveAccuracies.length / moveAccuracies.reduce((a, acc) => a + 1 / Math.max(acc, 0.01), 0);
  return Math.round(((weighted + harmonic) / 2) * 10) / 10;
}
