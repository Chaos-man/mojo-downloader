#!/usr/bin/env python3
"""
Download FSBO and Expired leads from Mojo Sells and upload to Google Drive as Google Sheets.

Flow:
  1. Validate .env variables
  2. Check Google Drive for duplicate sheets (fail fast if found)
  3. Open a browser, log in to Mojo Sells
  4. Navigate to Data & Dialer > FSBO, select all, export — wait for download
  5. Close the task window, switch to Expired, select all, export — wait for download
  6. Upload both .xlsx files to Google Drive as Google Sheets

Usage:
  python mojo_downloader.py [--check-drive] [--dry-run] [--force]
                            [--show-browser] [--test-notification]

Requires:
  pip install -r requirements.txt
  playwright install chromium
"""

import argparse
import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from _mojo import browser as _browser
from _mojo.browser import MOJO_USERNAME, MOJO_PASSWORD, download_exports
from _mojo.drive import (
    CREDENTIALS_FILE,
    GOOGLE_DRIVE_FOLDER_ID,
    SHEET_NAME_FSBO,
    SHEET_NAME_EXPIRED,
    check_sheet_exists,
    get_drive_service,
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
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Mojo Sells lead exporter")
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
        help="Skip the duplicate-sheet check.",
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

    validate_env()
    drive_service = get_drive_service()

    # --check-drive: query Drive for today's sheets and exit.
    if args.check_drive:
        for sheet_name in [SHEET_NAME_FSBO, SHEET_NAME_EXPIRED]:
            exists = check_sheet_exists(drive_service, sheet_name, GOOGLE_DRIVE_FOLDER_ID)
            log.info("%-45s %s", sheet_name, "EXISTS" if exists else "not found")
        sys.exit(0)

    # --force skips the duplicate check; otherwise abort if sheets already exist.
    if not args.force:
        for sheet_name in [SHEET_NAME_FSBO, SHEET_NAME_EXPIRED]:
            log.info("Checking Drive folder for existing sheet '%s'...", sheet_name)
            if check_sheet_exists(drive_service, sheet_name, GOOGLE_DRIVE_FOLDER_ID):
                log.error(
                    "Google Sheet '%s' already exists in the specified folder. "
                    "Delete or rename it, or use --force to skip this check.",
                    sheet_name,
                )
                sys.exit(1)
        log.info("No duplicates found — proceeding.")

    # --show-browser: override the HEADLESS constant in the browser module.
    if args.show_browser:
        _browser.HEADLESS = False

    try:
        fsbo_path, expired_path = retry(download_exports, max_attempts=3, delay_seconds=1800)
    except Exception as exc:
        log.exception("Export failed after all retry attempts.")
        send_failure_email(exc)
        sys.exit(1)

    # --dry-run: skip the Drive upload.
    if args.dry_run:
        log.info("--dry-run: skipping Drive upload. Files saved to:")
        log.info("  FSBO    : %s", fsbo_path)
        log.info("  Expired : %s", expired_path)
        sys.exit(0)

    fsbo_result    = upload_to_drive(drive_service, fsbo_path,    SHEET_NAME_FSBO,    GOOGLE_DRIVE_FOLDER_ID)
    expired_result = upload_to_drive(drive_service, expired_path, SHEET_NAME_EXPIRED, GOOGLE_DRIVE_FOLDER_ID)

    log.info("=" * 60)
    log.info("Done!")
    log.info("  FSBO sheet    : %s  —  %s", fsbo_result["name"],    fsbo_result.get("webViewLink", "N/A"))
    log.info("  Expired sheet : %s  —  %s", expired_result["name"], expired_result.get("webViewLink", "N/A"))
    log.info("=" * 60)


if __name__ == "__main__":
    main()
