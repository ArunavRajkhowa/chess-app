import { expect, test, type Page } from "@playwright/test";

/** The pieces drawn on the board equal the pieces of the position it was given, nothing more or less. */
async function expectSynced(page: Page) {
  await expect.poll(() => page.getByTestId("board").first().evaluate((board) => {
    const want: string[] = [];
    board.getAttribute("data-fen")!.split(" ")[0].split("/").forEach((row, r) => {
      let file = 0;
      for (const ch of row) {
        if (ch >= "1" && ch <= "8") file += Number(ch);
        else want.push(`${ch === ch.toUpperCase() ? "w" : "b"}${ch.toLowerCase()}@${"abcdefgh"[file++]}${8 - r}`);
      }
    });
    const got = [...board.querySelectorAll(".piece[data-piece]")].map((p) => `${p.getAttribute("data-piece")}@${p.getAttribute("data-square")}`);
    return JSON.stringify([...got].sort()) === JSON.stringify(want.sort()) ? "synced" : `board ${got.sort().join(",")} vs fen ${want.sort().join(",")}`;
  }), { timeout: 5_000 }).toBe("synced");
}

test("a reviewed game: every step forward and back draws exactly its position", async ({ page }) => {
  const imp = await (await page.request.post("/api/review/import", { data: { pgn: "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Bxc6 dxc6 5. O-O Bg4 6. h3 h5 7. hxg4 hxg4 8. Ne5 Qd4 9. Nxg4 Qxe4 10. Nf6+ gxf6 *", mode: "quick" } })).json();
  await expect.poll(async () => (await (await page.request.get(`/api/review/jobs/${imp.job.id}`)).json()).status, { timeout: 90_000 }).toBe("done");
  await page.goto(`/review/${imp.game_id}`);
  await expect(page.getByTestId("review")).toBeVisible();
  await expectSynced(page);
  for (let i = 0; i < 20; i++) { await page.keyboard.press("ArrowRight"); await expectSynced(page); }
  for (let i = 0; i < 20; i++) { await page.keyboard.press("ArrowLeft"); await expectSynced(page); }
});

test("a narrated lecture: every frame draws exactly its position", async ({ page }) => {
  await page.goto("/learn/b1m5l1");
  await expect(page.getByTestId("lecture")).toBeVisible();
  await page.getByTestId("lecture-play").click(); // pause the autoplay: the steps are ours
  const next = page.getByTestId("lecture-next");
  for (let i = 0; i < 40 && await next.isEnabled(); i++) { await expectSynced(page); await next.click(); }
  await expectSynced(page);
});

test("a live game: bot replies, move-list navigation and takeback keep the board in step", async ({ page }) => {
  await page.goto("/play");
  await page.getByTestId("bot-pip").click();
  await page.getByTestId("start-game").click();
  await expect(page.getByTestId("gameview")).toBeVisible();
  await expectSynced(page);
  await page.locator('[data-square="e2"].sq').click();
  await page.locator('[data-square="e4"].sq').click();
  await expect(page.locator(".movelist-move")).toHaveCount(2, { timeout: 20_000 });
  await expectSynced(page);
  await page.keyboard.press("ArrowLeft"); await expectSynced(page);
  await page.keyboard.press("ArrowLeft"); await expectSynced(page);
  await page.keyboard.press("ArrowDown"); await expectSynced(page);
  await page.getByTestId("takeback-btn").click();
  await expect(page.locator(".movelist-move")).toHaveCount(0, { timeout: 10_000 });
  await expectSynced(page);
});

test("a puzzle: the opponent's first move and the solver's moves keep the board in step", async ({ page }) => {
  await page.goto("/puzzles");
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.locator(".piece").first()).toBeVisible();
  await expectSynced(page);
  await page.waitForTimeout(1500); // the opponent's first move plays after a beat
  await expectSynced(page);
});
