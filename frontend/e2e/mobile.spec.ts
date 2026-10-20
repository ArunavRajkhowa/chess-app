import { devices, expect, test } from "@playwright/test";

const ROUTES = ["/", "/play", "/puzzles", "/learn", "/openings", "/games", "/insights", "/endgames", "/vision", "/analysis", "/review", "/coach", "/settings"];

test.use({ ...devices["Pixel 7"] });

test("installable: the manifest parses and lists 192 and 512 icons that load", async ({ page, request }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="manifest"]').getAttribute("href");
  expect(href).toBeTruthy();
  const manifest = await (await request.get(href!)).json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.map((i: { sizes: string }) => i.sizes)).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  for (const icon of manifest.icons) expect((await request.get(icon.src)).ok()).toBe(true);
});

for (const route of ROUTES) {
  test(`no sideways scroll on a phone: ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    // Mobile Chrome zooms out to fit wide content, so compare with the device width, not innerWidth.
    const scrollWidth = await page.evaluate(() => document.scrollingElement!.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(page.viewportSize()!.width);
  });
}
