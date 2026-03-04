# Changelog

All notable changes to this project will be documented in this file.

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
