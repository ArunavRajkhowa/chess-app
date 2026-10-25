# Chess Coach — the plan

This file says what the app is, how it is built, and why each decision was made. It is written
after a research sweep of chess.com (free and premium), lichess, the published move-classification
model, and the teaching methods of the Steps Method, Yusupov, Silman, Dvoretsky, de la Villa and
the lichess practice sets. The sweep lives outside the repo; the decisions it supports are here.

## 1. What the app is

A chess trainer that runs on one machine and serves browsers and phones; each visitor is a
player with their own progress. It gives, without a paywall:

| Area | What you get | chess.com equivalent |
|---|---|---|
| Play | 20 bots from 250 to 3200 with personalities and in-game chat, 140 specialist bots (openings, middlegames, endgames; 1000 to 2200) with an optional "Guide me" note after each move, an adaptive Coach bot, clocks with increments, coach mode (threat arrows, move feedback, hints, takebacks), eval bar, sounds, confetti | Bots, Play Coach |
| Game review | Accuracy per side, 11 move labels, key moments walkthrough, retry a mistake with "your accuracy would have been", eval graph, phase grades, estimated performance rating, coach explanations | Game Review (Diamond) |
| Puzzles | Rated puzzles with Glicko-2, themes, custom range, Puzzle Rush (3 min / 5 min / survival, three strikes), daily puzzle with hearts and a streak, "my mistakes" from your own reviewed games, stats and weakest themes | Puzzles, Puzzle Rush, Daily Puzzle |
| Endgames | 56 engine-verified positions in five themes, practice or a timed five-in-a-row challenge, best results kept | Endgames trainer |
| Analysis | Free board with three engine lines, eval bar, best-move arrow, FEN/PGN import, one click to a full review | Analysis board |
| Vision | Find-the-square and name-the-square drills, thirty seconds a round, best scores | Vision trainer |
| Learn | A nine-band spiral curriculum: text, positions with arrows, challenges, quizzes, drills against the engine, model games | Lessons |
| Openings | Explorer over 3,865 named lines, search, families, step through any line | Opening Explorer |
| Master games | Curated games by theme with every key move explained; guess-the-move scored by the engine | Master games, Practice |
| Coach | Chat about any position, explain any reviewed move, hints in three levels, a review narrative; grounded in engine facts | Coach |
| Insights | Your patterns per opening and colour (where you leave the book, the move you keep getting wrong), middlegame imbalances and how you score from them, endgame conversion, missed tactical motifs, strengths; each finding shown on a position from your games and linked to the lesson, puzzles, drill or bot that trains it; a weekly plan of five items | Insights (Diamond) |
| Study plans | A goal in your own words ("Sicilian for both sides") becomes a plan of real lessons, course lines, book variations, puzzles, master games and specialist games, with progress read from the store; a goal the app has nothing for gets no plan and the closest openings | none |
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
Qxf7# three times out of three; Pip varied across twelve tries. The Elo labels are estimates
checked by `scripts/calibrate_bots.py`: four games per bot against Stockfish limited to the bot's
labelled `UCI_Elo` (0.1 s per reference move; the reference cannot go below 1320, so the bots under
1320 are only shown to lose to it). Measured 2026-10-16 after the first weakening: Mei 2/4 at 1400,
Leo 1.5/4 at 1600, Ivy 3/4 at 1800, Omar, Zara and Viktor 4/4 at 2000-2400, so the Advanced tier was
weakened a second time (one depth less, higher temperature, four candidate lines). The rerun had
Ivy 2.5/4, Omar 2.5/4, Zara 3.5/4 and Viktor 3.5/4 (`data/bot_calibration.json`). Four games is a
coarse ruler (4/4 happens 6% of the time at equal strength), so the UI still says "about".

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
hanging, pinned and trapped pieces, pieces with no safe square, holes near the king, outposts,
pawn breaks, discovered attacks and checks, open and half-open files and who holds them,
mobility, the opening name with the book's main line from here, the phase and its goal, the
endgame's rule (opposition, Lucena, opposite bishops), the assessment (verdict, imbalances, plans
from `study/assess.py`), the last move's purpose (`study/reasons.py`), rule-based threats, the
opponent's best idea with a free move (the study's threat search) and three engine lines, each
with what its first move does. Next to it travels a context block the router reads from the store
(`backend/coach/context.py`; the browser sends only `game_id` or `lesson_id`): the player's puzzle
rating, band, weakest phase, blunder rate and missed puzzle themes; the bot, the clock, the moves
so far with their review labels, earlier mistakes and the eval trend; the lesson's objective.
The level comes from the puzzle rating unless the player picks one. Every answer follows one
order, and skips what the facts do not support: what just happened, the assessment, the plan,
what to check before moving, the better alternative, one question back. The prompt (`backend/coach/prompts/*.md`) forbids naming any move
not in the facts, and the API reports SAN tokens that are legal in none of the positions as
`unverified_moves`. Without a model the rule-based fallback answers from the same facts, so
every feature works offline. Model ids come from `.env`; every call logs tokens.

