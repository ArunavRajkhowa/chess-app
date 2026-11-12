import { expect, test } from "@playwright/test";

test("right-click leaves a note that knows the page; the board keeps its own right-click", async ({ page }) => {
  await page.goto("/analysis");
  const composer = page.getByRole("dialog", { name: "Leave a note" });
  await page.getByTestId("board").click({ button: "right" });
  await expect(composer).toBeHidden(); // right-click on the board draws arrows

  await page.getByRole("heading", { name: "Engine" }).click({ button: "right" });
  await expect(composer).toBeVisible();
  await expect(composer).toContainText("/analysis · Engine");
  await composer.getByText("Idea", { exact: true }).click();
  await composer.getByRole("textbox", { name: "Your note" }).fill("a button to copy the FEN");
  const sent = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/notes");
  await composer.getByRole("button", { name: "Send note" }).click();
  expect((await sent).request().postDataJSON()).toMatchObject({ page: "/analysis", anchor: "Engine", kind: "idea", note: "a button to copy the FEN" });
  await expect(composer).toBeHidden();
  await expect(page.getByRole("status")).toContainText("Note sent");
});

test("the pencil opens the composer and Escape closes it", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Leave a note" }).click();
  const composer = page.getByRole("dialog", { name: "Leave a note" });
  await expect(composer.getByRole("textbox", { name: "Your note" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(composer).toBeHidden();
});
