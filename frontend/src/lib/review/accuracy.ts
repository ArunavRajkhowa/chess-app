/* Game accuracy in the browser, the same formula as backend/review/classify.py, so the retry
   flow can say "your accuracy would have been N%" without a round trip. */

/** lichess's weight for each move (one per ply): the standard deviation of White's win% over a
    window of positions ending at that move, clamped to 0.5..12. Input has one entry per position. */
export function volatilityWeights(winPercentsWhiteView: number[]): number[] {
  const wp = winPercentsWhiteView;
  const window = Math.max(2, Math.min(8, Math.floor(wp.length / 10)));
  const first = wp.slice(0, window);
  const windows = [...Array<number[]>(window - 2).fill(first), ...Array.from({ length: wp.length - window + 1 }, (_, i) => wp.slice(i, i + window))];
  return windows.map((w) => {
    const mean = w.reduce((a, b) => a + b, 0) / w.length;
    const variance = w.reduce((a, b) => a + (b - mean) ** 2, 0) / w.length;
    return Math.max(0.5, Math.min(12, Math.sqrt(variance)));
  });
}

/** One side's game accuracy: the mean of the volatility-weighted average and the harmonic mean of
    its move accuracies. `weights` are volatilityWeights at that side's plies. */
export function gameAccuracy(moveAccuracies: number[], weights: number[]): number {
  const weighted = moveAccuracies.reduce((a, acc, i) => a + acc * weights[i], 0) / weights.reduce((a, b) => a + b, 0);
  const harmonic = moveAccuracies.length / moveAccuracies.reduce((a, acc) => a + 1 / Math.max(acc, 0.01), 0);
  return Math.round(((weighted + harmonic) / 2) * 10) / 10;
}
