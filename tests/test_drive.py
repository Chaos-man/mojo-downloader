"""Tests for Google Drive helper functions and sheet name constants."""

import pytest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import mojo_downloader


# ---------------------------------------------------------------------------
# Sheet name format
# ---------------------------------------------------------------------------

def test_sheet_name_fsbo_format():
    today = date.today().isoformat()
    assert mojo_downloader.SHEET_NAME_FSBO == f"mojo_export_fsbo_{today}"


def test_sheet_name_expired_format():
    today = date.today().isoformat()
    assert mojo_downloader.SHEET_NAME_EXPIRED == f"mojo_export_expired_{today}"


def test_sheet_names_are_distinct():
    assert mojo_downloader.SHEET_NAME_FSBO != mojo_downloader.SHEET_NAME_EXPIRED


# ---------------------------------------------------------------------------
# check_sheet_exists
# ---------------------------------------------------------------------------

def test_check_sheet_exists_returns_true_when_found(mock_drive_service):
    mock_drive_service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "abc123", "name": "mojo_export_fsbo_2026-03-01"}]
    }
    assert mojo_downloader.check_sheet_exists(
        mock_drive_service, "mojo_export_fsbo_2026-03-01", "folder123"
    ) is True


def test_check_sheet_exists_returns_false_when_not_found(mock_drive_service):
    mock_drive_service.files.return_value.list.return_value.execute.return_value = {
        "files": []
    }
    assert mojo_downloader.check_sheet_exists(
        mock_drive_service, "mojo_export_fsbo_2026-03-01", "folder123"
    ) is False


def test_check_sheet_exists_passes_correct_params(mock_drive_service):
    mojo_downloader.check_sheet_exists(mock_drive_service, "my_sheet", "my_folder")
    call_kwargs = mock_drive_service.files.return_value.list.call_args.kwargs
    assert call_kwargs["includeItemsFromAllDrives"] is True
    assert call_kwargs["supportsAllDrives"] is True
    assert "my_sheet" in call_kwargs["q"]
    assert "my_folder" in call_kwargs["q"]


def test_check_sheet_exists_filters_by_spreadsheet_mime(mock_drive_service):
    mojo_downloader.check_sheet_exists(mock_drive_service, "my_sheet", "my_folder")
    q = mock_drive_service.files.return_value.list.call_args.kwargs["q"]
    assert "application/vnd.google-apps.spreadsheet" in q


def test_check_sheet_exists_excludes_trashed(mock_drive_service):
    mojo_downloader.check_sheet_exists(mock_drive_service, "my_sheet", "my_folder")
    q = mock_drive_service.files.return_value.list.call_args.kwargs["q"]
    assert "trashed = false" in q


# ---------------------------------------------------------------------------
# upload_to_drive
# ---------------------------------------------------------------------------

def test_upload_to_drive_returns_api_result(mock_drive_service, tmp_path):
    xlsx = tmp_path / "export.xlsx"
    xlsx.write_bytes(b"fake xlsx content")

    with patch("mojo_downloader.MediaFileUpload"):
        result = mojo_downloader.upload_to_drive(
            mock_drive_service, xlsx, "mojo_export_fsbo_2026-03-01", "folder123"
        )

    assert result["id"] == "fake_sheet_id"
    assert result["name"] == "mojo_export_fsbo_2026-03-01"


def test_upload_to_drive_sets_google_sheet_mime(mock_drive_service, tmp_path):
    xlsx = tmp_path / "export.xlsx"
    xlsx.write_bytes(b"fake xlsx content")

    with patch("mojo_downloader.MediaFileUpload"):
        mojo_downloader.upload_to_drive(
            mock_drive_service, xlsx, "my_sheet", "folder123"
        )

    body = mock_drive_service.files.return_value.create.call_args.kwargs["body"]
    assert body["mimeType"] == "application/vnd.google-apps.spreadsheet"


def test_upload_to_drive_uses_supports_all_drives(mock_drive_service, tmp_path):
    xlsx = tmp_path / "export.xlsx"
    xlsx.write_bytes(b"fake xlsx content")

    with patch("mojo_downloader.MediaFileUpload"):
        mojo_downloader.upload_to_drive(
            mock_drive_service, xlsx, "my_sheet", "folder123"
        )

    kwargs = mock_drive_service.files.return_value.create.call_args.kwargs
    assert kwargs["supportsAllDrives"] is True
