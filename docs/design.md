# Design direction

For developers. The tokens are the contract (`frontend/src/styles/tokens.css`); this says why.

## Personality, in three lines

- A coach's study, not a casino: one brass accent for the one action that matters, everything else ink and paper.
- The board is calm and the sentence is the feedback: the coach says "Nf3 was better: it defends e5", a badge wall never does.
- Progress feels like promotion: nine piece emblems from pawn to master, drawn with a pen, not nine coloured badges.

## What chess.com does that we do on purpose differently

chess.com's review is a scoreboard: a wall of coloured classification badges, a green "Brilliant" confetti moment, a bright green primary button on every surface, cartoon bot avatars, and a home page of tiles that repeat the navigation. We make the review read like a coach's notebook: the key moments are the headline, each one is a sentence with the better move and why, the classification is an annotation glyph (`!!`, `?`, `??`) printed after the move the way a book prints it, and the colour is one small mark on the square. The board is bone on ink-teal with no gradients or textures, so the eye rests on the pieces. The home page greets the player with their own numbers ("your puzzle rating is 1,240; two positions are due") and shows one next step, not four doors. Bots are drawn in the same pen as the band emblems, so a new bot gets a face from its id without new art. A learner needs to know what to do next and why the last move was wrong; a scoreboard tells neither.

## Type

Two families, clearly different: Schibsted Grotesk for the interface, Newsreader (a book serif) for titles, the big numbers (accuracy, rating) and annotation glyphs. Scale: 13 / 14 / 16 / 18 / 21 / 28 / 40 px (`--fs-xs` to `--fs-3xl`). Body 16 px at 1.5 line height; nothing a player reads is under 13 px. Titles weight 560, headings 650. Line length under 70 characters (`--measure`).

## Layout system

The board is as large as the window allows; text is never squeezed to make room. Classes in `base.css`, sizes in `tokens.css`.
- Shell: full sidebar from 1280 px, an icon rail (64 px) from 901 to 1279 px, the phone tab bar at 900 px and under. Content is centred, at most 1600 px.
- Board page (`.board-page` > `.board-col` + `.side-col`): every page whose task is a board. The board and the thing you act on or read next to it are on screen together, without a scroll.
  1. Beside: the side column sits next to the board whenever the content can give the board `--board-min` (300 px) and the panel `--side-min` (a 640 px window and wider, so a 750 px window keeps both side by side).
  2. Board size: `window height - 2 x --main-pad - --tabbar-h - --board-chrome`, clamped to 300-800 px, and never wider than the width the panel leaves.
  3. Side column: `--side-min` is `clamp(280px, 30vw, 360px)`; the column grows to `--side-max` (560 px) when the board is height-limited.
  4. Phone (under 640 px): the panel stacks below the board, and the board also gives up `--panel-lead`, so the panel's first block (status or prompt and its primary buttons) is visible above the tab bar.
  5. Example: Play at 750 x 700 with `--board-chrome: 112px` gives a 384 px board and a 280 px panel with Hint and Resign at y 377, above the tab bar at 643.
- Page settings, on the page's own `.board-page`, measured, never guessed: `--board-chrome` is the height of the page's own rows above and below the board (page head, player strips, the button row under the board), not the shell padding or the tab bar; `--panel-lead` (default 120 px) is the height of the first panel block on a phone, and that block comes first in the side column.
- Shell: `--main-pad` (32 / 24 / 16 px) is the content padding; `--tabbar-h` is the phone tab bar (57 px plus the safe area), and the content has that much bottom padding so nothing hides under the bar.
- Reading (`.reading`, `.page-head p`): one column, at most 70 characters a line.
- Card grids (`.cards`): auto-fill, no card under 300 px, one column on a phone.
- Density: fewer, larger panels. One side column holds at most three cards; secondary content (ideas, structures, notes) goes in `<details class="fold">`, closed by default. No text under `--fs-xs` (13 px); body copy is `--fs-md`. Spacing comes from `--s-*` and `--gap` only.
- Verify at 390 x 844, 750 x 700, 768 x 900, 1024 x 800 and 1440 x 900: no sideways scroll; the board and the panel's first block visible together; body 16 px, secondary 13 px or more.

