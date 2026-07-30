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
# _table_is_empty
# ---------------------------------------------------------------------------

def test_table_is_empty_when_no_rows():
    """Returns True and logs when the tbody has zero rows."""
    page = MagicMock()
    page.locator.return_value.count.return_value = 0

    assert browser._table_is_empty(page, "FSBO") is True
    page.locator.assert_called_with("tbody.Table_tbody__WYAlK tr")


def test_table_is_empty_when_rows_present():
    """Returns False when the tbody has rows."""
    page = MagicMock()
    page.locator.return_value.count.return_value = 5

    assert browser._table_is_empty(page, "FSBO") is False


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


# ---------------------------------------------------------------------------
# _find_table_filter
# ---------------------------------------------------------------------------

def _make_filter_page(text_content: str):
    """Return a mock page whose filter locator yields one element with the given text."""
    page = MagicMock()
    el = MagicMock()
    el.text_content.return_value = text_content
    page.locator.return_value.all.return_value = [el]
    return page, el


def test_find_table_filter_exact_match():
    """Finds the element when text matches exactly."""
    page, el = _make_filter_page("FSBO")
    assert browser._find_table_filter(page, "FSBO") is el


def test_find_table_filter_case_insensitive():
    """Matches regardless of case in the label or page text."""
    page, el = _make_filter_page("FSBO")
    assert browser._find_table_filter(page, "fsbo") is el


def test_find_table_filter_trims_whitespace():
    """Trims surrounding whitespace from both the label and page text."""
    page, el = _make_filter_page("  FSBO  ")
    assert browser._find_table_filter(page, " fsbo ") is el


def test_find_table_filter_raises_when_not_found():
    """Raises ValueError when no element matches the label."""
    page = MagicMock()
    page.locator.return_value.all.return_value = []
    with pytest.raises(ValueError, match="not found"):
        browser._find_table_filter(page, "NonExistent")


# ---------------------------------------------------------------------------
# download_exports — empty-table handling
# ---------------------------------------------------------------------------

@contextmanager
def _fake_expect_response(predicate, timeout):
    yield MagicMock()


def _make_playwright_mock(page):
    """Return a fake sync_playwright() context manager wired to the given page mock."""
    browser_mock = MagicMock()
    context_mock = MagicMock()
    context_mock.new_page.return_value = page
    browser_mock.new_context.return_value = context_mock
    p_mock = MagicMock()
    p_mock.chromium.launch.return_value = browser_mock

    @contextmanager
    def fake_sync_playwright():
        yield p_mock

    return fake_sync_playwright


def test_download_exports_skips_empty_table_and_continues(monkeypatch, tmp_path):
    """An empty table is skipped (no export attempted) and the next table's filter is still applied."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)

    page = MagicMock()
    page.expect_response = _fake_expect_response
    page.locator.return_value.count.return_value = 0
    monkeypatch.setattr(browser, "sync_playwright", _make_playwright_mock(page))

    fsbo_el, expired_el = MagicMock(), MagicMock()
    monkeypatch.setattr(
        browser, "_find_table_filter",
        lambda page, label: fsbo_el if label == "FSBO" else expired_el,
    )
    monkeypatch.setattr(browser, "_table_is_empty", lambda page, label: label == "FSBO")
    export_path = tmp_path / "expired.xlsx"
    mock_export = MagicMock(return_value=export_path)
    monkeypatch.setattr(browser, "_select_all_and_export", mock_export)

    results, empty_tables = browser.download_exports(["FSBO", "Expired"], continue_on_error=False)

    assert empty_tables == ["FSBO"]
    assert results == {"Expired": export_path}
    fsbo_el.click.assert_called_once()
    expired_el.click.assert_called_once()
    mock_export.assert_called_once_with(page, "Expired")


def test_download_exports_raises_clear_error_on_invalid_login(monkeypatch, tmp_path):
    """A visible '.Form_NonFieldErrors__el6fn' after submit raises a clear login error
    instead of proceeding to navigation and failing later with an unrelated timeout."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)

    page = MagicMock()
    page.expect_response = _fake_expect_response
    error_el = page.locator.return_value
    error_el.count.return_value = 1
    error_el.first.is_visible.return_value = True
    error_el.first.text_content.return_value = "Invalid login/password"
    monkeypatch.setattr(browser, "sync_playwright", _make_playwright_mock(page))

    with pytest.raises(RuntimeError, match="Invalid login/password"):
        browser.download_exports(["FSBO", "Expired"], continue_on_error=False)

    page.click.assert_any_call('button[type="submit"]')
    # Must not have proceeded to click the Data & Dialer nav button.
    assert call('#menu-button-my-data') not in page.click.call_args_list


def test_download_exports_all_tables_empty(monkeypatch, tmp_path):
    """When every table is empty, results is empty and empty_tables lists them all."""
    monkeypatch.setattr(browser, "DOWNLOADS_DIR", tmp_path)

    page = MagicMock()
    page.expect_response = _fake_expect_response
    page.locator.return_value.count.return_value = 0
    monkeypatch.setattr(browser, "sync_playwright", _make_playwright_mock(page))

    monkeypatch.setattr(browser, "_find_table_filter", lambda page, label: MagicMock())
    monkeypatch.setattr(browser, "_table_is_empty", lambda page, label: True)
    mock_export = MagicMock()
    monkeypatch.setattr(browser, "_select_all_and_export", mock_export)

    results, empty_tables = browser.download_exports(["FSBO", "Expired"], continue_on_error=False)

    assert results == {}
    assert empty_tables == ["FSBO", "Expired"]
    mock_export.assert_not_called()
