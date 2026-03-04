"""Retry logic and failure email notification."""

import logging
import os
import smtplib
import time
from datetime import date
from email.mime.text import MIMEText

log = logging.getLogger("mojo_downloader")


def retry(fn, max_attempts: int = 3, delay_seconds: int = 1800):
    """Call fn() up to max_attempts times, waiting delay_seconds between tries."""
    last_exc: Exception = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                log.warning(
                    "Attempt %d/%d failed: %s — retrying in %d minutes.",
                    attempt, max_attempts, exc, delay_seconds // 60,
                )
                time.sleep(delay_seconds)
            else:
                log.error("All %d attempts failed.", max_attempts)
    raise last_exc


def send_failure_email(error: Exception) -> None:
    """Send a failure notification email if SMTP env vars are configured."""
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAIL"]
    cfg = {k: os.getenv(k) for k in required}
    if not all(cfg.values()):
        log.warning("SMTP not configured — skipping failure email.")
        return

    subject = f"[mojo-downloader] Export failed on {date.today().isoformat()}"
    body = (
        f"The mojo-downloader cron job failed after all retry attempts.\n\n"
        f"Error: {type(error).__name__}: {error}\n\n"
        f"Check logs/mojo_downloader.log for the full traceback."
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.getenv("NOTIFY_FROM") or cfg["SMTP_USER"]
    msg["To"] = cfg["NOTIFY_EMAIL"]

    try:
        port = int(cfg["SMTP_PORT"])
        if port == 587:
            with smtplib.SMTP(cfg["SMTP_HOST"], port) as server:
                server.starttls()
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(cfg["SMTP_HOST"], port) as server:
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                server.send_message(msg)
        log.info("Failure notification sent to %s.", cfg["NOTIFY_EMAIL"])
    except Exception as smtp_exc:
        log.error("Failed to send notification email: %s", smtp_exc)
