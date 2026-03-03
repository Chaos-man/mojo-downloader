"""Playwright browser automation: login, filter, select-all, and export."""

import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

load_dotenv()

log = logging.getLogger("mojo_downloader")

MOJO_URL = "https://lb11.mojosells.com/login/"
MOJO_USERNAME = os.getenv("MOJO_USERNAME")
MOJO_PASSWORD = os.getenv("MOJO_PASSWORD")

DOWNLOADS_DIR = Path(__file__).parent / "downloads"

# The export can take up to 5 minutes; give it 6 to be safe.
DOWNLOAD_TIMEOUT_MS = 360_000

HEADLESS = True


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
