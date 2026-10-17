# CLAUDE.md — Chess Coach

One `uvicorn` process serves a FastAPI backend (`/api/*`) and the built React frontend (`/`).
It wraps Stockfish (native or WASM), the lichess opening book, a curriculum, a puzzle library,
curated master games and a Claude coach. Layout and run instructions: [README.md](README.md).
Product and architecture decisions: [PLAN.md](PLAN.md).

This file is the working contract: the judgment and the invariants, not the file tree.

## The one philosophy: the best solution is always the simple one

When two approaches both work, take the one a new developer follows in one read.

- **Minimum code that solves the asked problem.** No feature beyond the ask, no abstraction
  for single-use code, no configurability nobody requested, no handling for impossible cases.
  If you wrote 200 lines and it could be 50, rewrite it. Use ASD-STE100 (Simplified Technical
  English) principles for documentation and structural comments.
- **Delete before you polish.** A weak feature, an unused function, variable or branch: remove
  it. Reuse an existing primitive before inventing one.
- **Surgical changes.** Touch only what the task needs. Do not improve adjacent code, comments
  or formatting; match the surrounding style. Every changed line traces to the request.
- **Think before coding.** State assumptions. If two readings of the ask exist, name both
  instead of picking one silently.
- **Measure, then decide.** A claim about behaviour (how strong a bot is, how long a review
  takes, how accurate a classification is) comes with the number that proves it, or it is
  labelled a guess.
- **Fail twice, re-plan.** A fix that did not work twice is a wrong model of the problem.
- **Never invent terminology.** Use chess's own words (fork, zugzwang, book move) and the
  names chess.com and lichess players already know (accuracy, brilliant, key moment).

## Golden rules (invariants)

1. **The server holds the rules.** Every game, puzzle attempt and drill move is validated by
   `python-chess` on the server before it is stored or answered. The browser's `chess.js` is
   for display and instant feedback only; a disagreement is a bug on the server side to fix.
2. **The coach never invents a move.** Every move the coach may name comes from the position
   fact sheet ([backend/coach/facts.py](backend/coach/facts.py)): engine candidate lines, rule-based
   threats, the played move and the review's best move. The API checks the model's answer for
   SAN tokens that are legal in none of the positions and reports them as `unverified_moves`.
   The rule-based fallback ([backend/coach/fallback.py](backend/coach/fallback.py)) answers when there
   is no key or the model declines; the stream always ends with a `done` event.
3. **Content is validated at load, never trusted.** Lessons, puzzles and master games are
   replayed with `python-chess` when loaded; a broken section or game is dropped with a warning
   naming the file and id. `scripts/validate_lessons.py --engine` must pass before lesson content
   is committed: every challenge solution is the engine's best move or a fastest mate.
4. **Every threshold has one home.** Move classification and accuracy constants live in
   [backend/review/classify.py](backend/review/classify.py); the browser copy in
   `frontend/src/lib/review/classify.ts` mirrors the drop ladder for live feedback and nothing more.
   Bot strength lives in [backend/bots/roster.py](backend/bots/roster.py) (depth, temperature,
   personality); the engine's own Skill Level is never used, so engine lines stay honest.
5. **Two config planes.** `.env` / `Settings` ([backend/settings.py](backend/settings.py)) holds
   what belongs to the machine: paths, the API key, the model name, ports. `Settings` uses
   `extra="ignore"`, so a new env var needs a field **and** a line in `.env.example`. Anything
   that decides what the chess logic does (depths, thresholds, bot profiles, prompts) is code
   or a prompt file, version-controlled, never an env var.
6. **The coach model is optional.** It is an OpenAI-compatible server (`COACH_BASE_URL`,
   `COACH_MODEL`, `COACH_API_KEY`: local Ollama or LM Studio, or a free hosted API) or Anthropic
   (`ANTHROPIC_*`). Every call logs its tokens to `coach_cost` (`usage_reported = 0` when the
   server sent none: the zeros then mean "unknown"); the model id comes from `.env`, never from
   code. No loop calls the model; one request answers one question. Keys live only in `.env`,
   which is gitignored.
7. **Absence is data.** A stat with no games is `null` or a message, never a zero. An opening
   not in the book is `None`, not "Unknown Opening" invented in code.
