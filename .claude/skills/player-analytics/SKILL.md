---
name: player-analytics
description: >
  Answer questions about how chess app players do and where they struggle, with read-only SQL
  against the Turso database (SQLite dialect). Use for "how are players doing", "where do
  players struggle", "which puzzles/lessons/bots are too hard", retention, funnel or cohort
  questions, or /player-analytics.
---

# Player analytics

## 1. Where the data is

- Production: Turso. `turso db shell <db> "<sql>"` after `turso auth login`; `<db>` is the
  first part of the host in `TURSO_DATABASE_URL` in `.env` (`libsql://<db>-<org>.turso.io`).
  Never print the auth token.
- Local: `data/chess.sqlite3`, same dialect (`sqlite3 data/chess.sqlite3`).

## 2. Read the schema now, not from memory

`_SCHEMA` and `_ADDED_COLUMNS` in `backend/storage/db.py` are the truth. Report JSON
(`reviews.report_json`) has the shape built in `backend/review/report.py`; read it before
writing a `json_extract(report_json, '$...')` path. Move labels are the constants in
`backend/review/classify.py`.

## 3. Rules

- `SELECT` only. Never write to production from an analysis.
- Every free-plan row read counts: bound exploration with a `created_at` range and `LIMIT`.
- SQLite dialect: `date(created_at)`, `strftime('%Y-%W', created_at)`, `json_extract`,
  window functions; no `ILIKE`, no `DATE_TRUNC`.
- Absence is data: a player with no games is NULL, not 0. Always show `n`; under 30 say the
  answer is thin.
- Aggregate. Never select or show `email` unless the question is about accounts; never paste
  a list of emails into chat or a document.

## 4. Starter questions

1. In which phase (opening, middlegame, endgame) do players lose the most accuracy, by rating
   band?
2. Which puzzle themes have the lowest solve rate for players under 1200?
3. Which bot is the first one most players never beat?
4. Where do players stop in the curriculum: which lessons are started but not completed?
5. Which move labels (blunder, mistake, miss) dominate per phase and per time control?
6. Of players who finish a first game, how many come back in their second week?

## 5. Answer shape

Per question: the answer in one line with `n`, then the SQL, then the result table. End with
the one finding that should change the product, and how sure it is.
