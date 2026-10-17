"""Checks the coach's model setup the way the app uses it: sends one short question, prints the
streamed answer, the time to the first text and the token counts the server reported.
Usage: python -m scripts.check_coach   (reads COACH_BASE_URL, COACH_MODEL, COACH_API_KEY from .env)"""
from __future__ import annotations

import asyncio
import time

from backend.coach import client
from backend.settings import settings
from backend.storage.db import database

QUESTION = "In two sentences: why is it good to control the centre in the opening?"


async def main() -> int:
    if problem := client.llm_problem():
        print(problem)
        return 1
    if not client.llm_enabled():
        print("No coach model is set. Fill COACH_BASE_URL and COACH_MODEL in .env (see .env.example).")
        return 1
    where = settings.COACH_BASE_URL if client.llm_provider() == client.PROVIDER_OPENAI else "Anthropic"
    print(f"provider={client.llm_provider()} model={client.llm_model()} at {where}")
    await database.start()
    started = time.monotonic()
    first: float | None = None
    try:
        async for text in client.stream_text(system=client.prompt("coach_system"), user=QUESTION, purpose="check"):
            first = first or time.monotonic() - started
            print(text, end="", flush=True)
    except client.CoachDeclined as exc:
        print(f"\nThe model gave no usable answer: {exc}")
        return 1
    except Exception as exc:  # boundary: a script that reports why the setup failed
        print(f"\nThe call failed: {exc}")
        print("Check: is the server running? is COACH_BASE_URL right (it ends in /v1)? is COACH_API_KEY valid? is COACH_MODEL spelled as the server lists it?")
        return 1
    finally:
        row = (await database.fetch_all("SELECT input_tokens, output_tokens, usage_reported FROM coach_cost ORDER BY id DESC LIMIT 1")) or [None]
        await database.stop()
    tokens = f"in={row[0]['input_tokens']} out={row[0]['output_tokens']}" if row[0] and row[0]["usage_reported"] else "the server did not report token counts"
    print(f"\n\nfirst text after {first:.1f}s, total {time.monotonic() - started:.1f}s, {tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
