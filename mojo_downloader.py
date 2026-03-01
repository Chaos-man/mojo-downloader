#!/usr/bin/env python3
"""
Download FSBO leads from Mojo Sells and upload to Google Drive as a Google Sheet.

Flow:
  1. Validate .env variables
  2. Check Google Drive for a duplicate sheet (fail fast if found)
  3. Open a browser, log in to Mojo Sells
  4. Navigate to Contacts > FSBO
  5. Select all records, click Export, and wait for the .xlsx download
  6. Upload the .xlsx to Google Drive, converting it to a Google Sheet

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
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

MOJO_URL = "https://lb11.mojosells.com/login/"
MOJO_USERNAME = os.getenv("MOJO_USERNAME")
MOJO_PASSWORD = os.getenv("MOJO_PASSWORD")

GOOGLE_SERVICE_ACCOUNT_EMAIL = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL")
# .env stores the key with literal \n; we convert them to real newlines here.
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

DOWNLOADS_DIR = Path(__file__).parent / "downloads"
SHEET_NAME = f"mojo_export_fsbo_{date.today().isoformat()}"

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
        "GOOGLE_SERVICE_ACCOUNT_EMAIL": GOOGLE_SERVICE_ACCOUNT_EMAIL,
        "GOOGLE_PRIVATE_KEY": GOOGLE_PRIVATE_KEY,
        "GOOGLE_DRIVE_FOLDER_ID": GOOGLE_DRIVE_FOLDER_ID,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Google Drive helpers
# ---------------------------------------------------------------------------

def get_drive_service():
    service_account_info = {
        "type": "service_account",
        "client_email": GOOGLE_SERVICE_ACCOUNT_EMAIL,
        "private_key": GOOGLE_PRIVATE_KEY,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=credentials)


def check_sheet_exists(drive_service, sheet_name: str, folder_id: str) -> bool:
    query = (
        f"name = '{sheet_name}'"
        f" and '{folder_id}' in parents"
        f" and mimeType = 'application/vnd.google-apps.spreadsheet'"
        f" and trashed = false"
    )
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
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
        .create(body=file_metadata, media_body=media, fields="id, name, webViewLink")
        .execute()
    )
    return result


# ---------------------------------------------------------------------------
# Browser automation
# ---------------------------------------------------------------------------

def download_fsbo_export() -> Path:
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
            # Step 2: Click the FSBO Leads widget on the dashboard
            # ------------------------------------------------------------------
            # The dashboard shows product widgets immediately after login.
            # Clicking "FSBO Leads" takes us directly to the FSBO contacts table.
            #
            # Future: to download Expired Leads instead, swap in:
            #   button.ProductWidget_widgetElement__RqNtF:has-text("Expired Leads")
            print("Clicking FSBO Leads widget...")
            page.click('button.ProductWidget_widgetElement__RqNtF:has-text("FSBO Leads")')
            page.wait_for_load_state("networkidle")

            # ------------------------------------------------------------------
            # Step 4: Select all records
            # ------------------------------------------------------------------
            # Try clicking the "Select All" button directly first. If it isn't
            # visible yet, fall back to opening the dropdown arrow first.
            print("Selecting all records...")
            try:
                page.click(
                    'button.Checkbox_Checkbox__FWKJN:has-text("Select All")',
                    timeout=3000,
                )
            except PlaywrightTimeoutError:
                # Open the dropdown arrow next to the header checkbox, then click
                # the "Select All" option that appears.
                page.click('.ContactTable_selectAllCheckboxContainer__FzQur')
                page.wait_for_timeout(500)
                page.click('button.Checkbox_Checkbox__FWKJN:has-text("Select All")')

            page.wait_for_timeout(500)

            # ------------------------------------------------------------------
            # Step 5: Click Export and wait for the download
            # ------------------------------------------------------------------
            print(
                "Clicking Export — the server may take up to 5 minutes to prepare the file..."
            )
            with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
                page.click('a[role="button"]:has-text("Export")')

            download = download_info.value
            filename = download.suggested_filename or f"mojo_fsbo_{date.today().isoformat()}.xlsx"
            save_path = DOWNLOADS_DIR / filename
            download.save_as(str(save_path))
            print(f"Downloaded: {save_path}")
            return save_path

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

    # Fail fast before touching the browser if the sheet already exists.
    print(f"Checking Drive folder for existing sheet '{SHEET_NAME}'...")
    if check_sheet_exists(drive_service, SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID):
        print(
            f"ERROR: A Google Sheet named '{SHEET_NAME}' already exists in the specified folder.\n"
            "Delete or rename it before running this script again."
        )
        sys.exit(1)
    print("No duplicate found — proceeding.")

    xlsx_path = download_fsbo_export()

    result = upload_to_drive(drive_service, xlsx_path, SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID)

    print("\nDone!")
    print(f"  Sheet name : {result['name']}")
    print(f"  Drive link : {result.get('webViewLink', 'N/A')}")


if __name__ == "__main__":
    main()
