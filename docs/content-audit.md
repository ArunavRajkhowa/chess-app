# Content audit, 2026-10-24

For developers. Nothing reads this file at runtime. Every number below comes from a script run on
the repository on 2026-10-24; "before" means the committed tree (`git show HEAD:...`) when the
audit started, "after" means the working tree when this pass finished.

## What the app teaches with, in numbers

| Content | Before | After | Source |
|---|---|---|---|
| Puzzles | 558 (generated from self-play and master games) | 5,801 (558 + 5,243 from lichess) | `data/puzzles/*.jsonl` |
| Puzzle themes with at least one puzzle | 26 of 42 keys | 59 of 60 keys (only `myMistake`, which is built per player) | `backend/puzzles/store.py` `THEME_INFO` |
| Endgame positions | 24 | 56 | `data/endgames.json` |
| Master games | 125 (41 dated before 1929) | see "Master games" | `data/games/*.pgn` |
| Lessons | 185 lessons, 49 modules, 1,037 sections, 20 lectures | see "Lessons" | `data/lessons/*.json` |
| Opening courses | 6 courses covering 7 of 150 lichess families | unchanged | `data/openings/courses/*.json` |

## Lessons: per band (before)

| Band | Modules | Lessons | Sections | Challenges | Drills | Quizzes | Lectures | Model games | Challenges per lesson | Lessons with no challenge or drill | Lessons with 4 sections or fewer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 Pawn | 3 | 15 | 90 | 31 | 2 | 24 | 3 | 0 | 2.1 | 1 | 0 |
| 1 Knight | 5 | 17 | 101 | 36 | 6 | 19 | 5 | 3 | 2.1 | 0 | 3 |
| 2 Bishop | 7 | 22 | 142 | 55 | 7 | 31 | 6 | 3 | 2.5 | 3 | 0 |
| 3 Rook | 6 | 25 | 173 | 66 | 9 | 32 | 6 | 8 | 2.6 | 0 | 0 |
| 4 Queen | 7 | 26 | 152 | 46 | 7 | 34 | 0 | 13 | 1.8 | 5 | 0 |
| 5 King | 7 | 28 | 140 | 32 | 5 | 45 | 0 | 15 | 1.1 | 10 | 7 |
| 6 Super King | 5 | 21 | 110 | 33 | 3 | 23 | 0 | 18 | 1.6 | 2 | 3 |
| 7 Candidate | 5 | 16 | 68 | 17 | 5 | 13 | 0 | 9 | 1.1 | 2 | 12 |
| 8 Master | 4 | 15 | 61 | 17 | 0 | 9 | 0 | 15 | 1.1 | 3 | 14 |

What is thin:

1. **Bands 4 to 8 had no lecture at all** (0 of 33 modules), against 20 lectures in bands 0 to 3.
   PLAN.md section 3.1 says the lesson shape starts with "show it first, with the pieces moving".
2. **The learner finds less, higher up.** Challenges per lesson fall from 2.6 (band 3) to 1.1
   (bands 5, 7, 8). 26 lessons had no challenge or drill at all: b0m1l1, b2m5l1, b2m5l2, b2m6l1,
   b4m5l3, b4m6l1, b4m6l2, b4m6l3, b4m7l4, b5m2l3, b5m5l1-l4, b5m6l1, b5m6l2, b5m6l5, b5m7l1,
   b5m7l3, b6m3l1, b6m4l1, b7m5l1, b7m5l3, b8m2l1, b8m2l3, b8m3l2. Fixed for bands 5 and 6: each
   of their 12 lessons now has one engine-checked challenge from its model game (0 findings from
   `validate_lessons --engine`).
3. **Short lessons at the top.** 12 of 16 band-7 lessons and 14 of 15 band-8 lessons have 4
   sections or fewer (text, game, one challenge, one quiz).
4. **Practice links pointed at empty puzzle themes.** 12 theme keys that lessons name in
   `practice` had zero puzzles: attraction, deflection, clearance, interference (all of b4m1),
   trappedPiece, capturingDefender, exposedKing, kingsideAttack, smotheredMate, backRankMate,
   defensiveMove, queenEndgame. The lichess import fills every one of them (see Puzzles).
