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

# Server setup (Linux only — registers 5AM cron job)
bash setup.sh
```

## Architecture

The application is split into five focused modules:

| Module | Responsibility |
|---|---|
| [mojo_downloader.py](mojo_downloader.py) | Entry point — `validate_env()`, `parse_args()`, `main()` |
| [_mojo/log.py](_mojo/log.py) | Logging setup — `LOGS_DIR`, `log`, `setup_logging()` |
| [_mojo/browser.py](_mojo/browser.py) | Playwright automation — login, filter, select-all, county field check, export |
| [_mojo/drive.py](_mojo/drive.py) | Google Drive helpers — OAuth, `check_sheet_exists()`, `upload_to_drive()` |
| [_mojo/filter.py](_mojo/filter.py) | Post-download XLSX filter — `filter_by_county()` |
| [_mojo/notify.py](_mojo/notify.py) | Retry logic and SMTP failure email |

**Execution flow in `main()`:**
1. `setup_logging()` — rotating file log (7-day, 8 backups) + console
2. `validate_env()` — fails fast (sys.exit 1) if `.env` vars or `credentials.json` are missing
3. `get_drive_service()` — OAuth2 flow; reads/writes `token.json`
4. `check_sheet_exists()` — aborts if today's sheets already exist on Drive (skipped by `--force` or `--dry-run`)
5. `retry(download_exports, ...)` — Playwright headless Chromium: login → Data & Dialer → for each table: apply filter, ensure County field is checked in export modal, select all, export; saves to `downloads/`; retries up to 3× on failure
6. `filter_by_county()` — removes rows whose county is not in `FILTER_COUNTIES`; sends failure email if County column is missing from the XLSX
7. `upload_to_drive()` × 2 — uploads each XLSX as a Google Sheet into the configured Drive folder
8. `send_failure_email()` — called only if all retries fail (requires SMTP config in `.env`)

**Browser automation detail (`_select_all_and_export` in browser.py):** attempts a direct "Select All" button click with a 3-second timeout, then falls back to a dropdown. Before confirming the export, `_ensure_county_checked()` finds the County field checkbox in the modal (identified by `div.DataColumns_field__RqWZR` containing the text "County") and checks it if unchecked. The export itself can take up to 5 minutes on the server side; the download timeout is set to 6 minutes (360,000 ms).

## Testing

Tests live in [tests/](tests/) and use `pytest` with mocks (no real network calls):

| File | What it covers |
|---|---|
| `test_validation.py` | `validate_env()` exit conditions |
| `test_drive.py` | Drive API query params, MIME type, sheet name format |
| `test_logging.py` | Handler count, rotation interval, backup count |
| `test_browser.py` | `_select_all_and_export` direct click and dropdown fallback |
| `test_filter.py` | `filter_by_county()` — matching, case-insensitivity, empty set no-op, missing column warning |
| `test_retry.py` | `retry()` — success, partial failure, exhaustion |
| `test_notification.py` | `send_failure_email()` — SMTP call, missing config, `--test-notification` flag |
| `test_cli.py` | All six CLI flags |

Shared fixtures (mocked Drive service, temp `credentials.json`) are in [tests/conftest.py](tests/conftest.py).

## Key Constants

- `mojo_downloader.__version__` — current version string (update when releasing)
- `_mojo.PROJECT_ROOT` — project root path (`Path(__file__).parent.parent`); imported by `browser.py` and `drive.py` for all file paths
- `_mojo.log.LOGS_DIR` — path to the `logs/` directory (`PROJECT_ROOT / "logs"`)
- `_mojo.browser.MOJO_URL` — login URL (from `MOJO_URL` env var, required)
- `_mojo.drive.SHEET_NAME_FSBO` / `_mojo.drive.SHEET_NAME_EXPIRED` — today's sheet names (set at import time)
- `_mojo.browser.DOWNLOAD_TIMEOUT_MS` — 360,000 ms
- `_mojo.browser.HEADLESS` — set to `False` via `--show-browser` flag for local debugging
- `_mojo.filter.COUNTY_COLUMN` — expected header name for the county column in exported XLSX (default: `"County"`); update if Mojo changes the column name

## Release Workflow

1. Update `__version__` in [mojo_downloader.py](mojo_downloader.py)
2. Update [CHANGELOG.md](CHANGELOG.md)
3. `git commit -m "Bump version to X.Y.Z"`
4. `git tag vX.Y.Z`
5. `git push && git push --tags`
6. GitHub Actions (`.github/workflows/release.yml`) creates the GitHub Release automatically

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
