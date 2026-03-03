"""Tests for browser automation helpers."""

import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from _mojo import browser
import mojo_downloader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page_mock(tmp_path, suggested_filename="export.xlsx"):
    """Return a mock Playwright page pre-configured for a successful download."""
    page = MagicMock()

    mock_download = MagicMock()
    mock_download.suggested_filename = suggested_filename

    mock_ctx = MagicMock()
    mock_ctx.value = mock_download

    @contextmanager
    def fake_expect_download(timeout):
        yield mock_ctx

    page.expect_download = fake_expect_download
    return page, mock_download


# ---------------------------------------------------------------------------
# _select_all_and_export
# ---------------------------------------------------------------------------

def test_select_all_direct_click_success(tmp_path, monkeypatch):
    """Select All button is clickable immediately — no dropdown needed."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)
    page, mock_download = _make_page_mock(tmp_path)

    result = browser._select_all_and_export(page, "FSBO")

    # Verify Select All was attempted directly
    page.click.assert_any_call(
        'button.Checkbox_Checkbox__FWKJN:has-text("Select All")',
        timeout=3000,
    )
    # Verify both export clicks happened
    page.click.assert_any_call('a[role="button"]:has-text("Export")')
    page.click.assert_any_call(
        'button.GenericModal_confirmButton__BAaWj:has-text("Export")'
    )


def test_select_all_falls_back_to_dropdown(tmp_path, monkeypatch):
    """When the direct Select All click times out, the dropdown is opened first."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)
    page, _ = _make_page_mock(tmp_path)

    # Make the first Select All click raise a timeout
    def click_side_effect(selector, **kwargs):
        if selector == 'button.Checkbox_Checkbox__FWKJN:has-text("Select All")' \
                and kwargs.get("timeout") == 3000:
            raise PlaywrightTimeoutError("timed out")

    page.click.side_effect = click_side_effect

    browser._select_all_and_export(page, "FSBO")

    clicks = [c.args[0] for c in page.click.call_args_list]
    assert ".ContactTable_selectAllCheckboxContainer__FzQur" in clicks


def test_select_all_saves_file_to_downloads_dir(tmp_path, monkeypatch):
    """Downloaded file is saved inside DOWNLOADS_DIR."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)
    page, mock_download = _make_page_mock(tmp_path, suggested_filename="export_2026-03-01.xlsx")

    result = browser._select_all_and_export(page, "FSBO")

    assert result.parent == tmp_path
    assert result.name == "export_2026-03-01.xlsx"
    mock_download.save_as.assert_called_once_with(str(result))


def test_select_all_uses_fallback_filename_when_none(tmp_path, monkeypatch):
    """Falls back to a generated filename when suggested_filename is empty."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)
    page, mock_download = _make_page_mock(tmp_path, suggested_filename="")

    result = browser._select_all_and_export(page, "Expired")

    assert "expired" in result.name.lower()
    assert result.suffix == ".xlsx"


def test_select_all_uses_label_in_fallback_filename(tmp_path, monkeypatch):
    """The label ('FSBO' or 'Expired') appears in the fallback filename."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)

    for label in ("FSBO", "Expired"):
        page, mock_download = _make_page_mock(tmp_path, suggested_filename="")
        result = browser._select_all_and_export(page, label)
        assert label.lower() in result.name.lower()
