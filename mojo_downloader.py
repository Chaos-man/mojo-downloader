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

import os
import sys
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
SHEET_NAME_FSBO    = f"mojo_export_fsbo_{date.today().isoformat()}"
SHEET_NAME_EXPIRED = f"mojo_export_expired_{date.today().isoformat()}"

# The export can take up to 5 minutes; give it 6 to be safe.
DOWNLOAD_TIMEOUT_MS = 360_000

# Set to True once you've confirmed the selectors work correctly.
HEADLESS = False


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
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: {CREDENTIALS_FILE} not found.")
        print("Download it from Google Cloud Console: APIs & Services > Credentials > your OAuth client > Download JSON")
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
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            # Opens a browser tab for one-time authorization. token.json is saved
            # afterward and reused on every subsequent run.
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

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
    print(f"Uploading '{xlsx_path.name}' as Google Sheet '{sheet_name}'...")
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

    print(f"Selecting all {label} records...")
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
    print(f"Opening {label} export dialog...")
    page.click('a[role="button"]:has-text("Export")')
    page.wait_for_timeout(500)

    # Second click triggers the actual download. Server may take up to 5 minutes.
    print(f"Confirming {label} export — server may take up to 5 minutes to prepare the file...")
    with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
        page.click('button.GenericModal_confirmButton__BAaWj:has-text("Export")')

    download = download_info.value
    filename = download.suggested_filename or f"mojo_{label.lower()}_{date.today().isoformat()}.xlsx"
    save_path = DOWNLOADS_DIR / filename
    download.save_as(str(save_path))
    print(f"Downloaded {label}: {save_path}")
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
            print("Navigating to Mojo Sells login page...")
            page.goto(MOJO_URL, wait_until="networkidle")

            page.fill('input[name="email"]', MOJO_USERNAME)
            page.fill('input[name="password"]', MOJO_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            print("Logged in.")

            # ------------------------------------------------------------------
            # Step 2: Open the Data & Dialer contacts view
            # ------------------------------------------------------------------
            # Note: The dashboard widgets export all contacts, not the filtered set.
            # Using the Data & Dialer nav button + left-sidebar filter instead.
            #
            # Dashboard widget selectors (for reference only, do not use for export):
            #   FSBO Leads:    button.ProductWidget_widgetElement__RqNtF:has-text("FSBO Leads")
            #   Expired Leads: button.ProductWidget_widgetElement__RqNtF:has-text("Expired Leads")
            print("Navigating to Data & Dialer contacts...")
            page.click('#menu-button-my-data')
            page.wait_for_load_state("networkidle")

            # ------------------------------------------------------------------
            # Step 3: FSBO — filter, select all, export
            # ------------------------------------------------------------------
            print("Applying FSBO filter...")
            page.click('div.SelectFieldElement_name__RO3oK:has-text("FSBO")')
            page.wait_for_load_state("networkidle")

            fsbo_path = _select_all_and_export(page, "FSBO")

            # ------------------------------------------------------------------
            # Step 4: Close the task/download status window
            # ------------------------------------------------------------------
            # Using img[alt="close"] to avoid escaping the '+' in the CSS class name.
            print("Closing task window...")
            page.click('button:has(img[alt="close"])')
            page.wait_for_timeout(500)

            # ------------------------------------------------------------------
            # Step 5: Expired — filter, select all, export
            # ------------------------------------------------------------------
            print("Applying Expired filter...")
            page.click('div.SelectFieldElement_name__RO3oK:has-text("Expired")')
            page.wait_for_load_state("networkidle")

            expired_path = _select_all_and_export(page, "Expired")

            return fsbo_path, expired_path

        except PlaywrightTimeoutError as exc:
            print(f"ERROR: Timed out — {exc}")
            sys.exit(1)
        except Exception as exc:
            print(f"ERROR during browser automation: {exc}")
            raise
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    validate_env()

    drive_service = get_drive_service()

    # Check both sheet names before touching the browser.
    for sheet_name in [SHEET_NAME_FSBO, SHEET_NAME_EXPIRED]:
        print(f"Checking Drive folder for existing sheet '{sheet_name}'...")
        if check_sheet_exists(drive_service, sheet_name, GOOGLE_DRIVE_FOLDER_ID):
            print(
                f"ERROR: A Google Sheet named '{sheet_name}' already exists in the specified folder.\n"
                "Delete or rename it before running this script again."
            )
            sys.exit(1)
    print("No duplicates found — proceeding.")

    fsbo_path, expired_path = download_exports()

    fsbo_result    = upload_to_drive(drive_service, fsbo_path,    SHEET_NAME_FSBO,    GOOGLE_DRIVE_FOLDER_ID)
    expired_result = upload_to_drive(drive_service, expired_path, SHEET_NAME_EXPIRED, GOOGLE_DRIVE_FOLDER_ID)

    print("\nDone!")
    print(f"  FSBO sheet    : {fsbo_result['name']}  —  {fsbo_result.get('webViewLink', 'N/A')}")
    print(f"  Expired sheet : {expired_result['name']}  —  {expired_result.get('webViewLink', 'N/A')}")


if __name__ == "__main__":
    main()
