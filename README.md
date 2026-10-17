# Chess Coach

Play, review and learn chess in one app that runs on your own machine. Twenty bots from 250 to
3200 with personalities, chat and an adaptive coach bot; clocks; chess.com-style Game Review
with accuracy, key moments, retry and practice-from-here; a puzzle trainer with ratings, Puzzle
Rush, a daily puzzle with streaks and puzzles made from your own mistakes; an endgame trainer; a
board vision trainer; an analysis board with engine lines; a spiral curriculum from the rules to
master level; an opening explorer; annotated master games with guess-the-move; Insights and
awards over your games; and a coach that works from rules or from any local or hosted language
model, and only talks about facts the engine verified.

No paywall, no account. Everything is stored in one SQLite file under `data/`.

## What is inside

| Content | Count | How it is checked |
|---|---|---|
| Lessons | 185 lessons in 49 modules, bands 0 (rules) to 8 (master), 1,017 sections | `scripts/validate_lessons.py --engine`: every challenge is the engine's best move or as good |
| Master games | 125 games in 27 themes, 561 key-moment notes | replayed at load; a test replays every move line in every note |
| Puzzles | 558, rated 400-2000 | replayed at load; every solver move has one solution at depth 16 |
| Endgames | 24 positions in five themes | engine goal check; no piece hangs at the start |
| Openings | 3,865 named lines (lichess, CC0) | parsed at load |
| Bots | 20, from 250 to 3200 | `data/bot_calibration.json` (four games each against Stockfish) |

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

### The coach and its model

The coach works without a model: it answers from rules, using the engine's lines and the position
facts. A language model words the answers better. You do not need an Anthropic key. Any
OpenAI-compatible server works, and some are free.

1. Copy `.env.example` to `.env`. `.env` is gitignored, so your keys stay on your machine.
2. Set `COACH_BASE_URL` and `COACH_MODEL`. For a hosted service, also set `COACH_API_KEY`.
3. Run `python -m scripts.check_coach`. It sends one question and prints the answer, the time and
   the token counts.

Only the position, the engine lines and your question go to the model.

| Where the model runs | Cost and limits (checked 2026-10-17) | Notes |
|---|---|---|
| Ollama or LM Studio on your computer | Free, private, no limits. Needs memory. | `gpt-oss:20b` is a 14 GB download. A smaller computer needs a 4B to 8B model. |
| Ollama Cloud, for example `gpt-oss:120b-cloud` | Free plan: starter usage, one request at a time, monthly reset. | You call your local Ollama; the model runs on Ollama's servers. The free model list is not published: check while signed in. |
| Groq | Free tier with a key. Third-party sources list 1,000 requests and 200,000 tokens a day for gpt-oss models. | Fast. Read your own limits in the Groq console. |
| OpenRouter, models that end in `:free` | 20 requests a minute and 50 a day. 1,000 a day after you buy $10 of credit once. | A failed call still counts. A free provider may log prompts. |

One coach question uses about 900 input tokens (measured on a real fact sheet) and a short
answer, so 200,000 tokens cover roughly 150 questions.

Not recommended as the default: the Gemini free tier (its limits were cut several times and Google
may use free-tier prompts), Cerebras (no permanent free tier: $5 of credit for 30 days) and NVIDIA
build (trial credits).

The client was tested against simulated and local fake servers, not a live model. Coaching quality
differs between models. Start with `gpt-oss:20b`: the same model runs locally, on Ollama Cloud, on
Groq and on OpenRouter, so you can switch without a change in behaviour. A thinking model spends
tokens on thought first. If answers come back empty, raise `COACH_MAX_TOKENS`.

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
boundaries after chess.com's published expected-points model. Master-game scores from the
pgnmentor.com player files and The Week in Chess (via the `rozim/ChessData` mirror), the 1997
Deep Blue games from python-chess's test data, and the AlphaZero games DeepMind released in 2018;
the themes and notes on them are this project's own.
