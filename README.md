# Chess Coach

Play, review and learn chess in one app that runs on your own machine or on free hosting. Twenty
bots from 250 to 3200 with personalities, chat and an adaptive coach bot, and 140 specialist bots
(openings, middlegames, endgames at 1000 to 2200) that can guide you move by move; a goal bar
that turns "I want to learn the Sicilian, both sides" into a study plan built only from the app's
own lessons, courses, puzzles, master games and bots; clocks; chess.com-style Game Review
with accuracy, key moments, retry and practice-from-here; a puzzle trainer with ratings, Puzzle
Rush, a daily puzzle with streaks and puzzles made from your own mistakes; an endgame trainer; a
board vision trainer; an analysis board with engine lines; a spiral curriculum from the rules to
master level with narrated lectures that play the moves while a voice explains them, engine
feedback on every wrong move and spaced review of what you missed; an opening explorer;
annotated master games watched with commentary, where every move says why it was played and why
not the alternatives, each one playable on the board, or played guess-the-move; the same
why-and-why-not study of your own reviewed games; a grandmaster's assessment of any position
(imbalances and plans); Insights that find your own patterns in openings, middlegames, endgames
and tactics, show each one on a position from your games and link the drill that fixes it; awards;
and a
coach that works from rules or from any local or hosted language model, and only talks about
facts the engine verified.

No paywall. Everyone plays as a guest from the first visit; an account (email and password, or
Google) keeps progress across devices. Data lives in one SQLite file under `data/`, or in a free
Turso database. It installs on Android, iPhone and desktop Chrome as an app, runs on free hosting
([docs/deploy.md](docs/deploy.md)) and ships as a store app ([docs/mobile.md](docs/mobile.md)).

## What is inside

| Content | Count | How it is checked |
|---|---|---|
| Lessons | 191 lessons in 52 modules, bands 0 (rules) to 8 (master), 1,095 sections, 33 narrated lectures | `scripts/validate_lessons.py --engine`: every challenge is the engine's best move or as good; every lecture move is replayed |
| Master games | 170 games in 27 themes, 845 key-moment notes, every move studied by the engine (three candidates at depth 14, reasons, threats, why-not lines) | replayed at load; a test replays every move line in every note; `scripts/annotate_games.py` caches the studies under `data/study/` |
| Puzzles | 5,801: 558 generated, rated by their shape (`backend/puzzles/difficulty.py`), and 5,243 from the lichess puzzle database (CC0, `scripts/import_lichess_puzzles.py`), which keep their measured lichess rating; 70 themes, opening tags | replayed at load; generated puzzles have one solution per solver move at depth 16; an engine sample of 100 lichess puzzles passed 98 |
| Endgames | 56 positions in five themes | engine goal check; no piece hangs at the start |
| Openings | 3,865 named lines (lichess, CC0) | parsed at load |
| Bots | 20, from 250 to 3200, plus 140 specialists generated from the 14 opening courses, master games and endgames | `scripts/calibrate_bots.py`, 6 games each against Stockfish at the bot's label (`data/bot_calibration.json`, 2026-10-25): every classic bot and every specialist kind and rating within the 6-game noise of its label |
| Opening courses | 14: Caro-Kann, English, French, Italian, King's Indian, London, Nimzo-Indian, Queen's Gambit, Queen's Gambit Declined, Ruy Lopez, Scandinavian, Sicilian Dragon, Sicilian Najdorf, Slav; 69 lines, 33 traps | `scripts/validate_courses.py --engine`: every trap's punishment is the engine's move; every board claim in the notes checked with python-chess |

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

One coach question uses about 2,200 input tokens (measured on Groq, 2026-10-24: the rules, who you
are, this game so far and the fact sheet) and 600 to 900 output tokens with gpt-oss's reasoning, so
200,000 tokens cover roughly 65 questions. Groq's free tier also caps a minute at 8,000 tokens:
about two questions a minute.

Not recommended as the default: the Gemini free tier (its limits were cut several times and Google
may use free-tier prompts), Cerebras (no permanent free tier: $5 of credit for 30 days) and NVIDIA
build (trial credits).

The client was tested against simulated and local fake servers, not a live model. Coaching quality
differs between models. Start with `gpt-oss:20b`: the same model runs locally, on Ollama Cloud, on
Groq and on OpenRouter, so you can switch without a change in behaviour. A thinking model spends
tokens on thought first. If answers come back empty, raise `COACH_MAX_TOKENS`.

### Narration