5. **Missing modules** (no lesson teaches it as its subject): converting an advantage, defending
   a worse position, pawn breaks, piece activity against material, a thinking ritual above band 3.
6. **Drills vanish at the top**: band 8 has 0 drills, band 6 has 3.

Where the prose names the pattern before the mechanism: a scan of the first sentence of all 185
text sections for a pattern name (fork, pin, skewer, opposition, Lucena, prophylaxis and 25
others) without a mechanism word (because, cannot, must, attacks both, behind it, would be in
check) flags 17: b1m2l3#0, b2m1l2#0, b2m1l3#0, b2m1l4#0, b2m2l3#0, b2m3l1#1, b3m1l6#0, b3m3l2#0,
b3m3l5#0, b3m4l1#1, b4m1l4#0, b4m2l2#0, b5m6l2#0, b5m6l5#0, b6m5l2#0, b7m1l1#0, b7m1l2#0
(`#n` is the section index). Example, b2m1l2 before: "The knight is the fork specialist." The
fact underneath (a knight attacks up to eight squares, all of the other colour, and no piece can
block it) came later or not at all. The scan is a heuristic: it misses sections that open with a
definition the reader cannot yet use, and it flags recaps.

## Puzzles: per theme and rating band

Before: 558 puzzles, rated 400-1800 by shape, 197 of them (35%) in the 600-799 band. 16 theme keys
had no puzzle: backRankMate, smotheredMate, deflection, attraction, clearance, interference,
zugzwang, trappedPiece, capturingDefender, defensiveMove, exposedKing, kingsideAttack,
queensideAttack, queenEndgame, equality, plus myMistake (built per player). No theme had 30
puzzles in more than two 200-point bands; 12 themes had fewer than 10 puzzles in total.

After: 5,801 puzzles. The lichess sample (`scripts/import_lichess_puzzles.py`, 10 puzzles per
(theme, 200-point band) cell, bands 400 to 2599, Popularity >= 80, NbPlays >= 500,
RatingDeviation <= 100) has 5,243 puzzles, 354 to 509 in each band from 400 to 2599 (358 to 662
per band together with the 558 generated puzzles); 1,028 carry lichess opening tags
(`opening_tags`). The library has 187-315 mate puzzles in every band and 201-350 endgame puzzles
in every band.

Still under 30 puzzles per band (11 bands from 400 to 2599, counts after the import):

| Themes | Bands under 30 |
|---|---|
| skewer, doubleCheck, every named mate (smothered, Anastasia, Arabian, Boden, double bishop, dovetail, hook, kill box, Vukovic), xRayAttack, intermezzo, attackingF2F7, clearance, interference, zugzwang, underPromotion, enPassant, castling, trappedPiece, capturingDefender, queensideAttack, all six endgame-type themes except rookEndgame | 10 or 11 of 11 (about 10 per band: the sampling quota) |
| backRankMate, hangingPiece | 9 |
| deflection, promotion, rookEndgame | 8 to 10 |
| mateIn4, exposedKing | 7 |
| quietMove, defensiveMove, opening | 6 |
| attraction, mateIn1 (above 2000) | 4 to 5 |
| fork, mateIn2, sacrifice, kingsideAttack, advantage | 1 |

Why not more: 30 per cell for every theme would mean about 15,000 puzzles, three times the target
of 4,000-6,000. Raise `--per-cell` when the library may grow; the CSV has 2.55 million puzzles that
pass the quality filters, and every cell above has hundreds of candidates (the rarest,
`doubleBishopMate`, has 1,428 in the whole file).

`equality` stays thin (25): lichess tags only 36 puzzles with it in the whole database.

Lichess themes not imported as keys (they stay on the puzzle but the app shows no filter for
them): discoveredCheck, operaMate, pillsburysMate, epauletteMate, cornerMate, swallowstailMate,
morphysMate, triangleMate, blindSwineMate, balestraMate, collinearMove. The source tags `master`,
`masterVsMaster`, `superGM` are dropped at import: they say who played, not what the puzzle trains.

Verification: every imported puzzle is replayed at load (`store._checked`: 5,243 of 5,243 load).
A random sample of 100 (seed 7) was checked with the generator's `solution_is_unique` at depth 16:
**98 of 100 pass**. The 2 that fail have a second solver move the engine scores within 150 cp at
depth 16: lichess:011o8 (1532, deflection) and lichess:00zu9 (2540, zugzwang).

