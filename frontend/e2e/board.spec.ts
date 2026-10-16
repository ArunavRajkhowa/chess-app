import { expect, test, type Page } from "@playwright/test";

async function dragMove(page: Page, from: string, to: string) {
  const board = page.getByTestId("board");
  const box = (await board.boundingBox())!;
  const orientation = await board.getAttribute("data-orientation");
  const center = (sq: string) => {
    const f = sq.charCodeAt(0) - 97;
    const r = Number(sq[1]) - 1;
    const col = orientation === "white" ? f : 7 - f;
    const row = orientation === "white" ? 7 - r : r;
    return { x: box.x + (col + 0.5) * (box.width / 8), y: box.y + (row + 0.5) * (box.height / 8) };
  };
  const a = center(from);
  const b = center(to);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(a.x + 10, a.y + 10, { steps: 3 });
  await page.mouse.move(b.x, b.y, { steps: 8 });
  await page.mouse.up();
}

async function clickMove(page: Page, from: string, to: string) {
  await page.locator(`[data-square="${from}"].sq`).click();
  await page.locator(`[data-square="${to}"].sq`).click();
}

test("board renders 32 pieces and accepts drag and click moves", async ({ page }) => {
  await page.goto("/dev/board");
  await expect(page.locator(".piece")).toHaveCount(32);
  await dragMove(page, "e2", "e4");
  await expect(page.getByTestId("demo-fen")).toContainText("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b");
  await clickMove(page, "e7", "e5");
  await expect(page.getByTestId("demo-fen")).toContainText("4p3/4P3");
  // selecting a piece shows legal destinations
  await page.locator('[data-square="g1"].sq').click();
  await expect(page.locator(".sq.dest")).toHaveCount(3); // f3, h3, e2
  await page.locator('[data-square="f3"].sq').click();
  await expect(page.getByTestId("demo-pgn")).toContainText("1. e4 e5 2. Nf3");
  // illegal drop snaps back and the position is unchanged
  await dragMove(page, "b8", "b4");
  await expect(page.getByTestId("demo-pgn")).toContainText("2. Nf3");
  await expect(page.getByTestId("demo-pgn")).not.toContainText("Nb4");
  // flip keeps the pieces
  await page.getByRole("button", { name: "Flip" }).click();
  await expect(page.getByTestId("board")).toHaveAttribute("data-orientation", "black");
  await dragMove(page, "b8", "c6");
  await expect(page.getByTestId("demo-pgn")).toContainText("Nc6");
});

test("promotion dialog appears and promotes", async ({ page }) => {
  await page.goto("/dev/board");
  // Fast line to a promotion: 1.a4 b5 2.axb5 a6 3.bxa6 c5 4.a7 c4 5.axb8=N
  for (const [f, t] of [["a2", "a4"], ["b7", "b5"], ["a4", "b5"], ["a7", "a6"], ["b5", "a6"], ["c7", "c5"], ["a6", "a7"], ["c5", "c4"]]) {
    await clickMove(page, f, t);
  }
  await clickMove(page, "a7", "b8");
  await expect(page.getByTestId("promo-q")).toBeVisible();
  await page.getByTestId("promo-n").click();
  await expect(page.getByTestId("demo-pgn")).toContainText("axb8=N");
});
