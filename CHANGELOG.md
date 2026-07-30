# Changelog

All notable changes to this project will be documented in this file.

## [3.1.0] – 2026-07-30
### Added
- Empty-table handling — after applying a table's filter, `_table_is_empty()` checks the contact table's row count; a table with no rows is skipped (no select-all, export, or download attempted) and the next table's filter is still applied
- `download_exports()` now returns `(results, empty_tables)` so callers can distinguish "no data today" from real failures
- Normal, `--cron`, and `--force` modes all exit 0 with a clear log message when every requested table comes back empty, instead of proceeding to the county filter/Drive upload steps or (in `--force`'s case) reporting it as a failure

## [3.0.1] – 2026-07-12
### Fixed
- `networkidle` waits after opening Data & Dialer and after applying a table filter timed out because the Mojo Sells site now holds persistent WebSocket connections open (ProductFruits onboarding widget, activity-stream), which prevented the network from ever going idle — replaced both waits with `page.expect_response()` matched on the `table-data` XHR that actually signals the filtered data has loaded

## [3.0.0] – 2026-05-28
### Added
- County field selection in export modal — `_ensure_county_checked()` automatically checks the County field in the Mojo export dialog before confirming, ensuring it is included in every download
- Post-download county filter — new `_mojo/filter.py` module with `filter_by_county()` removes rows whose county is not in the configured list before uploading to Drive
- `FILTER_COUNTIES` env var — comma-separated list of counties to keep (case-insensitive, spaces supported); leave blank to upload all rows unfiltered
- Failure email notification when the County column is absent from an exported XLSX (export and upload still continue)
- `openpyxl>=3.1.0` added as a runtime dependency
### Fixed
- `--dry-run` was silently blocked by the duplicate-sheet guard when today's sheets already existed on Drive — it now correctly skips that check (since it never uploads anyway)

## [2.2.1] – 2026-03-10
### Fixed
- Unhandled exception when `get_drive_service()` fails in cron mode — now logs, sends failure email, and exits cleanly
### Changed
- CI: code review workflow now uses Haiku 4.5

## [2.2.0] – 2026-03-04
### Added
- `--version` flag
- GitHub Actions release workflow (`release.yml`)
### Fixed
- Path regression introduced when internals moved to `_mojo/`
### Changed
- CI: code review workflow now runs only on PRs marked ready for review
- CI: removed explicit `--model` and `--max-turns` args from code review workflow

## [2.1.0] – 2026-03-03
### Added
- `NOTIFY_FROM` env var to override the From address in failure emails (defaults to `SMTP_USER`)
- STARTTLS support for SMTP — use port 587 instead of 465

## [2.0.0] – 2026-03-03
### Changed
- `MOJO_URL` moved from a hardcoded constant to a required `MOJO_URL` env var

## [1.1.0] – 2026-03-03
### Added
- Retry logic: up to 3 attempts with 30-minute gaps between each
- SMTP failure email sent after all retries are exhausted
- `--cron` CLI flag to enable retry loop and failure notification (for scheduled jobs)
- `MOJO_TABLES` env var to configure which tables to download (default: `FSBO,Expired`)
- `--test-notification`, `--check-drive`, `--show-browser`, `--dry-run`, `--force` CLI flags
- Internals reorganised into the `_mojo/` package (`browser.py`, `drive.py`, `notify.py`)

## [1.0.2] – 2026-03-02
### Changed
- Cron job updated to run at 5:00 AM
- `setup.sh` made idempotent (safe to run multiple times)

## [1.0.1] – 2026-03-01
### Added
- `.gitattributes` to exclude dev files from release archives

## [1.0.0] – 2026-03-01
### Added
- Initial release: Playwright-based Mojo Sells export, Google Drive upload, OAuth2 auth
