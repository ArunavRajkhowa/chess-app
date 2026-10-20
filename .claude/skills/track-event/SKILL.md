---
name: track-event
description: >
  How to add or change a product analytics event in the chess app without leaking personal data
  or duplicating what the store already holds. Use when a feature ships or changes and someone
  asks "track this", "add an event", "what should we measure", "instrument this feature", or
  /track-event.
---

# Track an event

## 1. Is it already stored?

Gameplay is already in the store in full detail, per player: `games`, `reviews`,
`puzzle_attempts`, `player_lessons`, `player_values` (ratings, rush and endgame history),
`players` (first seen, sign-in), `coach_cost` (schema: `backend/storage/db.py`). A fact those
tables hold is queried there (see `/player-analytics`), never re-sent as an event.

Events are for what the store does not see: a screen opened, a feature used (hint, takeback,
flip, coach question asked), app installed, signed in, a setting changed, a flow abandoned.

## 2. Prefer a property over a new event

`hint.used {level: 2}` beats `hint_level_2.used`. Ask: will anyone query this event on its own?
If not, it is a property on an existing event.

## 3. Name it

`object.action`, snake_case, past tense, the outcome not the button: `puzzle_rush.finished`,
not `rush_end_button.clicked`. Match the names already in the list.

## 4. Declare it once, mirror it once

- Backend: add the name and its allowed property keys to `EVENT_PROPS` in
  `backend/routers/events.py`. The API refuses an unknown name, an unknown key, and any text
  value that is not a short identifier (`[a-z0-9_.:/-]{1,64}`).
- Frontend: add the same name and props to `EventProps` in `frontend/src/lib/api.ts`, then call
  `track("hint.used", { level: 2 })` (`frontend/src/lib/track.ts`) where the outcome happens.
  It is fire-and-forget; it never blocks or delays the UI. App-wide events live in
  `frontend/src/components/account/Analytics.tsx`.
- Test: one case in `tests/test_accounts.py` that the new event is stored and a bad prop is refused.

## 5. Properties: no personal data

Flat object. Values are numbers, booleans, or short identifiers from a closed set (a bot id,
a page key, a lesson id, a puzzle theme, a time control).

Never: free text, email, a name (PGN `White`/`Black` headers are names), IP address, the full
user agent, location finer than country, the coach question text. Who the player is comes
from the session on the server, never from props.

No high-frequency noise: not every move, hover or scroll.

## 6. Done when

`/ship-check` passes, and the event appears in the events table after one manual run of the
flow on the dev server.
