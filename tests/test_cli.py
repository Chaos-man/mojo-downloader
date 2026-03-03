"""Tests for CLI flags in mojo_downloader."""

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from _mojo import browser
import mojo_downloader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_ENV = {
    "MOJO_USERNAME": "user@example.com",
    "MOJO_PASSWORD": "password",
    "GOOGLE_DRIVE_FOLDER_ID": "folder123",
}

FAKE_RESULTS = {
    "FSBO": Path("/tmp/fsbo.xlsx"),
    "Expired": Path("/tmp/expired.xlsx"),
}


def _mock_drive_service(fsbo_exists=False, expired_exists=False):
    """Return a MagicMock drive service whose check_sheet_exists returns given values."""
    service = MagicMock()
    # files().list().execute() called once per table: FSBO then Expired (default tables).
    service.files.return_value.list.return_value.execute.side_effect = [
        {"files": [{"id": "x"}]} if fsbo_exists else {"files": []},
        {"files": [{"id": "x"}]} if expired_exists else {"files": []},
    ]
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "new_id", "name": "sheet", "webViewLink": "http://example.com",
    }
    return service


# ---------------------------------------------------------------------------
# --check-drive
# ---------------------------------------------------------------------------

def test_check_drive_exits_zero(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--check-drive"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with pytest.raises(SystemExit) as exc:
                mojo_downloader.main()
    assert exc.value.code == 0


def test_check_drive_calls_check_sheet_exists_for_both_sheets(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--check-drive"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False) as mock_check:
                with pytest.raises(SystemExit):
                    mojo_downloader.main()
    assert mock_check.call_count == 2


# ---------------------------------------------------------------------------
# --force
# ---------------------------------------------------------------------------

def test_force_skips_duplicate_check(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--force"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists") as mock_check:
                with patch("mojo_downloader.download_exports", return_value=FAKE_RESULTS):
                    with patch("mojo_downloader.upload_to_drive", return_value={"name": "s", "webViewLink": "x"}):
                        mojo_downloader.main()
    mock_check.assert_not_called()


def test_force_passes_continue_on_error(monkeypatch, credentials_file):
    """--force calls download_exports with continue_on_error=True."""
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--force", "--dry-run"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.download_exports", return_value=FAKE_RESULTS) as mock_dl:
                with pytest.raises(SystemExit):
                    mojo_downloader.main()
    _, kwargs = mock_dl.call_args
    assert kwargs.get("continue_on_error") is True


def test_force_uploads_only_successful_tables(monkeypatch, credentials_file):
    """When only some tables succeed, --force uploads only the successful ones."""
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--force"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    partial = {"FSBO": Path("/tmp/fsbo.xlsx")}  # Expired failed and was skipped
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.download_exports", return_value=partial):
                with patch("mojo_downloader.upload_to_drive", return_value={"name": "s", "webViewLink": "x"}) as mock_upload:
                    mojo_downloader.main()
    assert mock_upload.call_count == 1


def test_force_all_tables_fail_exits_one(monkeypatch, credentials_file):
    """When all tables fail in --force mode, exits 1."""
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--force"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.download_exports", return_value={}):
                with pytest.raises(SystemExit) as exc:
                    mojo_downloader.main()
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# --force --cron (incompatible)
# ---------------------------------------------------------------------------

def test_force_cron_together_exits_one(monkeypatch, credentials_file):
    """--force and --cron together exit 1 with an error before any download."""
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--force", "--cron"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.download_exports") as mock_dl:
            with pytest.raises(SystemExit) as exc:
                mojo_downloader.main()
    assert exc.value.code == 1
    mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# --cron
# ---------------------------------------------------------------------------

def test_cron_calls_retry(monkeypatch, credentials_file):
    """--cron mode invokes retry() instead of calling download_exports directly."""
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--cron", "--dry-run"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False):
                with patch("mojo_downloader.retry", return_value=FAKE_RESULTS) as mock_retry:
                    with pytest.raises(SystemExit) as exc:
                        mojo_downloader.main()
    assert exc.value.code == 0
    mock_retry.assert_called_once()


def test_cron_sends_email_on_all_retries_exhausted(monkeypatch, credentials_file):
    """--cron sends failure email and exits 1 when retry() raises."""
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--cron"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False):
                with patch("mojo_downloader.retry", side_effect=RuntimeError("all failed")):
                    with patch("mojo_downloader.send_failure_email") as mock_email:
                        with pytest.raises(SystemExit) as exc:
                            mojo_downloader.main()
    assert exc.value.code == 1
    mock_email.assert_called_once()


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------

def test_dry_run_skips_upload_and_exits_zero(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--dry-run"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False):
                with patch("mojo_downloader.download_exports", return_value=FAKE_RESULTS):
                    with patch("mojo_downloader.upload_to_drive") as mock_upload:
                        with pytest.raises(SystemExit) as exc:
                            mojo_downloader.main()
    assert exc.value.code == 0
    mock_upload.assert_not_called()


# ---------------------------------------------------------------------------
# --show-browser
# ---------------------------------------------------------------------------

def test_show_browser_sets_headless_false(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--show-browser", "--dry-run"])
    monkeypatch.setattr(browser, "HEADLESS", True)
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False):
                with patch("mojo_downloader.download_exports", return_value=FAKE_RESULTS):
                    with pytest.raises(SystemExit):
                        mojo_downloader.main()
    assert browser.HEADLESS is False


# ---------------------------------------------------------------------------
# Default (no flags) — duplicate check still runs
# ---------------------------------------------------------------------------

def test_default_runs_duplicate_check(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False) as mock_check:
                with patch("mojo_downloader.download_exports", return_value=FAKE_RESULTS):
                    with patch("mojo_downloader.upload_to_drive", return_value={"name": "s", "webViewLink": "x"}):
                        mojo_downloader.main()
    assert mock_check.call_count == 2
