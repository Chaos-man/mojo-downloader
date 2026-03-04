"""Tests for the send_failure_email() helper in mojo_downloader."""

import pytest
from unittest.mock import patch, MagicMock

import mojo_downloader


SMTP_ENV = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "465",
    "SMTP_USER": "sender@example.com",
    "SMTP_PASSWORD": "secret",
    "NOTIFY_EMAIL": "recipient@example.com",
}


def test_sends_email_when_smtp_configured():
    """Calls SMTP_SSL, logs in, and sends the message when all vars are set."""
    error = RuntimeError("download timed out")
    mock_server = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_server)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch.dict("os.environ", SMTP_ENV, clear=False):
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx) as mock_smtp:
            mojo_downloader.send_failure_email(error)

    mock_smtp.assert_called_once_with("smtp.gmail.com", 465)
    mock_server.login.assert_called_once_with("sender@example.com", "secret")
    mock_server.send_message.assert_called_once()

    # Verify message content
    sent_msg = mock_server.send_message.call_args[0][0]
    assert "mojo-downloader" in sent_msg["Subject"]
    assert "RuntimeError" in sent_msg.get_payload()
    assert "download timed out" in sent_msg.get_payload()


def test_skips_email_when_smtp_vars_missing(monkeypatch):
    """Logs a warning and does not attempt SMTP when vars are absent."""
    for key in SMTP_ENV:
        monkeypatch.delenv(key, raising=False)

    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mojo_downloader.send_failure_email(RuntimeError("fail"))

    mock_smtp.assert_not_called()


def test_skips_email_when_one_smtp_var_missing(monkeypatch):
    """Even a single missing var prevents the email from being sent."""
    for key, val in SMTP_ENV.items():
        monkeypatch.setenv(key, val)
    monkeypatch.delenv("SMTP_PASSWORD")

    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mojo_downloader.send_failure_email(RuntimeError("fail"))

    mock_smtp.assert_not_called()


def test_test_notification_flag_sends_email_and_exits(monkeypatch):
    """--test-notification calls send_failure_email() then exits 0."""
    monkeypatch.setattr("sys.argv", ["mojo_downloader.py", "--test-notification"])
    mock_server = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_server)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch.dict("os.environ", SMTP_ENV, clear=False):
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx):
            with pytest.raises(SystemExit) as exc:
                mojo_downloader.main()

    assert exc.value.code == 0
    mock_server.send_message.assert_called_once()


def test_sends_email_via_starttls_on_port_587():
    """Uses SMTP + starttls() when SMTP_PORT is 587."""
    error = RuntimeError("test error")
    mock_server = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_server)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    env = {**SMTP_ENV, "SMTP_PORT": "587"}
    with patch.dict("os.environ", env, clear=False):
        with patch("smtplib.SMTP", return_value=mock_ctx) as mock_smtp:
            with patch("smtplib.SMTP_SSL") as mock_ssl:
                mojo_downloader.send_failure_email(error)

    mock_smtp.assert_called_once_with("smtp.gmail.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("sender@example.com", "secret")
    mock_server.send_message.assert_called_once()
    mock_ssl.assert_not_called()


def test_sends_email_with_notify_from_override():
    """Uses NOTIFY_FROM as the From address when set."""
    error = RuntimeError("test error")
    mock_server = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_server)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    env = {**SMTP_ENV, "NOTIFY_FROM": "noreply@example.com"}
    with patch.dict("os.environ", env, clear=False):
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx):
            mojo_downloader.send_failure_email(error)

    sent_msg = mock_server.send_message.call_args[0][0]
    assert sent_msg["From"] == "noreply@example.com"


def test_smtp_connection_error_does_not_raise():
    """If the SMTP call itself raises, send_failure_email catches it and does not propagate."""
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(side_effect=ConnectionRefusedError("refused"))
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch.dict("os.environ", SMTP_ENV, clear=False):
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx):
            # Should not raise
            mojo_downloader.send_failure_email(RuntimeError("original error"))
