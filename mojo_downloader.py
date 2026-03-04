#!/usr/bin/env python3
"""
Download leads from Mojo Sells and upload to Google Drive as Google Sheets.

Flow:
  1. Validate .env variables
  2. Check Google Drive for duplicate sheets (fail fast if found)
  3. Open a browser, log in to Mojo Sells
  4. For each configured table: apply filter, select all, export — wait for download
  5. Upload each .xlsx file to Google Drive as a Google Sheet

Usage:
  python mojo_downloader.py [--check-drive] [--dry-run] [--force] [--cron]
                            [--show-browser] [--test-notification]

Requires:
  pip install -r requirements.txt
  playwright install chromium
"""

import argparse
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

__version__ = "2.1.0"

from _mojo import browser as _browser
from _mojo.browser import MOJO_URL, MOJO_USERNAME, MOJO_PASSWORD, download_exports
from _mojo.drive import (
    CREDENTIALS_FILE,
    GOOGLE_DRIVE_FOLDER_ID,
    check_sheet_exists,
    get_drive_service,
    sheet_name_for,
    upload_to_drive,
)
from _mojo.notify import retry, send_failure_email

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGS_DIR = Path(__file__).parent / "logs"

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


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_env() -> None:
    required = {
        "MOJO_URL": MOJO_URL,
        "MOJO_USERNAME": MOJO_USERNAME,
        "MOJO_PASSWORD": MOJO_PASSWORD,
        "GOOGLE_DRIVE_FOLDER_ID": GOOGLE_DRIVE_FOLDER_ID,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        log.error("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    if not CREDENTIALS_FILE.exists():
        log.error("credentials.json not found at %s", CREDENTIALS_FILE)
        log.error("Download it from Google Cloud Console: APIs & Services > Credentials > your OAuth client > Download JSON")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

DEFAULT_TABLES = ["FSBO", "Expired"]


def parse_tables() -> list[str]:
    """Parse MOJO_TABLES env var into a list of table labels.

    Labels are returned in their original case (used for display and sheet naming).
    All matching against page text is done via .strip().lower() on both sides.
    Returns DEFAULT_TABLES if the var is blank, missing, or contains only whitespace.
    """
    raw = os.getenv("MOJO_TABLES", "").strip()
    if not raw:
        return list(DEFAULT_TABLES)
    tables = [t.strip() for t in raw.split(",") if t.strip()]
    if not tables:
        log.warning("MOJO_TABLES contained no valid entries — using default: %s", DEFAULT_TABLES)
        return list(DEFAULT_TABLES)
    # Deduplicate case-insensitively, preserving first occurrence.
    seen: dict[str, str] = {}
    for t in tables:
        key = t.lower()
        if key in seen:
            log.warning("Duplicate table '%s' in MOJO_TABLES — ignoring.", t)
        else:
            seen[key] = t
    return list(seen.values())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Download FSBO and Expired leads from Mojo Sells and upload to Google Drive.",
        epilog="Run with --cron in scheduled jobs for retry logic and failure email.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--test-notification", action="store_true",
        help="Send a test failure email and exit (verifies SMTP config).",
    )
    parser.add_argument(
        "--check-drive", action="store_true",
        help="Check Drive for today's sheets and exit.",
    )
    parser.add_argument(
        "--show-browser", action="store_true",
        help="Launch Chromium with a visible window instead of headless.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Download exports but skip the Drive upload.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip the duplicate-sheet check and continue past per-table failures.",
    )
    parser.add_argument(
        "--cron", action="store_true",
        help="Enable retry loop (up to 3 attempts) and failure email. Use in scheduled cron jobs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    setup_logging()
    log.info("=" * 60)
    log.info("Mojo Downloader started")
    log.info("=" * 60)

    # --test-notification: fire test email and exit before any other work.
    if args.test_notification:
        log.info("--test-notification: sending test email...")
        send_failure_email(RuntimeError("This is a test notification from mojo-downloader."))
        log.info("--test-notification: done.")
        sys.exit(0)

    # --force and --cron are mutually exclusive.
    if args.force and args.cron:
        log.error("--force and --cron cannot be used together.")
        sys.exit(1)

    validate_env()
    drive_service = get_drive_service()
    tables = parse_tables()

    # --check-drive: query Drive for today's sheets and exit.
    if args.check_drive:
        for table in tables:
            name = sheet_name_for(table)
            exists = check_sheet_exists(drive_service, name, GOOGLE_DRIVE_FOLDER_ID)
            log.info("%-55s %s", name, "EXISTS" if exists else "not found")
        sys.exit(0)

    # Duplicate-sheet guard — skipped only by --force.
    if not args.force:
        for table in tables:
            name = sheet_name_for(table)
            log.info("Checking Drive folder for existing sheet '%s'...", name)
            if check_sheet_exists(drive_service, name, GOOGLE_DRIVE_FOLDER_ID):
                msg = (
                    f"Google Sheet '{name}' already exists in the specified folder. "
                    "Delete or rename it, or use --force to skip this check."
                )
                log.error(msg)
                if args.cron:
                    send_failure_email(RuntimeError(msg))
                sys.exit(1)
        log.info("No duplicates found — proceeding.")

    # --show-browser: override the HEADLESS constant in the browser module.
    if args.show_browser:
        _browser.HEADLESS = False

    # ------------------------------------------------------------------
    # Download — three modes
    # ------------------------------------------------------------------

    if args.cron:
        # Cron mode: retry loop (up to 3×, 30-min delay) + failure email on exhaustion.
        try:
            results = retry(
                lambda: download_exports(tables, continue_on_error=False),
                max_attempts=3,
                delay_seconds=1800,
            )
        except Exception as exc:
            log.exception("Export failed after all retry attempts.")
            send_failure_email(exc)
            sys.exit(1)

    elif args.force:
        # Force mode: continue past per-table errors; upload whatever succeeded.
        results = download_exports(tables, continue_on_error=True)
        if not results:
            log.error("All tables failed to download.")
            sys.exit(1)

    else:
        # Normal mode: single attempt, exit 1 on any failure.
        try:
            results = download_exports(tables, continue_on_error=False)
        except Exception as exc:
            log.error("Download failed: %s", exc)
            sys.exit(1)

    # --dry-run: skip the Drive upload.
    if args.dry_run:
        log.info("--dry-run: skipping Drive upload. Downloaded tables: %s", list(results.keys()))
        for table, path in results.items():
            log.info("  %-20s: %s", table, path)
        sys.exit(0)

    # Upload each downloaded export as a Google Sheet.
    log.info("=" * 60)
    log.info("Uploading results")
    log.info("=" * 60)
    for table, path in results.items():
        name = sheet_name_for(table)
        result = upload_to_drive(drive_service, path, name, GOOGLE_DRIVE_FOLDER_ID)
        log.info("  %-20s: %s  —  %s", table, result["name"], result.get("webViewLink", "N/A"))

    log.info("=" * 60)
    log.info("Done!")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