## Colour

- Night (default): ink-slate surfaces `--bg #161e27`, `--bg-elev`, `--bg-elev-2`; bone ink `#ece6d9`; brass `--brand #d3a458`.
- Day (`[data-theme="light"]`, set from Settings or the device): warm paper `#f1ece2`, ink `#1b232c`, the same brass darkened to `#8d6522` so it still passes AA as text.
- The board: bone on ink-teal (`--sq-light #e7decb`, `--sq-dark #5a7a8c`) in both themes; three alternatives (boxwood, walnut, slate). Pieces: Colin M.L. Burnett's set (CC BY-SA 3.0, `frontend/src/assets/pieces/ATTRIBUTION.md`).
- State colours are the move classification colours (`--c-brilliant` to `--c-blunder`) and nothing else is coloured. `--danger`, `--warn`, `--ok`, `--info` reuse four of them.
- Measured (scratchpad `contrast.mjs`, 19 pairs per theme): every pair the UI uses passes WCAG AA in both themes (lowest: danger on a card 4.56 at night, warn on a card 4.56 by day).

## Motion

Three durations, two curves, one rule: `--anim-fast` 110 ms for a state flip, `--anim` 180 ms for a piece move, `--anim-slow` 320 ms for a reveal; `--ease` (out) and `--ease-settle` (a small overshoot). Transform and opacity only, never layout. The piece travels under one transform transition and settles with a short scale; check pulses twice; the eval bar is a scaled bar, not a resized one; the coach's bubble, the puzzle verdict and the game result rise or pop in once when they change; a miss shakes; the Rush clock pulses in its last ten seconds. `prefers-reduced-motion` zeroes all three durations. Measured 2026-10-24 on the dev board at 390 px, headless Chromium, six moves by click: 133 frames, median 16.7 ms, p95 26.3 ms; after the first move (one 667 ms frame while the first click warmed things up), 7 of 130 frames went over 25 ms. That is not zero. The next thing to try is dropping `will-change` from the 32 idle pieces.

## Sound

Synthesised in `frontend/src/lib/sound.ts`, no audio files. Pieces are a wooden tock on felt; everything the coach says in sound is a mallet tone. Rising intervals mean good (correct, your turn, award), falling mean no (wrong, lose), a bare tick means time (low clock, the last ten seconds of Rush). Master volume and mute live in Settings, where every sound can be heard by name.

## Illustration

One pen: a 2 px `currentColor` line and a single soft brass fill (`frontend/src/components/art/`). Band emblems are the nine pieces in a roundel; bot faces are generated from the bot id (eyes, brows, mouth, a mark) with a crest for the tier or a hat for the specialty; empty states are a board waiting for a move, a ticked-off puzzle board, a signpost; the home hero is a board corner with the coach's brass arrow. Each drawing is under 2 KB and works on paper and on slate.

## UX audit, 390 px and 1280 px (2026-10-24)

Fixed: a five-tab phone bar with labels and 44 px targets (was 13 unlabelled icons in a scrolling strip at 31 px); `pointer: coarse` raises buttons to 44 px; Home greets with the player's own numbers and one next step (was four tiles repeating the nav and a 22-badge wall); emoji replaced by drawn avatars everywhere; two AA contrast failures at night; empty states on Review, Home and Learn review say what to do; Learn's filters fit one row and the topic list collapses on a phone.

Left: Openings and Master games pages still open with a long list and no "start here"; the Analysis page has no empty-board hint for a first visit; Settings has no keyboard shortcut list; Insights and the Play bots list belong to other agents and were not audited.
