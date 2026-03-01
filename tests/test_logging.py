"""Tests for the logging setup."""

import logging
from logging.handlers import TimedRotatingFileHandler

import mojo_downloader


def _clear_handlers(logger_name: str):
    """Remove all handlers from a logger so tests don't bleed into each other."""
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()


def test_setup_logging_creates_logs_directory(monkeypatch, tmp_path):
    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(mojo_downloader, "LOGS_DIR", logs_dir)
    try:
        mojo_downloader.setup_logging()
        assert logs_dir.exists()
    finally:
        _clear_handlers("mojo_downloader")


def test_setup_logging_returns_logger(monkeypatch, tmp_path):
    monkeypatch.setattr(mojo_downloader, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = mojo_downloader.setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "mojo_downloader"
    finally:
        _clear_handlers("mojo_downloader")


def test_setup_logging_adds_file_and_console_handlers(monkeypatch, tmp_path):
    monkeypatch.setattr(mojo_downloader, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = mojo_downloader.setup_logging()
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types
        assert TimedRotatingFileHandler in handler_types
    finally:
        _clear_handlers("mojo_downloader")


def test_file_handler_rotates_weekly(monkeypatch, tmp_path):
    monkeypatch.setattr(mojo_downloader, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = mojo_downloader.setup_logging()
        file_handler = next(
            h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler)
        )
        assert file_handler.when == "MIDNIGHT"
        assert file_handler.interval == 60 * 60 * 24 * 7  # 7 days in seconds
    finally:
        _clear_handlers("mojo_downloader")


def test_file_handler_keeps_eight_backups(monkeypatch, tmp_path):
    monkeypatch.setattr(mojo_downloader, "LOGS_DIR", tmp_path / "logs")
    try:
        logger = mojo_downloader.setup_logging()
        file_handler = next(
            h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler)
        )
        assert file_handler.backupCount == 8
    finally:
        _clear_handlers("mojo_downloader")


def test_log_file_is_inside_logs_dir(monkeypatch, tmp_path):
    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(mojo_downloader, "LOGS_DIR", logs_dir)
    try:
        logger = mojo_downloader.setup_logging()
        file_handler = next(
            h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler)
        )
        assert str(logs_dir) in file_handler.baseFilename
    finally:
        _clear_handlers("mojo_downloader")
