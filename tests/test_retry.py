"""Tests for the retry() helper in mojo_downloader."""

import pytest
from unittest.mock import patch, call

from _mojo import notify
import mojo_downloader


def test_retry_succeeds_first_attempt():
    """No sleep when the function succeeds on the first try."""
    fn = lambda: "ok"
    with patch("_mojo.notify.time.sleep") as mock_sleep:
        result = notify.retry(fn, max_attempts=3, delay_seconds=1800)
    assert result == "ok"
    mock_sleep.assert_not_called()


def test_retry_succeeds_on_second_attempt():
    """Sleeps once then succeeds on the second attempt."""
    outcomes = [ValueError("first fail"), "ok"]

    def fn():
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("_mojo.notify.time.sleep") as mock_sleep:
        result = notify.retry(fn, max_attempts=3, delay_seconds=1800)

    assert result == "ok"
    mock_sleep.assert_called_once_with(1800)


def test_retry_exhausts_all_attempts_raises_last_exception():
    """Raises the last exception after all attempts fail."""
    errors = [ValueError("fail 1"), ValueError("fail 2"), ValueError("fail 3")]

    def fn():
        raise errors.pop(0)

    with patch("_mojo.notify.time.sleep") as mock_sleep:
        with pytest.raises(ValueError, match="fail 3"):
            notify.retry(fn, max_attempts=3, delay_seconds=1800)

    # Sleep called between attempts 1→2 and 2→3 (not after the last failure)
    assert mock_sleep.call_count == 2
    mock_sleep.assert_has_calls([call(1800), call(1800)])


def test_retry_single_attempt_raises_immediately():
    """With max_attempts=1, raises on the first failure without sleeping."""
    with patch("_mojo.notify.time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError, match="boom"):
            notify.retry(lambda: (_ for _ in ()).throw(RuntimeError("boom")), max_attempts=1, delay_seconds=60)
    mock_sleep.assert_not_called()
