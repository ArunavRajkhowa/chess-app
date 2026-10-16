import { expect, test } from "@playwright/test";

test("endgame trainer: mate with two rooks against the engine", async ({ page }) => {
  await page.goto("/endgames");
  await expect(page.getByTestId("endgames")).toBeVisible();
  await page.getByTestId("eg-mate-two-rooks").click();
  await expect(page.getByTestId("eg-title")).toContainText("Two rooks");
  // play the ladder: alternate rook checks; the engine replies each time
  const board = page.getByTestId("board");
  const move = async (from: string, to: string) => { await page.locator(`[data-square="${from}"].sq`).click(); await page.locator(`[data-square="${to}"].sq`).click(); await page.waitForTimeout(700); };
  await move("c1", "c4");
  await expect(page.locator(".chip", { hasText: "moves:" })).toContainText("1", { timeout: 15_000 });
  const fen = await board.getAttribute("data-fen");
  expect(fen).toContain(" w ");
  await page.getByTestId("eg-challenge").click();
  await expect(page.getByTestId("eg-challenge-bar")).toBeVisible();
});