8. **Only `frontend/dist` is web-served** and the static mount stays last in `app.py` so
   `/api/*` routes win. Never mount the repo root.

## Mental model (data flow)

Browser (`fetch /api/*`, SSE for the coach) → FastAPI routers → one of:
- the **engine pool** ([backend/engine/pool.py](backend/engine/pool.py)): two UCI engines,
  `play` for bot moves and `analysis` for review, hints, drills and the coach's facts, each
  behind its own lock;
- the **content loaders** (`backend/content/*`, `backend/openings/book.py`, `backend/puzzles/store.py`):
  JSON, PGN and TSV under `data/`, loaded once and cached;
- the **store** ([backend/storage/db.py](backend/storage/db.py)): SQLite, one connection, every
  call on a thread, additive migrations only.

The browser also runs its own Stockfish (WASM, single thread, `frontend/public/engine`) for
the eval bar and live move feedback so play never waits on the server for an evaluation.

Game Review ([backend/review/report.py](backend/review/report.py)) analyses every position once at
the chosen depth with two lines, judges every move with `classify.py`, and stores the report;
the browser polls the job. Insights read stored reports only.

## Code conventions (match existing code)

- Python 3.12+; `from __future__ import annotations` first after the module docstring. Async
  through the request path; engine and SQLite work is awaited.
- **Errors propagate.** Raise a specific exception at the layer that knows what went wrong;
  a wide catch only at a boundary (a review job, a content loader, the coach stream) and always
  with `exc_info=True`. Error text names the field, the value it had, and what was expected.
- **Logging** uses `%s` templates, never f-strings. One line per fact at INFO; dropped content
  and model refusals at WARNING.
- **Wire names are constants.** Classification labels, puzzle theme keys and SSE event types are
  declared once (`classify.py`, `puzzles/store.py`, `routers/coach.py`) and the TypeScript types in
  `frontend/src/lib/api.ts` mirror them; a renamed field must change both or it fails to compile.
- Pydantic models for request bodies live next to their router or in `backend/schema/`.

## Frontend

React + TypeScript + Vite in `frontend/`, plain CSS with tokens (`src/styles/tokens.css`).
- **Colour is state, not hierarchy.** A new hex in a component rule is a defect unless it is a
  state with no token. Classification colours are `--c-*` tokens and nowhere else.
- **The board is one component** (`src/components/board/Board.tsx`): FEN in, moves out. It knows
  nothing about games, puzzles or lessons; pages decide what is movable.
- **Motion answers a gesture**: piece moves animate through one `transform` transition under
  `--anim`, which `prefers-reduced-motion` sets to zero.
- Sounds are synthesised (`src/lib/sound.ts`); no audio assets, no licences.
- Keyboard: arrows navigate moves everywhere a move list exists; `f` flips in review.

## Tests

- `python -m pytest -q` from the repo root: every router through `TestClient` with a real engine
  and a temp SQLite file; no network, no API key (`tests/conftest.py` blanks it).
- `cd frontend && npx playwright test` with the backend running on :8765: board interaction,
  a full bot game, a PGN review with retry, puzzles and Puzzle Rush, a lesson with a drill.
- `ruff check .` before a commit. The lint config catches defects only (see `ruff.toml`).
- For a bug, reproduce first with a failing test, then fix.

## Gotchas (non-obvious, stable)

- The WASM engine in the browser cannot take a new `go` while searching: `Engine.analyse`
  queues searches and resolves the previous one on `stop`. Sending commands directly crashes
  the worker with `RuntimeError: unreachable`.
- Stockfish's `UCI_Elo` only affects `bestmove`; `info` lines stay full strength. Bots are
  weakened in `selector.py` (depth + softmax temperature + random moves), not by the engine.
- `database.start()` reads `settings.DB_PATH` at start, not at import, so tests can point at a
  temp file after importing the app.
- Puzzle FENs follow lichess: the position *before* the opponent's move; `moves[0]` is that move.
- `UCI_ShowWDL` is off in the browser engine; parsing assumes `score cp|mate` right after `score`.
- The lichess opening book names ~3,900 positions; `classify_game` stops looking six plies after
  the last named position, so a transposition back into theory later is not credited.
