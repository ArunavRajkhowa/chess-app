import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// BACKEND_URL points the dev server at another backend (a test server with a scratch database).
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8765";

// The page brings the player cookie, as the backend's own page does (backend/app.py), so the
// app's parallel first calls share one guest instead of each minting one. The backend judges the
// page's cookies, so a stale guest or session cookie is replaced here too.
const guestCookie: Plugin = {
  name: "guest-cookie",
  configureServer(server) {
    // Another project on the same port answers /api with 404s, so bots, puzzles and lessons look broken.
    fetch(`${BACKEND}/api/health`, { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json() as Promise<{ engine?: unknown }>)
      .then((h) => { if (!h.engine) throw new Error("the reply is not the chess backend's"); })
      .catch((e) => server.config.logger.error(`\nNo chess backend at ${BACKEND}/api/health (${e.message}). Start it, or set BACKEND_URL to where it runs.\n`));
    server.middlewares.use((req, res, next) => {
      if (!req.headers.accept?.includes("text/html")) return next();
      // A backend that is down or slow must not break the page: serve it without the cookie.
      fetch(`${BACKEND}/api/account`, { headers: { cookie: req.headers.cookie ?? "" }, signal: AbortSignal.timeout(2000) }).then((r) => {
        const cookies = r.headers.getSetCookie();
        if (cookies.length) res.setHeader("Set-Cookie", cookies);
        next();
      }, () => next());
    });
  },
};

export default defineConfig({
  plugins: [react(), guestCookie],
  server: {
    port: 5173,
    proxy: { "/api": { target: BACKEND, changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 1500 },
});
