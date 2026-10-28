import { expect, test, type Page } from "@playwright/test";
import { Chess } from "chess.js";

/** Every board meant to take a move takes one: a slow, real-mouse drag of a legal move changes the board. */

async function dragLike(page: Page, from: string, to: string) {
  const board = page.getByTestId("board").first();
  const box = (await board.boundingBox())!;
  const white = (await board.getAttribute("data-orientation")) === "white";
  const at = (sq: string) => {
    const f = sq.charCodeAt(0) - 97;
    const r = Number(sq[1]) - 1;
    const col = white ? f : 7 - f;
    const row = white ? 7 - r : r;
    return { x: box.x + (col + 0.5) * (box.width / 8), y: box.y + (row + 0.5) * (box.height / 8) };
  };
  const a = at(from);
  const b = at(to);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(b.x, b.y, { steps: Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 3) });
  await page.mouse.up();
}

/** The board shows dots for a legal move of the side it faces, and a drag of it changes the board or gets a verdict. */
async function assertTakesAMove(page: Page, { eitherSide = false } = {}) {
  const board = page.getByTestId("board").first();
  await expect(board).toBeVisible();
  // wait for the side to move to be the side the board faces (a puzzle first plays the opponent's move)
  if (!eitherSide) await expect.poll(async () => (await board.getAttribute("data-fen"))!.split(" ")[1] === ((await board.getAttribute("data-orientation")) === "white" ? "w" : "b"), { timeout: 15_000 }).toBe(true);
  const fen = (await board.getAttribute("data-fen"))!;
  const move = new Chess(fen).moves({ verbose: true })[0];
  expect(move, `no legal move on ${fen}`).toBeTruthy();
  await page.locator(`[data-square="${move.from}"].sq`).first().click();
  await expect(page.locator(".sq.dest").first(), `no move dots on ${fen}`).toBeVisible();
  await page.locator(`[data-square="${move.from}"].sq`).first().click(); // clear the selection again
  await board.evaluate((el) => {
    const w = window as unknown as { fenChanged: boolean };
    w.fenChanged = false;
    new MutationObserver(() => { w.fenChanged = true; }).observe(el, { attributes: true, attributeFilter: ["data-fen"] });
  });
  await dragLike(page, move.from, move.to);
  // a task answers a wrong move with a verdict and keeps its position
  const verdict = page.locator('[data-testid="task-bad"], [data-testid="task-ok"]');
  await expect.poll(async () => (await page.evaluate(() => (window as unknown as { fenChanged: boolean }).fenChanged)) || (await verdict.count()) > 0, { message: `drag ${move.from}-${move.to} on ${fen}`, timeout: 10_000 }).toBe(true);
}

const errors: string[] = [];
test.beforeEach(({ page }) => {
  errors.length = 0;
  page.on("pageerror", (e) => errors.push(e.message));
});
test.afterEach(() => expect(errors, "page errors").toEqual([]));

test("board demo", async ({ page }) => {
  await page.goto("/dev/board");
  await assertTakesAMove(page);
});

test("a game against a bot", async ({ page }) => {
  const game = await (await page.request.post("/api/play/games", { data: { bot_id: "pip", player_color: "white" } })).json();
  await page.goto(`/play/${game.id}`);
  await assertTakesAMove(page);
});

test("rated puzzles", async ({ page }) => {
  await page.goto("/puzzles");
  await page.getByTestId("start-puzzles").click();
  await expect(page.getByTestId("puzzle-turn")).toBeVisible({ timeout: 20_000 });
  await assertTakesAMove(page);
});

test("analysis board", async ({ page }) => {
  await page.goto("/analysis");
  await assertTakesAMove(page);
});

test("endgame trainer", async ({ page }) => {
  await page.goto("/endgames");
  await page.getByTestId("eg-mate-two-rooks").click();
  await assertTakesAMove(page);
});

test("master game, explored after pausing", async ({ page }) => {
  const games = await (await page.request.get("/api/games")).json();
  const id = (Array.isArray(games) ? games : games.games)[0].id;
  await page.goto(`/games/${id}`);
  await page.getByTestId("lecture-end").click();
  await page.keyboard.press("ArrowLeft"); // the last frame may be mate: step back one move
  await assertTakesAMove(page, { eitherSide: true }); // exploring a game moves either side
});

test("a lesson challenge", async ({ page }) => {
  await page.goto("/learn/b0m3l2");
  await page.getByTestId("lecture-end").click();
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("your-turn")).toBeVisible();
  await assertTakesAMove(page);
});

test("the Fischer lesson opens on move 30, not the start", async ({ page }) => {
  await page.goto("/learn/b8m1l1");
  await page.getByTestId("lecture-next").click();
  await page.getByTestId("lecture-next").click(); // the third paragraph is about 30.Bxf7+
  await expect(page.getByTestId("board")).toHaveAttribute("data-fen", "r4bk1/1bq1rppp/8/1pp1N3/4PQ2/1B5P/5PP1/3RR1K1 w - - 6 30");
});

// One lesson per band: its watch step, paused at the end, takes a move ("why not this one?").
for (const lessonId of ["b0m1l1", "b1m1l1", "b2m1l1", "b3m1l1", "b4m1l1", "b5m1l1", "b6m1l1", "b7m1l1", "b8m1l1"]) {
  test(`lesson ${lessonId} watch step`, async ({ page }) => {
    await page.goto(`/learn/${lessonId}`);
    await page.getByTestId("lecture-end").click();
    await assertTakesAMove(page);
  });
}
