"""Google Drive helpers: authentication, existence check, and upload."""

import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from _mojo import PROJECT_ROOT

load_dotenv()

log = logging.getLogger("mojo_downloader")

GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# OAuth credential files — keep both out of version control (.gitignore).
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"  # downloaded from Google Cloud Console
TOKEN_FILE       = PROJECT_ROOT / "token.json"         # auto-created after first auth

SCOPES = ["https://www.googleapis.com/auth/drive"]

def sheet_name_for(table: str) -> str:
    """Return today's Drive sheet name for the given table label."""
    return f"mojo_export_{table.lower()}_{date.today().isoformat()}"


# Legacy aliases kept for backward compatibility.
SHEET_NAME_FSBO    = sheet_name_for("FSBO")
SHEET_NAME_EXPIRED = sheet_name_for("Expired")


def get_drive_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Refreshing Google OAuth token...")
            creds.refresh(Request())
        else:
            log.info("Opening browser for one-time Google authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            # Opens a browser tab for one-time authorization. token.json is saved
            # afterward and reused on every subsequent run.
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
        log.info("Google credentials saved to %s", TOKEN_FILE)

    return build("drive", "v3", credentials=creds)


def check_sheet_exists(drive_service, sheet_name: str, folder_id: str) -> bool:
    query = (
        f"name = '{sheet_name}'"
        f" and '{folder_id}' in parents"
        f" and mimeType = 'application/vnd.google-apps.spreadsheet'"
        f" and trashed = false"
    )
    results = drive_service.files().list(
        q=query,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    return len(results.get("files", [])) > 0


def upload_to_drive(drive_service, xlsx_path: Path, sheet_name: str, folder_id: str) -> dict:
    log.info("Uploading '%s' as Google Sheet '%s'...", xlsx_path.name, sheet_name)
    file_metadata = {
        "name": sheet_name,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [folder_id],
    }
    media = MediaFileUpload(
        str(xlsx_path),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=True,
    )
    result = (
        drive_service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return result
