import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { Chess } from "chess.js";
import type { GameReport } from "../src/lib/api";

async function reviewed(request: APIRequestContext, pgn: string): Promise<{ id: string; report: GameReport }> {
  const imp = await (await request.post("/api/review/import", { data: { pgn, mode: "quick" } })).json();
  await expect.poll(async () => (await (await request.get(`/api/review/jobs/${imp.job.id}`)).json()).status, { timeout: 60_000 }).toBe("done");
  const r = await (await request.get(`/api/review/games/${imp.game_id}`)).json();
  return { id: imp.game_id, report: r.report };
}

async function clickMove(page: Page, uci: string) {
  await page.locator(`[data-square="${uci.slice(0, 2)}"].sq`).click();
  await page.locator(`[data-square="${uci.slice(2, 4)}"].sq`).click();
}

test("a game from a FEN starts there, a side with no moves has no accuracy, and retry accepts another mate", async ({ page, request }) => {
  const fen = "6k1/5ppp/8/8/8/8/5PPP/R2R2K1 w - - 0 1"; // Ra8# and Rd8# both mate; 1.Ra7 lets the mate go
  const { id, report } = await reviewed(request, `[SetUp "1"]\n[FEN "${fen}"]\n\n1. Ra7 *`);
  await page.goto(`/review/${id}`);
  await expect(page.getByTestId("review")).toBeVisible();
  await expect(page.getByTestId("board")).toHaveAttribute("data-fen", fen);
  await expect(page.getByTestId("evalbar")).toHaveAttribute("title", "M1");
  await expect(page.getByTestId("acc-black")).toHaveText("–");
  await page.keyboard.press("ArrowRight");
  await page.getByTestId("retry-btn").click();
  await expect(page.getByTestId("board")).toHaveAttribute("data-fen", fen);
  const best = report.moves[0].best_move_uci;
  await clickMove(page, best === "a1a8" ? "d1d8" : "a1a8"); // the mate the engine did not pick
  await expect(page.getByTestId("retry-banner")).toContainText("is checkmate");
});

test("Legal's mate: the bar names mate in 2, a correct retry stays on its move, graph marks stay inside", async ({ page, request }) => {
  const { id, report } = await reviewed(request, "1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5# 1-0");
  const blunder = report.moves[9]; // 5...Bxd1?? allows Bxf7+ Ke7 Nd5#
  expect(blunder.eval_after_text).toBe("M2");
  await page.goto(`/review/${id}`);
  await expect(page.getByTestId("review")).toBeVisible();
  for (let i = 0; i < 10; i++) await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("evalbar")).toHaveAttribute("title", "M2");
  await page.getByTestId("retry-btn").click();
  await clickMove(page, blunder.best_move_uci);
  await expect(page.getByTestId("retry-banner")).toContainText("Correct");
  const after = new Chess(blunder.fen_before);
  after.move({ from: blunder.best_move_uci.slice(0, 2), to: blunder.best_move_uci.slice(2, 4) });
  await expect(page.getByTestId("board")).toHaveAttribute("data-fen", after.fen());
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("evalbar")).toHaveAttribute("title", "1-0");
  const marks = await page.locator('[data-testid="evalgraph"] g').evaluateAll((gs) => gs.map((g) => g.getAttribute("transform")!));
  expect(marks.length).toBeGreaterThan(0);
  for (const t of marks) {
    const [x, y] = t.match(/-?[\d.]+/g)!.map(Number);
    expect(x).toBeLessThanOrEqual(593);
    expect(y).toBeGreaterThanOrEqual(7);
    expect(y).toBeLessThanOrEqual(113);
  }
});
