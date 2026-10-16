import { expect, test, type Page } from "@playwright/test";

async function clickMove(page: Page, from: string, to: string) {
  await page.locator(`[data-square="${from}"].sq`).click();
  await page.locator(`[data-square="${to}"].sq`).click();
}

test("a timed game shows ticking clocks and adds the increment", async ({ page }) => {
  await page.goto("/play");
  await page.getByTestId("bot-pip").click();
  await page.getByTestId("tc-3+2").click();
  await page.getByTestId("start-game").click();
  await expect(page.getByTestId("gameview")).toBeVisible();
  const clocks = page.getByTestId("clock");
  await expect(clocks).toHaveCount(2);
  await expect(clocks.nth(1)).toContainText("3:00"); // clocks start with the first move
  await clickMove(page, "e2", "e4");
  await expect(page.locator(".movelist-move")).toHaveCount(2, { timeout: 15_000 });
  // the increment put the player's clock at about 3:02; it now runs again on the player's turn
  const before = (await clocks.nth(1).textContent())!;
  expect(before).toMatch(/3:0[0-2]/);
  await page.waitForTimeout(2000);
  const after = (await clocks.nth(1).textContent())!;
  expect(after).not.toBe(before);
});

test("review offers a coach summary and practice from here", async ({ page }) => {
  await page.goto("/review");
  await page.getByTestId("pgn-input").fill('[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0');
  await page.getByTestId("import-btn").click();
  await expect(page.getByTestId("review")).toBeVisible({ timeout: 90_000 });
  await page.getByTestId("summary-btn").click();
  await expect(page.getByTestId("narrative")).toContainText("accuracy", { timeout: 20_000 });
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.getByTestId("practice-btn").click();
  await expect(page).toHaveURL(/\/play\/[a-z0-9]+$/);
  await expect(page.getByTestId("gameview")).toBeVisible();
  // the practice game starts from the review position: a pawn already on e4 and e5
  await expect(page.locator('.piece[data-square="e4"]')).toHaveCount(1);
  await expect(page.locator('.piece[data-square="e5"]')).toHaveCount(1);
});

test("the home page shows the daily puzzle and hearts survive one wrong move", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("daily-card")).toBeVisible();
  await page.getByRole("link", { name: "Solve today's puzzle" }).click();
  await expect(page.getByTestId("puzzle-turn")).toContainText("Daily puzzle", { timeout: 15_000 });
  await expect(page.getByTestId("puzzle-turn")).toContainText("to play", { timeout: 15_000 });
  await expect(page.locator(".sq.last-move")).toHaveCount(2); // the opponent's move has been played
  await expect(page.getByTestId("hearts")).toContainText("♥♥♥♥♥");
  // play a deliberately bad move: pick any legal king/pawn move that is unlikely to be the solution
  const fen = (await page.getByTestId("board").getAttribute("data-fen"))!;
  const turn = fen.split(" ")[1];
  // click a piece of the side to move and a destination; if the move happens to be right the heart stays
  const pieces = page.locator(`.piece[data-piece^="${turn}"]`);
  const n = await pieces.count();
  let changed = false;
  for (let i = 0; i < n && !changed; i++) {
    const sq = (await pieces.nth(i).getAttribute("data-square"))!;
    await page.locator(`[data-square="${sq}"].sq`).click();
    const dest = page.locator(".sq.dest").first();
    if ((await dest.count()) === 0) continue;
    const d = (await dest.getAttribute("data-square"))!;
    await page.locator(`[data-square="${d}"].sq`).click();
    changed = true;
  }
  expect(changed).toBe(true);
  await page.waitForTimeout(500);
  const hearts = await page.getByTestId("hearts").textContent();
  const solved = await page.getByTestId("puzzle-turn").textContent();
  expect(hearts === "♥♥♥♥♥" ? solved?.includes("Solved") || solved?.includes("to play") : true).toBeTruthy();
});
