"""Logging configuration for mojo-downloader."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from _mojo import PROJECT_ROOT

LOGS_DIR = PROJECT_ROOT / "logs"

log = logging.getLogger("mojo_downloader")


def setup_logging() -> logging.Logger:
    LOGS_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("mojo_downloader")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — rotates every 7 days, keeps 8 rotated files (~2 months total).
    file_handler = TimedRotatingFileHandler(
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
