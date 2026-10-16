"""One logging configuration for the process: level from LOG_LEVEL, %s templates everywhere."""
from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # python-chess logs every UCI line at DEBUG; keep it quiet unless asked for.
    logging.getLogger("chess.engine").setLevel(logging.WARNING)
