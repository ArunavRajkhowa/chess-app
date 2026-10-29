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
  // a real mouse reports a few pixels per event: big jumps once hid a drag that never started
  await page.mouse.move(b.x, b.y, { steps: Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 3) });
  await page.mouse.up();
}

async function clickMove(page: Page, from: string, to: string) {
  await page.locator(`[data-square="${from}"].sq`).click();
  await page.locator(`[data-square="${to}"].sq`).click();
}

test("a slow one-square drag plays the move", async ({ page }) => {
  await page.goto("/dev/board");
  await dragMove(page, "e2", "e3");
  await expect(page.getByTestId("demo-fen")).toContainText("rnbqkbnr/pppppppp/8/8/8/4P3/PPPP1PPP/RNBQKBNR b");
});

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

test("click to select, click a box to move, click again to clear", async ({ page }) => {
  await page.goto("/dev/board");
  const sq = (s: string) => page.locator(`[data-square="${s}"].sq`);
  // a knight in the start position has two destination boxes
  await sq("b1").click();
  await expect(sq("b1")).toHaveClass(/selected/);
  await expect(page.locator(".sq.dest")).toHaveCount(2);
  await expect(sq("a3")).toHaveClass(/dest/);
  await expect(sq("c3")).toHaveClass(/dest/);
  // the selected piece clicked again clears the selection
  await sq("b1").click();
  await expect(page.locator(".sq.selected")).toHaveCount(0);
  await expect(page.locator(".sq.dest")).toHaveCount(0);
  // an empty square that is not a destination clears it
  await sq("g1").click();
  await expect(page.locator(".sq.dest")).toHaveCount(2);
  await sq("d5").click();
  await expect(page.locator(".sq.selected")).toHaveCount(0);
  // another own piece switches the selection
  await sq("g1").click();
  await sq("e2").click();
  await expect(sq("e2")).toHaveClass(/selected/);
  await expect(sq("g1")).not.toHaveClass(/selected/);
  await expect(page.locator(".sq.dest")).toHaveCount(2); // e3, e4
  // Escape clears
  await page.keyboard.press("Escape");
  await expect(page.locator(".sq.selected")).toHaveCount(0);
  // click-click moves
  await sq("e2").click();
  await sq("e4").click();
  await expect(page.getByTestId("demo-pgn")).toContainText("1. e4");
  await expect(page.locator(".sq.selected")).toHaveCount(0);
  // a press with a small wobble is a click, not a drag onto the next square
  const box = (await sq("e7").boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 4, box.y + box.height / 2 + 3, { steps: 2 });
  await page.mouse.up();
  await expect(sq("e7")).toHaveClass(/selected/);
  await expect(page.locator(".sq.dest")).toHaveCount(2);
});

test("keyboard: arrows move the focus ring, Enter selects and moves", async ({ page }) => {
  await page.goto("/dev/board");
  await page.getByTestId("board").focus();
  await page.keyboard.press("ArrowUp"); // first arrow lands on e1
  await expect(page.locator('[data-square="e1"].sq')).toHaveClass(/kbd-focus/);
  await page.keyboard.press("ArrowUp"); // e2
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-square="e2"].sq')).toHaveClass(/selected/);
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowUp"); // e4
  await page.keyboard.press(" ");
  await expect(page.getByTestId("demo-pgn")).toContainText("1. e4");
  await page.keyboard.press("Escape");
  await expect(page.locator(".sq.kbd-focus")).toHaveCount(0);
});

test("every piece type draws from the page's own CSS, never a separate image request", async ({ page }) => {
  const pieceRequests: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/pieces/")) pieceRequests.push(r.url()); });
  await page.goto("/analysis");
  await expect(page.locator(".piece")).toHaveCount(32);
  const images = await page.locator(".piece").evaluateAll((els) => [...new Set(els.map((e) => getComputedStyle(e).backgroundImage))]);
  expect(images).toHaveLength(12);
  for (const img of images) expect(img).toMatch(/^url\("data:image\/svg\+xml/);
  expect(pieceRequests).toEqual([]);
});
