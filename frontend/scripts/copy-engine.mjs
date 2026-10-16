// Copies the single-threaded WASM Stockfish build from node_modules into public/engine so the
// browser can load it as a Web Worker without cross-origin-isolation headers.
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "node_modules", "stockfish", "src");
const dest = join(here, "..", "public", "engine");
mkdirSync(dest, { recursive: true });
const files = readdirSync(src).filter((f) => f.includes("-lite-single-"));
if (files.length === 0) throw new Error(`no lite-single engine build in ${src}`);
for (const f of files) copyFileSync(join(src, f), join(dest, f));
const js = files.find((f) => f.endsWith(".js"));
// A manifest so the app knows the hashed file name without a glob at runtime.
const manifest = JSON.stringify({ worker: `/engine/${js}` });
import("node:fs").then(({ writeFileSync }) => writeFileSync(join(dest, "manifest.json"), manifest));
console.log(`engine copied: ${files.join(", ")} -> ${existsSync(dest) ? dest : "?"}`);
