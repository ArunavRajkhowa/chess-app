# Chess Coach — the plan

This file says what the app is, how it is built, and why each decision was made. It is written
after a research sweep of chess.com (free and premium), lichess, the published move-classification
model, and the teaching methods of the Steps Method, Yusupov, Silman, Dvoretsky, de la Villa and
the lichess practice sets. The sweep lives outside the repo; the decisions it supports are here.

## 1. What the app is

A single-user chess trainer that runs on one machine. It gives, without a paywall:

| Area | What you get | chess.com equivalent |
|---|---|---|
| Play | 20 bots from 250 to 3200 with personalities and in-game chat, an adaptive Coach bot, clocks with increments, coach mode (threat arrows, move feedback, hints, takebacks), eval bar, sounds, confetti | Bots, Play Coach |
| Game review | Accuracy per side, 11 move labels, key moments walkthrough, retry a mistake with "your accuracy would have been", eval graph, phase grades, estimated performance rating, coach explanations | Game Review (Diamond) |
| Puzzles | Rated puzzles with Glicko-2, themes, custom range, Puzzle Rush (3 min / 5 min / survival, three strikes), daily puzzle with hearts and a streak, "my mistakes" from your own reviewed games, stats and weakest themes | Puzzles, Puzzle Rush, Daily Puzzle |
| Endgames | 24 engine-verified positions in five themes, practice or a timed five-in-a-row challenge, best results kept | Endgames trainer |
| Analysis | Free board with three engine lines, eval bar, best-move arrow, FEN/PGN import, one click to a full review | Analysis board |
| Vision | Find-the-square and name-the-square drills, thirty seconds a round, best scores | Vision trainer |
| Learn | A nine-band spiral curriculum: text, positions with arrows, challenges, quizzes, drills against the engine, model games | Lessons |
| Openings | Explorer over 3,865 named lines, search, families, step through any line | Opening Explorer |
| Master games | Curated games by theme with every key move explained; guess-the-move scored by the engine | Master games, Practice |
| Coach | Chat about any position, explain any reviewed move, hints in three levels, a review narrative; grounded in engine facts | Coach |
| Insights | Accuracy over time and by phase, results and endings, move quality per game, openings table, game shapes, worst moves, what to work on | Insights (Diamond) |
| Awards | 22 achievements computed from the store (wins per tier, puzzles, rush, streaks, lessons, reviews, endgames) | Awards |

## 2. Architecture

One `uvicorn` process serves `/api/*` (FastAPI) and the built React app. See [CLAUDE.md](CLAUDE.md)
for the invariants; this section records the choices.

### 2.1 Engine: native on the server, WASM in the browser

- The server runs Stockfish through `python-chess` (two UCI processes: `play` and `analysis`).
  It finds a native binary (`STOCKFISH_PATH`, PATH, `/usr/games/stockfish`, Homebrew) and falls
  back to the WASM build from `npm install` run under Node. Measured on this container: a quick
  review (depth 12) of a 60-ply game takes about 8 s natively; depth 16 about 25 s.
- The browser runs the single-threaded WASM Stockfish 17.1 lite (7 MB, no cross-origin
  isolation headers needed) in a Web Worker for the eval bar and instant move feedback. It never
  decides anything the server stores.
- Why not browser-only: the review, bots and coach facts need deterministic, testable Python
  with python-chess; the user's laptop may not have a native engine, so the WASM fallback keeps
  the app zero-install.

### 2.2 Bots: honest engine lines, human-like choice

Stockfish's `UCI_Elo` only weakens `bestmove`; its analysis lines stay full strength. Bots
therefore take honest multipv lines at a bot-specific depth (1 to 24) and choose by a softmax over
centipawn loss with a temperature from 400 cp (Pip, 250) to 0 (Stockfish, 3200), plus a random
move probability for the weakest bots and personality nudges (aggression, solidity, trading when
ahead, favourite openings from the book). Measured on one tactical position: Elena (2600) found
Qxf7# three times out of three; Pip varied across twelve tries. The Elo labels are calibrated by
depth and temperature, not yet by matches against rated play: label them as estimates in the UI
until a self-play ladder measures them (`scripts/selfplay.py` is the start of that).

### 2.3 Game review

- Every position is analysed once at the chosen depth (quick 12, full 16, deep 20) with two
  lines. Win chance uses the lichess curve `50 + 50 (2 / (1 + e^(-0.00368 cp)) - 1)`.
- Labels follow chess.com's published expected-points boundaries: Excellent <= 2 points lost,
  Good <= 5, Inaccuracy <= 10, Mistake <= 20, Blunder beyond. Best is the engine's first line.
  Great is the only good move (second line 10 points worse) or the punish of a mistake.
  Brilliant is a sound sacrifice (two pawns of material or more, position not already won, not in
  check, not a promotion). Miss is a winning chance (85%+) thrown away. Book is a position in the
  lichess opening book within the first 24 plies. Forced is the only legal move.
