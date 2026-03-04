"""Tests for validate_env()."""

import pytest
import mojo_downloader


def _patch_all_valid(monkeypatch, credentials_file):
    """Patch every required variable to a valid state."""
    monkeypatch.setattr(mojo_downloader, "MOJO_URL", "https://example.com/login/")
    monkeypatch.setattr(mojo_downloader, "MOJO_USERNAME", "user@example.com")
    monkeypatch.setattr(mojo_downloader, "MOJO_PASSWORD", "secret")
    monkeypatch.setattr(mojo_downloader, "GOOGLE_DRIVE_FOLDER_ID", "folder123")
    monkeypatch.setattr(mojo_downloader, "CREDENTIALS_FILE", credentials_file)


def test_validate_env_passes_when_all_present(monkeypatch, credentials_file):
    _patch_all_valid(monkeypatch, credentials_file)
    mojo_downloader.validate_env()  # should not raise


def test_validate_env_exits_when_url_missing(monkeypatch, credentials_file):
    _patch_all_valid(monkeypatch, credentials_file)
    monkeypatch.setattr(mojo_downloader, "MOJO_URL", None)
    with pytest.raises(SystemExit):
        mojo_downloader.validate_env()


def test_validate_env_exits_when_username_missing(monkeypatch, credentials_file):
    _patch_all_valid(monkeypatch, credentials_file)
    monkeypatch.setattr(mojo_downloader, "MOJO_USERNAME", None)
    with pytest.raises(SystemExit):
        mojo_downloader.validate_env()


def test_validate_env_exits_when_password_missing(monkeypatch, credentials_file):
    _patch_all_valid(monkeypatch, credentials_file)
    monkeypatch.setattr(mojo_downloader, "MOJO_PASSWORD", None)
    with pytest.raises(SystemExit):
        mojo_downloader.validate_env()


def test_validate_env_exits_when_folder_id_missing(monkeypatch, credentials_file):
    _patch_all_valid(monkeypatch, credentials_file)
    monkeypatch.setattr(mojo_downloader, "GOOGLE_DRIVE_FOLDER_ID", None)
    with pytest.raises(SystemExit):
        mojo_downloader.validate_env()


def test_validate_env_exits_when_credentials_file_missing(monkeypatch, tmp_path):
    _patch_all_valid(monkeypatch, tmp_path / "credentials.json")  # file does not exist
    with pytest.raises(SystemExit):
        mojo_downloader.validate_env()


def test_validate_env_exits_when_multiple_vars_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(mojo_downloader, "MOJO_USERNAME", None)
    monkeypatch.setattr(mojo_downloader, "MOJO_PASSWORD", None)
    monkeypatch.setattr(mojo_downloader, "GOOGLE_DRIVE_FOLDER_ID", "folder123")
    monkeypatch.setattr(mojo_downloader, "CREDENTIALS_FILE", tmp_path / "credentials.json")
    with pytest.raises(SystemExit):
        mojo_downloader.validate_env()
