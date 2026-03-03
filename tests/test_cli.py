"""Tests for CLI flags in mojo_downloader."""

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

import mojo_downloader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_ENV = {
    "MOJO_USERNAME": "user@example.com",
    "MOJO_PASSWORD": "password",
    "GOOGLE_DRIVE_FOLDER_ID": "folder123",
}

FAKE_PATHS = (Path("/tmp/fsbo.xlsx"), Path("/tmp/expired.xlsx"))


def _mock_drive_service(fsbo_exists=False, expired_exists=False):
    """Return a MagicMock drive service whose check_sheet_exists returns given values."""
    service = MagicMock()
    # files().list().execute() called twice: once for FSBO, once for Expired
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
                with patch("mojo_downloader.retry", return_value=FAKE_PATHS):
                    with patch("mojo_downloader.upload_to_drive", return_value={"name": "s", "webViewLink": "x"}):
                        mojo_downloader.main()
    mock_check.assert_not_called()


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------

def test_dry_run_skips_upload_and_exits_zero(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--dry-run"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False):
                with patch("mojo_downloader.retry", return_value=FAKE_PATHS):
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
    monkeypatch.setattr("mojo_downloader.HEADLESS", True)
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False):
                with patch("mojo_downloader.retry", return_value=FAKE_PATHS):
                    with pytest.raises(SystemExit):
                        mojo_downloader.main()
    assert mojo_downloader.HEADLESS is False


# ---------------------------------------------------------------------------
# Default (no flags) — duplicate check still runs
# ---------------------------------------------------------------------------

def test_default_runs_duplicate_check(monkeypatch, credentials_file):
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py"])
    monkeypatch.setattr("mojo_downloader.CREDENTIALS_FILE", credentials_file)
    with patch.dict("os.environ", REQUIRED_ENV, clear=False):
        with patch("mojo_downloader.get_drive_service", return_value=_mock_drive_service()):
            with patch("mojo_downloader.check_sheet_exists", return_value=False) as mock_check:
                with patch("mojo_downloader.retry", return_value=FAKE_PATHS):
                    with patch("mojo_downloader.upload_to_drive", return_value={"name": "s", "webViewLink": "x"}):
                        mojo_downloader.main()
    assert mock_check.call_count == 2