- Accuracy per move is the lichess formula `103.1668 e^(-0.04354 drop) - 3.1669`; game accuracy is
  the mean of a volatility-weighted average and the harmonic mean, as lichess does.
- Estimated performance rating is a table from average centipawn loss. It is a rough estimate
  and is labelled as such.
- Phases follow lichess's divider: middlegame when ten or fewer non-pawn pieces remain, the back
  ranks have emptied, or ply 30; endgame at six or fewer non-pawn pieces.

### 2.4 Coach: facts first, model second

The coach never sees a bare FEN. It sees a fact sheet: material, king safety, pawn structure,
hanging and pinned pieces, mobility, the opening name, the phase, rule-based threats, and three
engine lines with evaluations. The prompt (`backend/coach/prompts/*.md`) forbids naming any move
not in the facts, and the API reports SAN tokens that are legal in none of the positions as
`unverified_moves`. Without an API key the rule-based fallback answers from the same facts, so
every feature works offline. Model id and effort come from `.env`; every call logs tokens.

### 2.5 Content

| Content | Format | Validation at load | Source |
|---|---|---|---|
| Openings | lichess TSV (3,865 lines, CC0) | every line replayed | lichess-org/chess-openings |
| Lessons | JSON: bands > modules > lessons > sections | FENs legal, solutions legal; `scripts/validate_lessons.py --engine` proves every challenge solution is the engine's best or a mate | authored from the pedagogy research |
| Puzzles | JSONL, lichess shape (FEN before the opponent's move) | loaded as-is; the generator verifies with Stockfish at creation | `scripts/generate_puzzles.py` from self-play and master games |
| Master games | PGN with `Themes`, `Why`, `Level` headers and move comments | replayed; broken games dropped | curated classics |

### 2.6 Storage

SQLite, one file. Tables: games, reviews, puzzle_attempts, lesson_progress, player (key-value:
puzzle rating, rush bests), coach_cost. Migrations are additive (`_ADDED_COLUMNS`).

## 3. The learning design

Nine bands, named after pieces so progress feels like promotion:

| Band | Name | Rating | Spine |
|---|---|---|---|
| 0 | Pawn | learning the rules | lichess Learn basics, Steps 1 lessons 1-7 |
| 1 | Knight | under 800 | Steps 1, elementary mates, "is it safe?" |
| 2 | Bishop | 800-1100 | Steps 2: double attack, pin, discovered attack, mate in two, K+P endings, CCT |
| 3 | Rook | 1100-1400 | Steps 3, mating patterns, Lucena and Philidor, five-step thinking |
| 4 | Queen | 1400-1700 | Steps 4 preparatory moves, Yusupov Fundamentals, Silman imbalances |
| 5 | King | 1700-2000 | Steps 5, Yusupov Beyond the Basics, de la Villa's 100 endgames, Nimzowitsch |
| 6 | Super King | 2000-2200 | Steps 6, Yusupov Mastery, Dvoretsky's blue positions, Aagaard calculation |
| 7 | Candidate | 2200-2400 | Aagaard GM Preparation, Watson, Marin |
| 8 | Master | 2400+ | process and depth: own-game analysis, preparation workflows |

Each lesson is the proven unit: a five-minute concept, then interactive positions, then a scored
checkpoint. Section types: `text`, `position` (arrows and highlights), `challenge` (find the
move or line), `quiz`, `drill` (play the position against the engine to a goal), `game`
(model game walkthrough). Every band ends with exit criteria the Insights page can check:
accuracy by phase, blunder rate, puzzle rating by theme.

## 4. What is built and what is next

Built and tested (43 backend tests, 8 Playwright flows): everything in section 1. Content so far
is a seed: band 0 and part of band 1 (7 lessons, 30 sections), one annotated master game, 36
generated puzzles plus a second batch generating from 72 self-play games.

Next, in order:
1. Lesson content for bands 1-6 from the curriculum research, validated with the engine.
2. Curated master games (80+) with move-by-move explanations and theme tags.
3. Puzzle library to several thousand from master games and self-play; theme detection for
   deflection and attraction.
4. Bot Elo calibration by self-play against fixed `UCI_Elo` opponents (`scripts/calibrate_bots.py`).
5. More endgame positions (de la Villa's hundred) and a knight-and-bishop mate walkthrough.
6. Spaced repetition of missed puzzles and lesson challenges (SM-2 ladder).
7. Opening ideas per family (plans, traps, model games) once the openings research lands.

## 5. Risks

- The coach's quality depends on the fact sheet. A missing fact (for example, a discovered
  attack the rules do not detect) makes the model generic, never wrong. Add facts, not freedom.
- Bot strength labels are unmeasured against humans. Say "about" until measured.
- Content is the long pole. The validators keep it correct; nothing keeps it interesting except
  review by a strong player.
