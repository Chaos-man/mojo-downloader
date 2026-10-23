"""Tests for the logging setup."""

import logging
import os
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

import _mojo.log as log_module


def _clear_handlers(logger_name: str):
    """Remove all handlers from a logger so tests don't bleed into each other."""
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()


def test_setup_logging_creates_logs_directory(monkeypatch, tmp_path):
    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(log_module, "LOGS_DIR", logs_dir)
    try:
        log_module.setup_logging()
        assert logs_dir.exists()
    finally:
        _clear_handlers("mojo_downloader")


def test_setup_logging_returns_logger(monkeypatch, tmp_path):
    monkeypatch.setattr(log_module, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = log_module.setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "mojo_downloader"
    finally:
        _clear_handlers("mojo_downloader")


def test_setup_logging_adds_file_and_console_handlers(monkeypatch, tmp_path):
    monkeypatch.setattr(log_module, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = log_module.setup_logging()
        assert any(type(h) is logging.StreamHandler for h in logger.handlers)
        assert any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers)
    finally:
        _clear_handlers("mojo_downloader")


def test_file_handler_rotates_weekly(monkeypatch, tmp_path):
    monkeypatch.setattr(log_module, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = log_module.setup_logging()
        file_handler = next(
            h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler)
        )
        assert file_handler.when == "MIDNIGHT"
        assert file_handler.interval == 60 * 60 * 24 * 7  # 7 days in seconds
    finally:
        _clear_handlers("mojo_downloader")


def test_file_handler_keeps_eight_backups(monkeypatch, tmp_path):
    monkeypatch.setattr(log_module, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = log_module.setup_logging()
        file_handler = next(
            h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler)
        )
        assert file_handler.backupCount == 8
    finally:
        _clear_handlers("mojo_downloader")


def test_log_file_is_inside_logs_dir(monkeypatch, tmp_path):
    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(log_module, "LOGS_DIR", logs_dir)
    try:
        logger = log_module.setup_logging()
        file_handler = next(
            h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler)
        )
        assert str(logs_dir) in file_handler.baseFilename
    finally:
        _clear_handlers("mojo_downloader")


# ---------------------------------------------------------------------------
# Rollover scheduling for short-lived daily runs
# ---------------------------------------------------------------------------

def _close_handlers(logger_name: str):
    """Close and remove handlers so the log file is released (needed on Windows)."""
    logger = logging.getLogger(logger_name)
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def _write_existing_log(logs_dir, first_record: datetime, mtime: datetime):
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "mojo_downloader.log"
    path.write_text(
        f"{first_record:%Y-%m-%d %H:%M:%S} [INFO    ] first run\n"
        f"{mtime:%Y-%m-%d %H:%M:%S} [INFO    ] latest run\n",
        encoding="utf-8",
    )
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))
    return path


def test_log_rotates_when_first_record_is_older_than_interval(monkeypatch, tmp_path):
    """Regression: a log written daily (mtime = yesterday) whose first record is
    8 days old must rotate on the next run. The stock handler schedules rollover
    from mtime, so a daily run kept pushing it forward and the file never rotated."""
    logs_dir = tmp_path / "logs"
    now = datetime.now()
    path = _write_existing_log(logs_dir, now - timedelta(days=8), now - timedelta(days=1))
    monkeypatch.setattr(log_module, "LOGS_DIR", logs_dir)
    try:
        logger = log_module.setup_logging()
        logger.info("new run")
    finally:
        _close_handlers("mojo_downloader")

    backups = list(logs_dir.glob("mojo_downloader.log.*"))
    assert len(backups) == 1
    assert "first run" in backups[0].read_text(encoding="utf-8")
    current = path.read_text(encoding="utf-8")
    assert "new run" in current
    assert "first run" not in current


def test_log_does_not_rotate_when_first_record_is_recent(monkeypatch, tmp_path):
    logs_dir = tmp_path / "logs"
    now = datetime.now()
    path = _write_existing_log(logs_dir, now - timedelta(days=3), now - timedelta(days=1))
    monkeypatch.setattr(log_module, "LOGS_DIR", logs_dir)
    try:
        logger = log_module.setup_logging()
        logger.info("new run")
    finally:
        _close_handlers("mojo_downloader")

    assert list(logs_dir.glob("mojo_downloader.log.*")) == []
    current = path.read_text(encoding="utf-8")
    assert "first run" in current and "new run" in current


def test_log_with_empty_or_unparseable_file_does_not_crash(monkeypatch, tmp_path):
    """An empty file or a first line without a timestamp falls back to default behaviour."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr(log_module, "LOGS_DIR", logs_dir)
    for content in ("", "Traceback (most recent call last):\n"):
        (logs_dir / "mojo_downloader.log").write_text(content, encoding="utf-8")
        try:
            logger = log_module.setup_logging()
            logger.info("new run")
        finally:
            _close_handlers("mojo_downloader")
        assert list(logs_dir.glob("mojo_downloader.log.*")) == []


def test_setup_logging_without_console_adds_only_file_handler(monkeypatch, tmp_path):
    """console=False (used by --cron) skips the console handler so cron.log
    doesn't duplicate the whole file log."""
    monkeypatch.setattr(log_module, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = log_module.setup_logging(console=False)
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], TimedRotatingFileHandler)
    finally:
        _close_handlers("mojo_downloader")
