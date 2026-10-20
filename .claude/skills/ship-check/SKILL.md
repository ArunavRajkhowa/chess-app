---
name: ship-check
description: >
  Pre-commit gate for the chess app: runs this repo's real checks on what changed and reports
  pass or fail with the failing output. Use before any commit or PR, and when the user says
  "ship it", "ready to commit", "check before push", "is this done", or /ship-check.
---

# Ship check

Run from the repo root with the venv active (`.venv`). Run every step that applies; never commit
on a failure, never skip a hook, never "fix" a check by loosening it.

## 1. What changed

`git status --porcelain` and `git diff --cached --name-only`. The changed paths decide which
steps below apply. Say which steps you skipped and why.

## 2. Nothing secret or local is staged

Refuse (name the path) if any staged path is `.env` or `*/.env*` (only `*.env.example` is
tracked), `data/chess.sqlite3*`, `*.pem`, `*.key`, `secrets/`, `frontend/dist/`,
`frontend/public/engine/`. They are gitignored, so a hit means someone force-added it.

## 3. Checks

| When | Command | Passes when |
|---|---|---|
| always | `python -m pytest -q` | 0 failed |
| always | `ruff check .` | no findings |
| `frontend/` changed | `cd frontend && npm run build` (runs `tsc -b` then `vite build`) | exit 0 |
| `frontend/` changed | `cd frontend && npm run lint` | no errors |
| `frontend/` or `backend/routers/` changed | backend on :8765 (`python -m uvicorn backend.app:app --port 8765`), then `cd frontend && npx playwright test` | 0 failed; includes `e2e/mobile.spec.ts` (phone viewport) and `e2e/account.spec.ts` |
| `data/lessons/` changed | `python -m scripts.validate_lessons data/lessons/*.json --engine` | every challenge passes |

## 4. Rules no test catches

- A renamed classification label, puzzle theme, SSE event type or analytics event changed on
  both sides: the backend constant and its mirror in `frontend/src/lib/api.ts`.
- A new env var has a `Settings` field in `backend/settings.py` and a line in `.env.example`.
  A chess or coaching knob is code, not an env var.
- A schema change is additive only: a new column goes in `_ADDED_COLUMNS` in
  `backend/storage/db.py`.
- A bug fix comes with the test that failed before it.

## 5. Report

One table: check, result, time. For a failure, quote the first failing output verbatim and name
the file. Last line: `Ship.` or `Do not ship: <the failing check>.`
