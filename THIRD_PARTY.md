# Third-party software and data

Chess Coach is licensed under the GNU AGPL-3.0 ([LICENSE](LICENSE)). It ships or runs the following.
Each licence below was read from the item's own notice, package metadata or source header.

## Shipped or run by the app

| What | Where | Licence | Source |
|---|---|---|---|
| Maia-3 5M model (CSSLab, University of Toronto), converted to ONNX | `data/maia/` | AGPL-3.0 | [data/maia/NOTICE](data/maia/NOTICE), https://github.com/CSSLab/maia3 |
| Stockfish (native engine) | Debian `stockfish` package in the Docker image | GPL-3.0 | https://github.com/official-stockfish/Stockfish |
| Stockfish.js 17.1 lite single (WASM build, (c) Chess.com, LLC; npm `stockfish`) | `frontend/public/engine/` | GPL-3.0 (file header) | https://github.com/nmrugg/stockfish.js |
| cburnett piece set by Colin M.L. Burnett | `frontend/src/assets/pieces/cburnett/` | CC BY-SA 3.0 and GPLv2+ | [ATTRIBUTION.md](frontend/src/assets/pieces/ATTRIBUTION.md) |
| lichess chess-openings tables | `data/openings/*.tsv` | CC0 | https://github.com/lichess-org/chess-openings |
| lichess puzzle database (sampled) | `data/puzzles/lichess.jsonl` | CC0 | https://database.lichess.org/ |
| Newsreader font (`@fontsource-variable/newsreader`) | frontend bundle | SIL OFL 1.1 | https://github.com/productiontype/Newsreader |
| Schibsted Grotesk font (`@fontsource-variable/schibsted-grotesk`) | frontend bundle | SIL OFL 1.1 | https://github.com/schibsted/schibsted-grotesk |

## Dependencies

- **Copyleft:** `python-chess` (GPL-3.0+) and `edge-tts` (LGPL-3.0) on the server. Both are
  compatible with AGPL-3.0; their source is on PyPI and their licences come with the package.
- **Permissive, notice required:** these licences require that their copyright notice stays with
  copies. The notices are in each package's `LICENSE` file.
  - Python: FastAPI (MIT), pydantic-settings (MIT), anthropic (MIT), onnxruntime (MIT),
    libsql (MIT), uvicorn (BSD-3-Clause), python-dotenv (BSD-3-Clause), httpx (BSD-3-Clause),
    NumPy (BSD-3-Clause).
  - Browser bundle: React and React DOM (MIT), react-router-dom (MIT), zustand (MIT),
    chess.js (BSD-2-Clause), lucide-react (ISC).
- Build and test tools (Vite, TypeScript, Playwright, Vitest, Capacitor and others in
  `devDependencies`) are not shipped and need no notice here.
