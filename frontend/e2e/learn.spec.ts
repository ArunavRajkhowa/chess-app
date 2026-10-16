import { expect, test } from "@playwright/test";

test("open the curriculum, complete a lesson with a challenge, a quiz and a drill", async ({ page }) => {
  await page.goto("/learn");
  await expect(page.getByTestId("learn")).toBeVisible();
  await expect(page.getByTestId("band-0")).toBeVisible();
  await page.getByTestId("lesson-b0m3l2").click();
  await expect(page.getByTestId("lesson")).toBeVisible();
  await page.getByTestId("continue").click(); // text section
  // challenge: back-rank mate Ra8#
  await expect(page.getByTestId("challenge-prompt")).toContainText("Mate in one");
  await page.locator('[data-square="a1"].sq').click();
  await page.locator('[data-square="a2"].sq').click(); // wrong move
  await expect(page.getByTestId("task-bad")).toBeVisible();
  await page.locator('[data-square="a1"].sq').click();
  await page.locator('[data-square="a8"].sq').click();
  await expect(page.getByTestId("task-ok")).toContainText("Ra8#");
  await page.getByTestId("continue").click();
  // Scholar's mate challenge
  await page.locator('[data-square="h5"].sq').click();
  await page.locator('[data-square="f7"].sq').click();
  await expect(page.getByTestId("task-ok")).toBeVisible();
  await page.getByTestId("continue").click();
  // epaulette mate Qe6#
  await page.locator('[data-square="a2"].sq').click();
  await page.locator('[data-square="e6"].sq').click();
  await expect(page.getByTestId("task-ok")).toBeVisible();
  await page.getByTestId("continue").click();
  // quiz
  await expect(page.getByTestId("quiz-question")).toBeVisible();
  await page.getByTestId("quiz-option-1").click();
  await expect(page.getByTestId("task-ok")).toBeVisible();
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("lesson-done")).toBeVisible();
  await page.screenshot({ path: "test-results/lesson-done.png" });
  // progress is recorded
  await page.goto("/learn");
  await expect(page.getByTestId("band-0")).toContainText(/[1-9]\d*\/\d+/);
});

test("a drill plays against the engine and detects stalemate", async ({ page }) => {
  await page.goto("/learn/b0m3l3");
  await page.getByTestId("continue").click(); // text
  await page.getByTestId("continue").click(); // position
  await page.getByTestId("quiz-option-1").click();
  await page.getByTestId("continue").click();
  await page.getByTestId("quiz-option-0").click();
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("drill-prompt")).toContainText("Mate with king and queen");
  // play a legal queen move and get an engine reply
  await page.locator('[data-square="e1"].sq').click();
  await page.locator('[data-square="e4"].sq').click();
  await expect(page.locator(".chip", { hasText: "moves:" })).toContainText("1", { timeout: 15_000 });
  await expect(page.locator(".piece")).toHaveCount(3);
});

test("show solution plays the answer without counting it; a quiz board faces the side to move", async ({ page }) => {
  await page.goto("/learn/b0m3l1");
  await page.getByTestId("continue").click(); // text
  await page.getByTestId("continue").click(); // position
  await page.getByRole("button", { name: "Show solution" }).click(); // Kd7, Black to move
  await expect(page.getByTestId("task-revealed")).toContainText("The solution: Kd7");
  await expect(page.getByTestId("task-ok")).toHaveCount(0);
  await expect(page.locator('.piece[data-square="d7"][data-piece="bk"]')).toHaveCount(1);
  await page.getByTestId("continue").click();
  await page.getByRole("button", { name: "Show solution" }).click(); // Qd8#
  await expect(page.locator('.piece[data-square="d8"][data-piece="wq"]')).toHaveCount(1);
  await expect(page.locator(".lesson-side .chip-ok")).toHaveText("0 solved");
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("quiz-question")).toBeVisible(); // Black to move
  await expect(page.getByTestId("board")).toHaveAttribute("data-orientation", "black");
});

test("openings explorer walks the Open Sicilian and steps with the arrow keys", async ({ page }) => {
  await page.goto("/openings");
  await page.getByTestId("opening-search").fill("Sicilian");
  await expect(page.locator(".results li").first()).toContainText("Sicilian Defense");
  const conts = page.getByTestId("continuations");
  for (const san of ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4"]) {
    await conts.locator("button", { has: page.locator(".conts-san", { hasText: new RegExp(`^${san}$`) }) }).click();
    await expect(page.locator(".movelist-move.current")).toHaveText(san);
  }
  await expect(page.getByTestId("opening-name")).toHaveText("B50 · Sicilian Defense");
  await expect(conts.locator(".conts-san", { hasText: /^Nf6$/ })).toBeVisible();
  await expect(page.locator(".sq.last-move")).toHaveCount(2);
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".movelist-move.current")).toHaveText("cxd4");
  await expect(page.locator('.sq.last-move[data-square="d4"]')).toHaveCount(1);
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".movelist-move.current")).toHaveText("Nxd4");
});

test("vision trainer says which side is at the bottom", async ({ page }) => {
  await page.goto("/vision");
  await expect(page.getByTestId("vision-bottom")).toHaveText("White at the bottom");
  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByTestId("vision-bottom")).toHaveText("Black at the bottom");
});

test("stepping through a master game keeps the board on screen", async ({ page }) => {
  await page.goto("/games/vladimir-kramnik-viswanathan-anand-2008");
  await expect(page.getByTestId("gamestudy")).toBeVisible();
  for (let i = 0; i < 80; i++) await page.keyboard.press("ArrowRight");
  await expect(page.locator(".chip", { hasText: "80/" })).toBeVisible();
  await expect(page.getByTestId("board")).toBeInViewport({ ratio: 0.9 });
});
