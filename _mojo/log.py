"""Logging configuration for mojo-downloader."""

import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from _mojo import PROJECT_ROOT

LOGS_DIR = PROJECT_ROOT / "logs"

log = logging.getLogger("mojo_downloader")

_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _first_record_time(path: Path) -> int | None:
    """Return the timestamp of the first log record in path, or None if unavailable."""
    try:
        with open(path, encoding="utf-8") as f:
            first_line = f.readline()
        return int(time.mktime(time.strptime(first_line[:19], _DATEFMT)))
    except (OSError, ValueError):
        return None


class _FirstRecordRotatingHandler(TimedRotatingFileHandler):
    """TimedRotatingFileHandler that schedules rollover from the file's first record.

    The stock handler schedules from the file's mtime, so a short-lived process
    that runs daily keeps pushing the rollover a full interval ahead and the file
    never rotates.
    """

    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        first = _first_record_time(Path(self.baseFilename))
        if first is not None:
            self.rolloverAt = self.computeRollover(first)


def setup_logging() -> logging.Logger:
    LOGS_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("mojo_downloader")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt=_DATEFMT,
    )

    # File handler — rotates every 7 days, keeps 8 rotated files (~2 months total).
    file_handler = _FirstRecordRotatingHandler(
        filename=LOGS_DIR / "mojo_downloader.log",
        when="midnight",
        interval=7,
        backupCount=8,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # Console handler — mirrors output to the terminal.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
