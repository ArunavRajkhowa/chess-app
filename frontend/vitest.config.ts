// Unit tests only (vitest ships its own vite, so it stays out of vite.config.ts).
import { defineConfig } from "vitest/config";

export default defineConfig({ test: { environment: "jsdom", include: ["src/**/*.test.ts"] } });
