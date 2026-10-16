import { expect, test, type Page } from "@playwright/test";

async function clickMove(page: Page, from: string, to: string) {
  await page.locator(`[data-square="${from}"].sq`).click();
  await page.locator(`[data-square="${to}"].sq`).click();
}

test("play a game against Pip: moves, bot replies, hint, resign, review link", async ({ page }) => {
  await page.goto("/play");
  await expect(page.getByTestId("botpicker")).toBeVisible();
  await page.getByTestId("bot-pip").click();
  await page.getByTestId("start-game").click();
  await expect(page).toHaveURL(/\/play\/[a-z0-9]+$/);
  await expect(page.getByTestId("gameview")).toBeVisible();
  await expect(page.locator(".piece")).toHaveCount(32);

  const wasmErrors: string[] = [];
  page.on("pageerror", (err) => wasmErrors.push(err.message));
  await clickMove(page, "e2", "e4");
  // the bot answers within a couple of seconds; the move list then has two plies
  await expect(page.locator(".movelist-move")).toHaveCount(2, { timeout: 15_000 });
  // the browser engine evaluates the live position for the eval bar
  await expect(page.getByTestId("evalbar")).toHaveAttribute("title", /[+-]\d|M\d/, { timeout: 15_000 });
  await clickMove(page, "d2", "d4");
  await expect(page.locator(".movelist-move")).toHaveCount(4, { timeout: 15_000 });

  await page.getByTestId("hint-btn").click();
  await expect(page.getByTestId("hint")).toBeVisible();

  // navigation through the move list does not break the live game
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".chip-warn", { hasText: "viewing move" })).toBeVisible();
  await page.keyboard.press("ArrowDown");

  page.once("dialog", (d) => d.accept());
  await page.getByTestId("resign-btn").click();
  await expect(page.getByTestId("result")).toContainText("Pip won");
  await expect(page.getByTestId("review-btn")).toBeVisible();
  await page.screenshot({ path: "test-results/play-finished.png", fullPage: true });
  expect(wasmErrors, "no uncaught errors from the engine worker").toEqual([]);
});

test("takeback undoes the player's move and the bot's reply", async ({ page }) => {
  await page.goto("/play");
  await page.getByTestId("bot-luna").click();
  await page.getByTestId("start-game").click();
  await expect(page.getByTestId("gameview")).toBeVisible();
  await clickMove(page, "g1", "f3");
  await expect(page.locator(".movelist-move")).toHaveCount(2, { timeout: 15_000 });
  await page.getByTestId("takeback-btn").click();
  await expect(page.locator(".movelist-move")).toHaveCount(0, { timeout: 10_000 });
  await expect(page.locator(".piece")).toHaveCount(32);
});
