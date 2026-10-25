import { expect, test } from "@playwright/test";

test("a goal becomes a study plan whose steps link into the app, and a play step carries Guide me", async ({ page }) => {
  await page.goto("/plan");
  await expect(page.getByTestId("plans-empty")).toBeVisible();
  await page.getByTestId("goal-input").fill("Sicilian for both sides");
  await page.getByTestId("goal-submit").click();
  await expect(page).toHaveURL(/\/plan\/[a-z0-9]+$/, { timeout: 60_000 });
  await expect(page.getByTestId("plan-title")).toContainText("Sicilian Defense for both sides");
  await expect(page.getByTestId("plan-points")).toContainText("bishop");
  expect(await page.getByTestId("plan-step").count()).toBeGreaterThan(10);
  await expect(page.getByTestId("plan-group-play")).toContainText("as white");
  await expect(page.getByTestId("plan-group-play")).toContainText("as black");
  // a course line is ticked by hand; the count moves
  await expect(page.getByTestId("plan-progress")).toContainText("0 of");
  await page.getByTestId("step-tick").first().click();
  await expect(page.getByTestId("plan-progress")).toContainText("1 of");
  // the plan is listed, and a play step lands on the picker with the specialist chosen
  await page.goto("/plan");
  await expect(page.getByTestId("plan-list")).toContainText("Sicilian");
  await page.getByRole("link", { name: /Sicilian Defense for both sides/ }).click();
  await page.getByTestId("step-play").first().click();
  await expect(page).toHaveURL(/\/play\?bot=opening-sicilian-dragon-\d+&color=white&guide=1/);
  await expect(page.getByTestId("start-game")).toContainText("Dragon", { timeout: 20_000 });
  await page.getByTestId("start-game").click();
  await expect(page.getByTestId("gameview")).toBeVisible();
  await expect(page.getByTestId("guide-toggle")).toBeChecked();
  await page.locator('[data-square="e2"].sq').click();
  await page.locator('[data-square="e4"].sq').click();
  await expect(page.getByTestId("guide")).toContainText("book move", { timeout: 20_000 });
});

test("an unknown goal gets no plan and the closest openings", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("goalbar")).toBeVisible();
  await page.getByTestId("goal-input").fill("the Sicillian");
  await page.getByTestId("goal-submit").click();
  await expect(page.getByTestId("plan-none")).toContainText("Nothing", { timeout: 30_000 });
  await expect(page.getByTestId("closest-family").first()).toContainText("Sicilian Defense");
  await page.getByTestId("closest-family").first().click();
  await expect(page).toHaveURL(/\/plan\/[a-z0-9]+$/, { timeout: 60_000 });
});

test("the play page filters the bots by specialty", async ({ page }) => {
  await page.goto("/play");
  await expect(page.getByTestId("bot-pip")).toBeVisible();
  await page.getByTestId("bot-filter-endgame").click();
  await expect(page.getByTestId("bot-endgame-rook-1400")).toBeVisible();
  await expect(page.getByTestId("bot-pip")).toHaveCount(0);
  await page.getByTestId("bot-endgame-rook-1400").click();
  await expect(page.getByTestId("start-game")).toContainText("Rook endgames");
  await page.getByTestId("bot-filter-classic").click();
  await expect(page.getByTestId("bot-pip")).toBeVisible();
});
