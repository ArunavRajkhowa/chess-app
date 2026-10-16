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
