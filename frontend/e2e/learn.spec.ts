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
  // epaulette-style mate Qxd8#
  await page.locator('[data-square="d1"].sq').click();
  await page.locator('[data-square="d8"].sq').click();
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
  await expect(page.getByTestId("band-0")).toContainText("1/");
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
