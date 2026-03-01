"""Shared fixtures for all test modules."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_drive_service():
    """A MagicMock that mimics the Google Drive service client's method chains."""
    service = MagicMock()

    # files().list(...).execute() — default: no files found
    service.files.return_value.list.return_value.execute.return_value = {"files": []}

    # files().create(...).execute() — default: success response
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "fake_sheet_id",
        "name": "mojo_export_fsbo_2026-03-01",
        "webViewLink": "https://docs.google.com/spreadsheets/d/fake_sheet_id",
    }

    return service


@pytest.fixture
def credentials_file(tmp_path):
    """Write a minimal OAuth credentials.json so file-existence checks pass."""
    creds = tmp_path / "credentials.json"
    creds.write_text('{"installed": {}}')
    return creds