The model is any OpenAI-compatible server (`COACH_BASE_URL`, `COACH_MODEL`, `COACH_API_KEY`) or
Anthropic. The owner cannot use an Anthropic organisation key, so the default route is a local or
free open-weight model. The client (`backend/coach/client.py`) streams server-sent events with
`httpx` and has no SDK dependency. It sends `stream_options.include_usage` (most servers send no
token counts without it), drops `reasoning` fields and `<think>` blocks, and raises when the model
sends no answer text so the router falls back to rules.

Provider research, 2026-10-17 (limits change often; the sources are search results, and the
documentation hosts were not reachable from the build machine):

| Provider | Finding | Source |
|---|---|---|
| Groq | OpenAI-compatible. The rate-limit page lists gpt-oss-120b at 30 requests a minute, 1,000 a day, 200,000 tokens a day for the Developer plan; free-plan numbers were not shown. | [Groq rate limits](https://console.groq.com/docs/rate-limits) |
| OpenRouter | `:free` models: 20 requests a minute, 50 a day; 1,000 a day after $10 of credit. Failed calls count. | [OpenRouter limits](https://openrouter.ai/docs/api_reference/limits) |
| Cerebras | Current docs: $5 trial credit for 30 days, no renewing free tier. Older sources say 1M tokens a day. | [Cerebras rate limits](https://inference-docs.cerebras.ai/support/rate-limits) |
| Gemini API | Free-tier limits changed often; forum reports of 20 to 250 requests a day. Not open weights. | [Google AI forum](https://discuss.ai.google.dev/t/gemini-rate-limit-20-rpd/111274) |
| Ollama Cloud | Free plan with starter usage, one concurrent request, monthly reset. Both gpt-oss sizes have `-cloud` tags. | [Ollama pricing](https://ollama.com/pricing) |
| Ollama local | `/v1/chat/completions`. Streamed usage only with `stream_options.include_usage`. | [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility) |
| LM Studio | `/v1/chat/completions` on port 1234. Streamed usage not confirmed. | [LM Studio docs](https://lmstudio.ai/docs/developer/openai-compat/chat-completions) |
| NVIDIA build | 1,000 sign-up credits (up to 5,000), 40 requests a minute; forum posts only. | [NVIDIA forum](https://forums.developer.nvidia.com/t/api-credits-for-build-nvidia-com/306633) |
| Mistral | Free mode with the lowest limits; numbers shown only in the admin panel. | [Mistral limits](https://docs.mistral.ai/admin/billing-usage/usage-limits) |

Model sizes from the Ollama library: gpt-oss 20b about 14 GB, 120b about 65 GB (128K context);
Gemma 4 in sizes e2b, e4b, 12b, 26b and 31b; Qwen 3.6 in 27b and 35b. Not verified: how well any
of them coaches chess. One question measures about 2,200 input tokens; the fact sheet alone is
about 830 tokens on a typical middlegame (was about 470), at 3.42 characters a token from Groq's
own count.

Quality is measured, not judged by eye: `python -m scripts.coach_eval [--model] [--pause 25]` asks
27 positions (13 hand-picked, labelled opening, middlegame, endgame, winning, losing, after a
blunder, beginner or advanced; 14 library puzzles, one per motif) and scores each answer by the
facts a good answer must name (the threat, the solution, the opening, the endgame rule, an earlier
blunder, a question back, no evaluation numbers for a beginner) and by moves the move check cannot
verify. Measured 2026-10-24; the cases were written alongside the new fallback, so read the rules'
score as coverage, not as independent proof:

| Answerer | Before (HEAD prompts and sheet) | After | Unverified moves after |
|---|---|---|---|
| Rule-based fallback, 27 positions | 0.27 | 0.96 | 0 answers |
| gpt-oss-120b on Groq, first 10 positions | 0.42 | 0.89 | 0 answers |
| gpt-oss-120b on Groq, all 27 positions | not run (daily token budget) | 0.82 | 1 answer (`Nf3`) |

What both still miss: the motif word for a pin, skewer, deflection and a trapped queen, which no
rule detects yet; the model also skips the opening's name twice and the earlier blunder once.

### 2.5 Content

| Content | Format | Validation at load | Source |
|---|---|---|---|
| Openings | lichess TSV (3,865 lines, CC0) | every line replayed | lichess-org/chess-openings |
| Lessons | JSON: bands > modules > lessons > sections | FENs legal, solutions legal; `scripts/validate_lessons.py --engine` proves every challenge solution is the engine's best or a mate | authored from the pedagogy research |
| Puzzles | JSONL, lichess shape (FEN before the opponent's move) | loaded as-is; the generator verifies with Stockfish at creation | `scripts/generate_puzzles.py` from self-play and master games |
| Master games | PGN with `Themes`, `Why`, `Level` headers and move comments | replayed; broken games dropped | curated classics |

### 2.6 Storage

SQLite through `libsql`: one local file, or a Turso database when `TURSO_DATABASE_URL` is set.
Turso was chosen (2026-10-19) over Supabase and Neon because it speaks the same SQLite dialect, so
tests keep running on a file and no query changes; its free plan holds 5 GB. Tables: players (id,
email, Google subject, password hash), games, reviews, puzzle_attempts, player_lessons, player_values
(key-value: puzzle rating, rush bests, trainer stats), player_reviews, player_plans, events, sessions,
coach_cost. Every per-player row carries `player_id`, and every per-player table is listed in
`PLAYER_TABLES` or `PLAYER_KEYED_TABLES` (a test compares the list with the schema), so sign-in merge
and delete-my-data cannot miss one. Migrations are additive (`_ADDED_COLUMNS`); the single-player
`player` and `lesson_progress` tables are left in old files and no longer read. Audited 2026-10-24:
WAL on the file only (Turso refuses the pragma), the three hot lists (games by `updated_at`,
attempts by id, events by time) each have a `(player_id, ...)` index, the keyed tables are indexed by
their primary key, and `sessions(player_id)` and `players(email)` were added for sign-out-everywhere
and sign-in. The one foreign key (reviews -> games) is declared but not enforced by SQLite's default;
delete-my-data removes reviews through the games it owns.

### 2.7 Players and analytics

Every visitor is a player from the first page load: a random 128-bit id in an httpOnly,
SameSite=Lax cookie. Signing in, by email and password or with Google (Google Identity Services
button, token checked by Google's tokeninfo endpoint), replaces that cookie with a session token
whose SHA-256 is a row in `sessions`; a guest's rows move to the account, and the account's value
wins where both have one. Decided 2026-10-24: server-side sessions over signed cookies because
"sign out everywhere" is then one `DELETE`, and a per-process cache keeps a signed-in request from
costing a Turso round trip. Passwords: scrypt from the standard library (no C extension to build for
arm64), 8 characters minimum and nothing else, one error message for a wrong email or password, ten
failures per address per 15 minutes (in memory). Password reset: an HMAC-signed link (SECRET_KEY)
that embeds the current hash, so it is single-use by construction and needs no table; the mail goes
over SMTP or, unconfigured, to the log. A Google sign-in never links to a password account by email
alone, because a sign-up email is unverified; the reset link to that address is the proof. Only the
email and the hash are stored. Delete-my-data removes every row. Analytics come from the stored games, reviews, attempts and progress, plus three
browser events (app opened, page viewed, app installed) whose properties are declared per event
and must be short identifiers, so no free text or personal data enters the table.

### 2.8 Phones

An installable web app (manifest and icons; Chrome needs no service worker for its install menu
since version 108 on Android and 112 on desktop). Decided 2026-10-24: the app is hosted, because
the owner's computer is not always on. Revised 2026-10-25: "free" means no card is ever linked, which
rules out Cloud Run, Oracle, Koyeb and Fly.io; the host is Render's free web service (no card,
512 MB, 0.1 CPU, sleeps after 15 idle minutes), SnapDeploy the fallback (docs/deploy.md). Store apps are Capacitor shells in
remote-URL mode (`frontend/capacitor.config.ts`): the WebView loads the hosted address, so one
deploy serves every platform and the first-party cookie keeps working; Android builds as a debug
APK in GitHub Actions for free, iOS needs a Mac and the $99 programme, so the home-screen install
stays the free iOS path (docs/mobile.md). A tunnel to the owner's computer remains an option (README).

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

### 3.1 How the app teaches (the principles behind every lesson)

The lesson shape copies what a good coach does at the board, and each step rests on a finding
from learning research or from how chess skill is built:

1. **Show it first, from first principles, with the pieces moving.** The teaching sections of a
   lesson (text, positions, lectures, model games) run together as one narrated video that stops
   only at a task, which it announces ("Your turn. White to play. Mate in one."). A `lecture` section plays
   moves on the board while a narration explains them, starting from the rule underneath
   (one move per turn; a check must be answered; a king may not be captured) and only then
   naming the pattern (fork, pin, opposition). Narrated animation beats text beside a diagram
   (Mayer's modality and temporal contiguity principles); arrows and highlights point at what
   the words name (signalling); frames are short and learner-paced (segmenting); the caption
   shows only the sentence being spoken, never the whole text (redundancy). The narration is
   the browser's own speech synthesis: no audio assets, no server, no rate limit.
2. **Then the learner finds it.** Challenges are retrieval, not recognition: the move has to be
   played. A wrong move is not just "wrong": the engine shows the reply that punishes it, the
   way a coach would ("after Nf3, Black takes on e4"). Hints climb a ladder, words first, then
   the piece, then the square, so the learner keeps thinking as long as possible. "Why not this
   move?" is answered on every teaching board (try a move, engine verdict) and by the coach.
3. **Then play it out.** Drills put the idea against engine resistance, because chess skill is
   a stock of patterns (de Groot, Chase and Simon) tied to the positions where they apply.
4. **Then come back to it.** A challenge or quiz missed in a lesson returns the next day in
   Review, then on a growing ladder (1, 3, 7, 16, 35, 90 days), the spaced-retrieval schedule
   Chessable's MoveTrainer and SM-2 use. A miss at review restarts the ladder.
5. **Start where the player is.** The puzzle rating, once settled, places a new player in a band
   (a 1,180 puzzle rating starts at Rook, not at "The board"); until then the page says so
   instead of guessing. Themes are interleaved across bands rather than finished one at a time,
   as Yusupov's course does, and the thinking rituals (Heisman's "is it safe?", checks-captures-
   threats, five steps) are taught as lessons because most games below 1400 are lost by a move
   that was never checked.
6. **Model games are watched, not read, and every move answers "why, and why not".** A master
   game or lesson model game opens as a narrated walkthrough. The study
   ([backend/study/annotate.py](backend/study/annotate.py)) gives every move the engine's three
   candidates at depth 14, says what the played move does in board words
   ([backend/study/reasons.py](backend/study/reasons.py): develops, forks, pins, parries the threat of,
   takes for free), what the opponent threatened (a free-move search), and for each alternative
   why not: the engine's reply to it, told the same way ("much worse: Nd4 forks the pawn on c2 and
   the queen on f3"). A mistake gets its problem and the better move. Every alternative plays out
   on the board on a click, spoken. Studies are computed once (`scripts/annotate_games.py`, all
   games, cached under `data/study/`) or on first sight, polled while the engine works. The
   player's own reviewed games get the same study on the Game Review page: every move of yours,
   why it was fine or what it ran into, and the engine's choices played out.
7. **Assess like a grandmaster.** Any position can be assessed ([backend/study/assess.py](backend/study/assess.py)):
   the imbalances (material, bishop pair, king in the centre, development, isolated and doubled
   pawns, passed pawns, outposts, open files, space, activity, king activity) and the plan each
   side gets from each, with the engine's eval anchoring the verdict. On the Analysis board and
   under every watched game.
8. **Puzzles come back too.** A missed library puzzle returns on the same ladder as a missed lesson
   task, computed from the attempt history alone (every solve since the last miss climbs a rung).
9. **Ratings mean what they say.** A puzzle's rating comes from its shape (one home:
   `backend/puzzles/difficulty.py`), the player's puzzle rating moves at most 80 points on one
   result, and a game review estimates strength only from twenty judged moves or more.

Section types: `lecture` (narrated frames: a position or a move, arrows and highlights, one
spoken sentence or two), `text`, `position` (arrows and highlights, read aloud on demand),
`challenge` (find the move or line), `quiz`, `drill` (play the position against the engine to a
goal), `game` (model game, played as a narrated walkthrough). Every module in bands 0 to 3 opens
with a lecture; bands 4 to 8 open with narrated model games. Every band ends with exit criteria
the Insights page can check: accuracy by phase, blunder rate, puzzle rating by theme.

## 4. What is built and what is next

Built and tested (91 backend tests, 21 Playwright flows): everything in section 1, with the
content in the README table (185 lessons in all nine bands, 125 annotated master games, 558
puzzles, 24 endgame positions).

Four independent critics then used the running app (play, review, learning, engine and API) and
reported 49 defects; every one was reproduced, fixed with a test and committed. The largest were:
a static path that served files outside `frontend/dist`, a kingless FEN that crashed Stockfish
for good, puzzle and endgame results taken from the browser's word, 136 puzzles that could not be
solved, draws declared one move early, and review accuracy weighted by the wrong ply.

Built since (2026-10-20): narrated lectures with the browser's speech synthesis (20 scripts,
bands 0 to 3), master games as narrated walkthroughs, engine refutations and a hint ladder in
challenges, spaced review of missed lesson tasks and puzzles, placement by puzzle rating, the
why-and-why-not study of every master and lesson game with playable variations, and the
grandmaster assessment (imbalances and plans) of any position.

Built since (2026-10-24): study plans from a typed goal, specialist bots with Guide me, the
Insights rebuild (findings with your own positions and linked prescriptions), a richer coach fact
sheet with player and game context (rule-based eval 0.27 to 0.96, model 0.42 to 0.89, PLAN §2.4),
email and password accounts with server sessions, free-hosting and store-app resources, the
lichess puzzle import (5,801 puzzles), 56 endgames, 170 master games, 33 lectures, and the UI
restyle (day and night themes, motion and sound palette, drawn emblems and bot faces). A review
by 8 reviewers found 84 defects, 79 confirmed by independent skeptics; all were fixed and
re-checked, the worst being an old guest cookie that still opened a signed-in account.

Built since (2026-10-25): eight more opening courses (14 in all), 140 specialists measured by kind
and rating and all 20 classic bots re-measured at 6 games each (Nova and Rafa weakened), tasks for
17 of the 26 lessons that had none and drills for band 8, the intermittent e2e 404 traced to the
Vite dev server minting a guest per parallel call, and phone motion profiled and cut (worst frame
after the first move 133 to 67 ms on the board page, 133 to 100 ms in a game, at 4x CPU throttle).

Next, in order:
1. Measure bot strength against people (the calibration is 6 games per bot against Stockfish).
2. A first deploy on Render (`render.yaml`, `docs/deploy.md`) with Turso set.
3. Tasks for the 9 lessons that still have none (bands 0 to 4).
4. The Play page's remaining 100 ms frame: the game view's render, style and layout per move.
5. A strong player's review of the lesson and course prose: the engine and python-chess check the
   moves and the board claims, not the teaching.

## 5. Risks

- The coach's quality depends on the fact sheet. A missing fact (for example, a discovered
  attack the rules do not detect) makes the model generic, never wrong. Add facts, not freedom.
- Bot strength labels are unmeasured against humans. Say "about" until measured.
- Content is the long pole. Agents wrote the lessons and an engine-checking reviewer pass found
  and fixed many wrong claims; the validators keep the moves correct. Whether the teaching is
  good still needs a strong player's review.