Every lesson plays as one narrated video: the teaching parts run on their own, the pieces move
and the arrows appear as the voice explains, and the flow stops only when it is your move, which
it says out loud. The voice is a free neural one (Microsoft Edge's, through the `edge-tts`
client): each sentence is fetched once and cached as MP3 under `data/audio/`, so only the first
listener of a sentence waits a second. `NARRATION_TTS=false`, or no internet, and the browser's
own speech synthesis speaks instead (Edge's "Natural" voices sound best); without any voice the
video still runs on a reading timer with captions. Settings → Narration sets the speed and the
fallback voice.

## On your phone

The app installs like a native one: Android Chrome menu → "Install app"; iPhone Safari → Share →
"Add to Home Screen"; desktop Chrome → the install icon in the address bar. Run the built app
(`./run-local.sh`, not `dev`): the server then sets the player cookie on the page itself.

The simplest phone setup is the hosted app ("Deploy it" below): one https address that is up when
your computer is off. An Android APK and the iOS story (a Mac and a $99 developer account; the home
screen install is the free path) are in [docs/mobile.md](docs/mobile.md).

To use the app on your own computer from a phone instead, it needs an HTTPS address that reaches it:

| Way | Cost | Limits (checked 2026-10-19) |
|---|---|---|
| Cloudflare quick tunnel: `cloudflared tunnel --url http://localhost:8765` (Windows: `winget install Cloudflare.cloudflared`) | Free, no account | A new address every run, so Google sign-in cannot be registered for it. No server-sent events, so coach answers do not stream. A first look only. |
| Cloudflare named tunnel on a domain you own | Free tunnel, plus the domain | Needs a Cloudflare account. A fixed address: register it once with Google. |
| Tailscale Funnel: `tailscale funnel 8765` | Free on all plans (beta) | A fixed `https://<machine>.<tailnet>.ts.net` address. Bandwidth limits are not published. |

Sources: [Cloudflare quick tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/), [Tailscale Funnel](https://tailscale.com/kb/1223/funnel).

## Deploy it

The Docker image runs on free hosting with a Turso database (the hosts' disks are wiped on restart).
Checked 2026-10-25, counting only hosts that never ask for a card: Render's free web service runs
it (`render.yaml`: New, then Blueprint, then this repo), SnapDeploy is the fallback. Both sleep after
15 idle minutes and give the engine a fraction of a CPU, so a review is slow. Cloud Run, Oracle,
Koyeb and Fly.io need a card; Hugging Face Docker Spaces are paid since July 2026. The table, limits
and sources: [docs/deploy.md](docs/deploy.md).

## Accounts, the database and analytics

- **Guests.** The first visit makes a player: a random id in an httpOnly cookie. Settings → Account
  offers sign-in, sign-out (this device or everywhere) and "Delete my data", which removes every row
  of the player.
- **Email and password.** No setup: Settings → Account → "Create an account". Passwords are at least
  8 characters, hashed with scrypt; a signed-in device holds a session token, so "Sign out everywhere"
  works. Ten failed sign-ins from one address in 15 minutes lock that address out for the window.
  "Forgot password?" mails a link that is valid for two hours and once; without an SMTP server
  (`SMTP_HOST`, see `.env.example` for Brevo's and Resend's free relays) the link is printed in the
  server log instead.
- **Google sign-in.** Google Cloud Console → APIs & Services → Credentials → OAuth client ID, type
  "Web application". Add every address the app opens from (`http://localhost:8765`, your tunnel's
  address) as an authorised JavaScript origin, and put the client id in `GOOGLE_CLIENT_ID`. While
  the consent screen is in "Testing", only the test users you list can sign in. Signing in on a
  second device moves that device's guest games to the account.
- **Turso.** `turso db create chess-coach`, then `turso db show chess-coach --url` and
  `turso db tokens create chess-coach` into `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. Free plan:
  5 GB, 500 million rows read and 10 million rows written a month ([pricing](https://turso.tech/pricing),
  checked 2026-10-19). Without them the app uses `DB_PATH`.
- **What is stored, per player.** Every game move by move, every review judged move by move, every
  puzzle attempt with its time and rating, lesson progress, ratings and trainer bests, and three
  events: app opened (installed app or browser), page viewed, app installed, each with the
  operating system family. Personal data: the email, after sign-in. Not stored: IP addresses, the
  user agent string, location. Player names appear only in the headers of PGNs you import.
- **Questions over the data:** the `player-analytics` skill, or `turso db shell chess-coach "<sql>"`.

Games and puzzle attempts saved before accounts existed have no player; they stay in the file and
no one sees them.

## Layout

```
backend/        FastAPI app: engine pool, bots, review, puzzles, coach, content loaders, routers
frontend/       React + TypeScript + Vite; the board, pages, the WASM engine worker
data/           openings (lichess TSV, CC0), lessons (JSON), puzzles (JSONL), games (PGN), study (the engine's why/why-not of every game), the SQLite file
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
python -m scripts.annotate_games --workers 4                 # the why/why-not study of every master and lesson game (cached; skips what is done)
```

## Credits

Piece set by Colin M.L. Burnett (CC BY-SA 3.0). Opening names from lichess
[chess-openings](https://github.com/lichess-org/chess-openings) (CC0). Engine: Stockfish (GPLv3),
WASM build by Nathan Rugg. Accuracy and win-chance formulas after lichess; move classification
boundaries after chess.com's published expected-points model. Master-game scores from the
pgnmentor.com player files and The Week in Chess (via the `rozim/ChessData` mirror), the 1997
Deep Blue games from python-chess's test data, and the AlphaZero games DeepMind released in 2018;
the themes and notes on them are this project's own.
