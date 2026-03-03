# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Automates nightly export of FSBO and Expired leads from [Mojo Sells](https://lb11.mojosells.com/login/) and uploads them to Google Drive as Google Sheets. The two output sheets are named `mojo_export_fsbo_YYYY-MM-DD` and `mojo_export_expired_YYYY-MM-DD`.

## Environment Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements-dev.txt
playwright install chromium
```

Copy `.env.example` to `.env` and fill in credentials. Place `credentials.json` (Google OAuth) in the project root.

## Common Commands

```bash
# Run the downloader
python mojo_downloader.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_drive.py

# Run a single test by name
pytest tests/test_drive.py::test_check_sheet_exists_returns_true

# Server setup (Linux only — registers 1AM cron job)
bash setup.sh
```

## Architecture

The entire application lives in a single file: [mojo_downloader.py](mojo_downloader.py).

**Execution flow in `main()`:**
1. `setup_logging()` — rotating file log (7-day, 8 backups) + console
2. `validate_env()` — fails fast (sys.exit 1) if `.env` vars or `credentials.json` are missing
3. `get_drive_service()` — OAuth2 flow; reads/writes `token.json`
4. `check_sheet_exists()` — aborts if today's sheets already exist on Drive (prevents duplicates)
5. `download_exports()` — Playwright headless Chromium: login → Data & Dialer → export FSBO → export Expired; saves to `downloads/`
6. `upload_to_drive()` × 2 — uploads each XLSX as a Google Sheet into the configured Drive folder

**Browser automation detail (`_select_all_and_export`):** attempts a direct "Select All" button click with a 3-second timeout, then falls back to a dropdown. The export itself can take up to 5 minutes on the server side; the download timeout is set to 6 minutes (360,000 ms).

## Testing

Tests live in [tests/](tests/) and use `pytest` with mocks (no real network calls):

| File | What it covers |
|---|---|
| `test_validation.py` | `validate_env()` exit conditions |
| `test_drive.py` | Drive API query params, MIME type, sheet name format |
| `test_logging.py` | Handler count, rotation interval, backup count |
| `test_browser.py` | `_select_all_and_export` direct click and dropdown fallback |

Shared fixtures (mocked Drive service, temp `credentials.json`) are in [tests/conftest.py](tests/conftest.py).

## Key Constants (top of mojo_downloader.py)

- `MOJO_URL` — login URL
- `SHEET_NAME_FSBO` / `SHEET_NAME_EXPIRED` — today's sheet names (set at import time)
- `DOWNLOAD_TIMEOUT` — 360,000 ms
- `HEADLESS = True` — set to `False` for local debugging of browser steps