Rating: `backend/puzzles/difficulty.py` returns the lichess rating (`rating_measured`) when the
puzzle has one, and the shape estimate otherwise. The 558 generated puzzles keep their shape rating.

## Endgames: against de la Villa's 100 and the lichess practice sets

Before (24): five themes, three positions or fewer for each of opposition, the rook pawn, Lucena,
Philidor, Vancura, queen against pawn; nothing on triangulation, protected passed pawn, short-side
defence, rook against minor piece, opposite bishops that win, good knight against bad bishop,
queen against rook (Philidor position), bishop and knight in the right corner, or any mate with Black.

Added (32, each checked with the engine at depth 18, the same check `tests/test_endgames.py`
makes): opposition for the defender, king on the sixth, distant opposition, rook pawn corner, the
square for the defender, protected passed pawn, triangulation, two connected pawns, short-side
defence, king cut off by a file, rook behind the passed pawn, rook against pawn (cut-off), Lucena
for Black, rook pawn in the corner, rook in front of the rook pawn, rook against knight, rook
against bishop (safe corner), the right rook pawn, run to the wrong corner, opposite bishops with
two pawns far apart, good knight against bad bishop, knight against pawn on the seventh, queen
against knight pawn, queen against rook pawn with the king near, queen against rook (Philidor
position), mates with Black (queen, rook, two rooks), queen and rook, two bishops in the corner,
bishop and knight in the right corner (two positions).

Still missing from de la Villa's list (tried and rejected, or not tried):

| Ending | Why not added |
|---|---|
| Same-colour bishops, bishop and pawn against bishop (Centurini) | 6 candidate FENs written from memory scored +0 to +11 cp at depth 18: drawn as set up. Needs a book position. |
| Rook and two pawns against rook, queen and pawn against queen, rook and bishop against rook (Philidor) | Not tried: long wins that the drill's move limit (`max_moves`) and a win_material goal do not measure well. |
| Knight endings with pawns, rook endings with several pawns | Not tried: no single goal (promote, mate) fits them. |
| Corresponding squares beyond simple triangulation | Not tried. |

## Master games

Before: 125 games, 27 theme keys. Thin themes (games): fortress 1, minority-attack 2,
opposite-bishops 2, bishop-pair 3, opening-trap 3, opposite-castling 3, development 4,
blockade 5, iqp 5, zugzwang 5, knight-vs-bishop 6, exchange-sacrifice 7, prophylaxis 7,
rook-endgame 9. Levels are top-heavy: 4 games at level 1, 12 at level 2, against 36 at level 4
and 37 at level 5.

## Openings

6 courses (Caro-Kann, Italian, King's Indian, Queen's Gambit with the Slav, Ruy Lopez, Sicilian
Dragon) cover 7 of the 150 families the lichess book names. The largest families with no course
(lines in the book): French Defense 211, Queen's Gambit Declined 211, English Opening 176, King's
Gambit Accepted 137, Nimzo-Indian Defense 104, Queen's Pawn Game 82, Semi-Slav Defense 72, Dutch
Defense 69, Benoni Defense 66, Queen's Gambit Accepted 63, Grünfeld Defense 59, Queen's Indian
Defense 58, Alekhine Defense 56, Scotch Game 53, Petrov's Defense 50, Four Knights Game 49,
Scandinavian Defense 45, London System 4 (a club favourite the book barely names). Not fixed in
this pass: courses belong to the openings workstream.

## Sources and licences

- Puzzles: the lichess puzzle database, https://database.lichess.org/lichess_db_puzzle.csv.zst,
  CC0. Each puzzle keeps its lichess id (`lichess:<id>`) and its game URL (`source.url`).
- Master-game moves: games played before 1929 (public domain); move scores from the pgnmentor
  player files via the `rozim/ChessData` mirror. The notes are this project's own, checked with
  Stockfish.
- Endgame positions: theoretical positions (de la Villa, *100 Endgames You Must Know*, used as a
  list of what to cover, nothing copied), each set up by hand and verified with Stockfish.
