import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

// The cloud dev container ships one Chromium at a fixed path; laptops use Playwright's own.
const PRESET_CHROMIUM = "/opt/pw-browsers/chromium";
const executablePath = process.env.PW_CHROMIUM_PATH ?? (existsSync(PRESET_CHROMIUM) ? PRESET_CHROMIUM : undefined);

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173",
    headless: true,
    viewport: { width: 1280, height: 860 },
    screenshot: "only-on-failure",
    launchOptions: executablePath ? { executablePath } : {},
  },
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : { command: "npm run dev -- --host 127.0.0.1 --port 5173", url: "http://127.0.0.1:5173/dev/board", reuseExistingServer: true, timeout: 60_000 },
});
