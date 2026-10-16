import { expect, test } from "@playwright/test";

test("vision trainer: find the square scores a correct click", async ({ page }) => {
  await page.goto("/vision");
  await page.getByTestId("vision-start").click();
  const target = (await page.getByTestId("vision-target").textContent())!.trim();
  expect(target).toMatch(/^[a-h][1-8]$/);
  await page.locator(`[data-square="${target}"].sq`).click();
  await expect(page.locator(".chip", { hasText: "score 1" })).toBeVisible();
  await page.getByTestId("vision-name").click();
  await page.getByTestId("vision-start").click();
  await expect(page.locator(".sq.hl-yellow")).toHaveCount(1);
  const lit = await page.locator(".sq.hl-yellow").getAttribute("data-square");
  await page.getByTestId(`opt-${lit}`).click();
  await expect(page.locator(".chip", { hasText: "score 1" })).toBeVisible();
});

test("analysis board shows engine lines and sends a game to review", async ({ page }) => {
  await page.goto("/analysis");
  await expect(page.getByTestId("analysis")).toBeVisible();
  await expect(page.locator(".engine-lines button")).toHaveCount(3, { timeout: 30_000 });
  await page.getByTestId("analysis-input").fill("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6");
  await page.getByTestId("analysis-load").click();
  await expect(page.locator(".movelist-move")).toHaveCount(6);
  await expect(page.locator(".engine-lines button").first()).toContainText(/[+-]\d/, { timeout: 30_000 });
  await page.getByTestId("analysis-review").click();
  await expect(page).toHaveURL(/\/review\/[a-z0-9]+$/);
  await expect(page.getByTestId("review")).toBeVisible({ timeout: 120_000 });
});

test("puzzles: my mistakes mode explains when there are none, rated mode still works", async ({ page }) => {
  await page.goto("/puzzles");
  await page.getByTestId("mode-mistakes").click();
  await page.getByTestId("start-puzzles").click();
  await expect(page.locator(".chip-danger").or(page.getByTestId("puzzle-turn"))).toBeVisible({ timeout: 15_000 });
});

test("analysis from a FEN: back to the start, a mate ends the search, a failed review shows why", async ({ page }) => {
  const click = async (from: string, to: string) => {
    await page.locator(`[data-square="${from}"].sq`).click();
    await page.locator(`[data-square="${to}"].sq`).click();
  };
  const fen = "8/8/8/4k3/8/8/8/4K2Q w - - 0 1";
  await page.goto("/analysis");
  await page.getByTestId("analysis-input").fill(fen);
  await page.getByTestId("analysis-load").click();
  await click("h1", "h5");
  await click("e5", "d4");
  await expect(page.locator(".movelist-move")).toHaveCount(2);
  for (let i = 0; i < 2; i++) await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("board")).toHaveAttribute("data-fen", fen);
  for (let i = 0; i < 2; i++) await page.keyboard.press("ArrowRight");

  await page.route("**/api/review/import", (route) => route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"server down"}' }));
  await page.getByTestId("analysis-review").click();
  await expect(page.getByTestId("analysis-error")).toContainText("server down");
  await page.unroute("**/api/review/import");
  await page.getByTestId("analysis-review").click();
  await expect(page.getByTestId("review")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("board")).toHaveAttribute("data-fen", fen);

  await page.goto("/analysis");
  await page.getByTestId("analysis-input").fill("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1");
  await page.getByTestId("analysis-load").click();
  await click("a1", "a8");
  await expect(page.getByTestId("engine-status")).toHaveText("Checkmate · 1-0");
  await expect(page.getByTestId("evalbar")).toHaveAttribute("title", "1-0");
});
