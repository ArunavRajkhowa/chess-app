# Chess Coach

Play, review and learn chess in one app that runs on your own machine. Twenty bots from 250 to
3200 with personalities, chat and an adaptive coach bot; clocks; chess.com-style Game Review
with accuracy, key moments, retry and practice-from-here; a puzzle trainer with ratings, Puzzle
Rush, a daily puzzle with streaks and puzzles made from your own mistakes; an endgame trainer; a
board vision trainer; an analysis board with engine lines; a spiral curriculum from the rules to
master level; an opening explorer; annotated master games with guess-the-move; Insights and
awards over your games; and a coach powered by Claude that only talks about facts the engine
verified.

No paywall, no account. Everything is stored in one SQLite file under `data/`.

## Run it

Requires Python 3.12+ and Node 22+. A native Stockfish makes Game Review faster but is not
required: the WASM engine from `npm install` is used when no binary is found.

```bash
./run-local.sh            # macOS / Linux: installs, builds, serves http://127.0.0.1:8765
.\run-local.ps1           # Windows PowerShell
```

Development with hot reload (backend on :8765, Vite on :5173 proxying `/api`):

```bash
./run-local.sh dev
```

Docker (bundles a native Stockfish):

```bash
cp .env.example .env
docker compose up --build   # → http://127.0.0.1:8765
```

### The coach

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` to turn on model-written explanations,
hints, chat and review narratives (`ANTHROPIC_MODEL` defaults to `claude-fable-5-1`). Without a key
the coach still works from rules: every answer is grounded in the engine's lines and the position
facts, it is just terser.

## Layout

```
backend/        FastAPI app: engine pool, bots, review, puzzles, coach, content loaders, routers
frontend/       React + TypeScript + Vite; the board, pages, the WASM engine worker
data/           openings (lichess TSV, CC0), lessons (JSON), puzzles (JSONL), games (PGN), the SQLite file
scripts/        self-play, puzzle generation, lesson validation, bot calibration (calibrate_bots.py)
tests/          pytest; frontend/e2e holds the Playwright tests
```

See [CLAUDE.md](CLAUDE.md) for the rules of the codebase and [PLAN.md](PLAN.md) for the design.

## Smoke test

```bash
curl localhost:8765/api/health        # engine name, opening count, coach mode
curl localhost:8765/api/bots          # the roster
```

## Content pipeline

```bash
python -m scripts.selfplay --games 40                       # bot games as puzzle material
python -m scripts.generate_puzzles data/selfplay/*.pgn      # tactics puzzles with themes and ratings
python -m scripts.validate_lessons data/lessons/*.json --engine   # must pass before committing lessons
```

## Credits

Piece set by Colin M.L. Burnett (CC BY-SA 3.0). Opening names from lichess
[chess-openings](https://github.com/lichess-org/chess-openings) (CC0). Engine: Stockfish (GPLv3),
WASM build by Nathan Rugg. Accuracy and win-chance formulas after lichess; move classification
boundaries after chess.com's published expected-points model.
