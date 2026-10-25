import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const playerCookie = async (context: BrowserContext) => (await context.cookies()).filter((c) => c.name === "player");

const eventSent = (page: Page, name: string) =>
  page.waitForResponse((r) => new URL(r.url()).pathname === "/api/events" && r.request().postDataJSON().name === name);

test("a first visit is one guest, and the app's opens and page views are recorded", async ({ page, context }) => {
  const opened = eventSent(page, "app.opened");
  const viewed = eventSent(page, "page.viewed");
  const pageResponse = await page.goto("/puzzles");
  // the page itself brings the cookie, or the parallel first calls each mint a guest and the last to land wins
  expect(await pageResponse!.headerValue("set-cookie")).toContain("player=");
  expect((await opened).status()).toBe(200);
  expect((await viewed).status()).toBe(200);
  expect((await viewed).request().postDataJSON().props).toEqual({ page: "puzzles" });
  const cookies = await playerCookie(context);
  expect(cookies).toHaveLength(1);
  expect(cookies[0].httpOnly).toBe(true);
});

test("delete my data starts a new guest", async ({ page, context }) => {
  await page.goto("/settings");
  await expect(page.getByTestId("account")).toContainText("guest");
  const before = (await playerCookie(context))[0].value;
  page.once("dialog", (d) => d.accept());
  await page.getByTestId("delete-account").click();
  await expect.poll(async () => (await playerCookie(context))[0]?.value).not.toBe(before);
  await expect(page.getByTestId("account")).toContainText("guest");
});
