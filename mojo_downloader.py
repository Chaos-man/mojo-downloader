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
  python mojo_downloader.py

Requires:
  pip install -r requirements.txt
  playwright install chromium
"""

import logging
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

MOJO_URL = "https://lb11.mojosells.com/login/"
MOJO_USERNAME = os.getenv("MOJO_USERNAME")
MOJO_PASSWORD = os.getenv("MOJO_PASSWORD")

GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# OAuth credential files — keep both out of version control (.gitignore).
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"  # downloaded from Google Cloud Console
TOKEN_FILE = Path(__file__).parent / "token.json"              # auto-created after first auth

SCOPES = ["https://www.googleapis.com/auth/drive"]

DOWNLOADS_DIR = Path(__file__).parent / "downloads"
LOGS_DIR      = Path(__file__).parent / "logs"

SHEET_NAME_FSBO    = f"mojo_export_fsbo_{date.today().isoformat()}"
SHEET_NAME_EXPIRED = f"mojo_export_expired_{date.today().isoformat()}"

# The export can take up to 5 minutes; give it 6 to be safe.
DOWNLOAD_TIMEOUT_MS = 360_000

HEADLESS = True


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

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


log = logging.getLogger("mojo_downloader")


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
# Google Drive helpers
# ---------------------------------------------------------------------------

def get_drive_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Refreshing Google OAuth token...")
            creds.refresh(Request())
        else:
            log.info("Opening browser for one-time Google authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            # Opens a browser tab for one-time authorization. token.json is saved
            # afterward and reused on every subsequent run.
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
        log.info("Google credentials saved to %s", TOKEN_FILE)

    return build("drive", "v3", credentials=creds)


def check_sheet_exists(drive_service, sheet_name: str, folder_id: str) -> bool:
    query = (
        f"name = '{sheet_name}'"
        f" and '{folder_id}' in parents"
        f" and mimeType = 'application/vnd.google-apps.spreadsheet'"
        f" and trashed = false"
    )
    results = drive_service.files().list(
        q=query,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    return len(results.get("files", [])) > 0


def upload_to_drive(drive_service, xlsx_path: Path, sheet_name: str, folder_id: str) -> dict:
    log.info("Uploading '%s' as Google Sheet '%s'...", xlsx_path.name, sheet_name)
    file_metadata = {
        "name": sheet_name,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [folder_id],
    }
    media = MediaFileUpload(
        str(xlsx_path),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=True,
    )
    result = (
        drive_service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return result


# ---------------------------------------------------------------------------
# Browser automation
# ---------------------------------------------------------------------------

def _select_all_and_export(page: Page, label: str) -> Path:
    """Select all records for the current filter, export, and return the saved file path."""

    log.info("Selecting all %s records...", label)
    # Try clicking "Select All" directly; fall back to opening the dropdown first.
    try:
        page.click(
            'button.Checkbox_Checkbox__FWKJN:has-text("Select All")',
            timeout=3000,
        )
    except PlaywrightTimeoutError:
        page.click('.ContactTable_selectAllCheckboxContainer__FzQur')
        page.wait_for_timeout(500)
        page.click('button.Checkbox_Checkbox__FWKJN:has-text("Select All")')

    page.wait_for_timeout(500)

    # First click opens a confirmation modal.
    log.info("Opening %s export dialog...", label)
    page.click('a[role="button"]:has-text("Export")')
    page.wait_for_timeout(500)

    # Second click triggers the actual download. Server may take up to 5 minutes.
    log.info("Confirming %s export — server may take up to 5 minutes to prepare the file...", label)
    with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
        page.click('button.GenericModal_confirmButton__BAaWj:has-text("Export")')

    download = download_info.value
    filename = download.suggested_filename or f"mojo_{label.lower()}_{date.today().isoformat()}.xlsx"
    save_path = DOWNLOADS_DIR / filename
    download.save_as(str(save_path))
    log.info("Downloaded %s: %s", label, save_path)
    return save_path


def download_exports() -> tuple:
    """Run the full browser session and return (fsbo_path, expired_path)."""
    DOWNLOADS_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            # ------------------------------------------------------------------
            # Step 1: Login
            # ------------------------------------------------------------------
            log.info("Navigating to Mojo Sells login page...")
            page.goto(MOJO_URL, wait_until="networkidle")

            page.fill('input[name="email"]', MOJO_USERNAME)
            page.fill('input[name="password"]', MOJO_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            log.info("Logged in.")

            # ------------------------------------------------------------------
            # Step 2: Open the Data & Dialer contacts view
            # ------------------------------------------------------------------
            # Note: The dashboard widgets export all contacts, not the filtered set.
            # Using the Data & Dialer nav button + left-sidebar filter instead.
            #
            # Dashboard widget selectors (for reference only, do not use for export):
            #   FSBO Leads:    button.ProductWidget_widgetElement__RqNtF:has-text("FSBO Leads")
            #   Expired Leads: button.ProductWidget_widgetElement__RqNtF:has-text("Expired Leads")
            log.info("Navigating to Data & Dialer contacts...")
            page.click('#menu-button-my-data')
            page.wait_for_load_state("networkidle")

            # ------------------------------------------------------------------
            # Step 3: FSBO — filter, select all, export
            # ------------------------------------------------------------------
            log.info("Applying FSBO filter...")
            page.click('div.SelectFieldElement_name__RO3oK:has-text("FSBO")')
            page.wait_for_load_state("networkidle")

            fsbo_path = _select_all_and_export(page, "FSBO")

            # ------------------------------------------------------------------
            # Step 4: Close the task/download status window
            # ------------------------------------------------------------------
            # Using img[alt="close"] to avoid escaping the '+' in the CSS class name.
            log.info("Closing task window...")
            page.click('button:has(img[alt="close"])')
            page.wait_for_timeout(500)

            # ------------------------------------------------------------------
            # Step 5: Expired — filter, select all, export
            # ------------------------------------------------------------------
            log.info("Applying Expired filter...")
            page.click('div.SelectFieldElement_name__RO3oK:has-text("Expired")')
            page.wait_for_load_state("networkidle")

            expired_path = _select_all_and_export(page, "Expired")

            return fsbo_path, expired_path

        except Exception as exc:
            log.exception("Browser automation error: %s", exc)
            raise
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# Retry / notification helpers
# ---------------------------------------------------------------------------

def retry(fn, max_attempts: int = 3, delay_seconds: int = 1800):
    """Call fn() up to max_attempts times, waiting delay_seconds between tries."""
    last_exc: Exception = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                log.warning(
                    "Attempt %d/%d failed: %s — retrying in %d minutes.",
                    attempt, max_attempts, exc, delay_seconds // 60,
                )
                time.sleep(delay_seconds)
            else:
                log.error("All %d attempts failed.", max_attempts)
    raise last_exc


def send_failure_email(error: Exception) -> None:
    """Send a failure notification email if SMTP env vars are configured."""
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAIL"]
    cfg = {k: os.getenv(k) for k in required}
    if not all(cfg.values()):
        log.warning("SMTP not configured — skipping failure email.")
        return

    subject = f"[mojo-downloader] Export failed on {date.today().isoformat()}"
    body = (
        f"The mojo-downloader cron job failed after all retry attempts.\n\n"
        f"Error: {type(error).__name__}: {error}\n\n"
        f"Check logs/mojo_downloader.log for the full traceback."
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = cfg["SMTP_USER"]
    msg["To"] = cfg["NOTIFY_EMAIL"]

    try:
        with smtplib.SMTP_SSL(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"])) as server:
            server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            server.send_message(msg)
        log.info("Failure notification sent to %s.", cfg["NOTIFY_EMAIL"])
    except Exception as smtp_exc:
        log.error("Failed to send notification email: %s", smtp_exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()
    log.info("=" * 60)
    log.info("Mojo Downloader started")
    log.info("=" * 60)

    validate_env()

    drive_service = get_drive_service()

    # Check both sheet names before touching the browser.
    for sheet_name in [SHEET_NAME_FSBO, SHEET_NAME_EXPIRED]:
        log.info("Checking Drive folder for existing sheet '%s'...", sheet_name)
        if check_sheet_exists(drive_service, sheet_name, GOOGLE_DRIVE_FOLDER_ID):
            log.error(
                "Google Sheet '%s' already exists in the specified folder. "
                "Delete or rename it before running this script again.",
                sheet_name,
            )
            sys.exit(1)
    log.info("No duplicates found — proceeding.")

    try:
        fsbo_path, expired_path = retry(download_exports, max_attempts=3, delay_seconds=1800)
    except Exception as exc:
        log.exception("Export failed after all retry attempts.")
        send_failure_email(exc)
        sys.exit(1)

    fsbo_result    = upload_to_drive(drive_service, fsbo_path,    SHEET_NAME_FSBO,    GOOGLE_DRIVE_FOLDER_ID)
    expired_result = upload_to_drive(drive_service, expired_path, SHEET_NAME_EXPIRED, GOOGLE_DRIVE_FOLDER_ID)

    log.info("=" * 60)
    log.info("Done!")
    log.info("  FSBO sheet    : %s  —  %s", fsbo_result["name"],    fsbo_result.get("webViewLink", "N/A"))
    log.info("  Expired sheet : %s  —  %s", expired_result["name"], expired_result.get("webViewLink", "N/A"))
    log.info("=" * 60)


if __name__ == "__main__":
    main()
