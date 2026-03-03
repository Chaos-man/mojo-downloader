# mojo-downloader

Automates the nightly export of **FSBO** and **Expired** leads from [Mojo Sells](https://lb11.mojosells.com) and uploads them to Google Drive as Google Sheets.

## What It Does

1. Logs in to Mojo Sells using your credentials
2. Navigates to **Data & Dialer → FSBO**, selects all records, and exports
3. Closes the export dialog, switches to **Expired**, and repeats
4. Uploads both `.xlsx` files to a specified Google Drive folder as Google Sheets named:
   - `mojo_export_fsbo_YYYY-MM-DD`
   - `mojo_export_expired_YYYY-MM-DD`
5. Fails immediately if either sheet already exists in Drive for today
6. Retries the export up to **3 times** (30-minute gaps) if a transient error occurs
7. Sends a **failure email** after all retries are exhausted (optional — requires SMTP config)

---

## Project Structure

```
mojo-downloader/
├── mojo_downloader.py      # Main script
├── setup.sh                # One-time Linux server setup + cron registration
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Dev/test dependencies (includes requirements.txt)
├── .env                    # Credentials — never commit (see .env.example)
├── .env.example            # Template for .env
├── credentials.json        # Google OAuth client — never commit
├── token.json              # Google OAuth token — never commit (auto-created)
├── downloads/              # Temporary .xlsx files — gitignored
├── logs/                   # Rotating log files — gitignored
└── tests/
    ├── conftest.py
    ├── test_validation.py
    ├── test_drive.py
    ├── test_logging.py
    ├── test_browser.py
    ├── test_retry.py
    ├── test_notification.py
    └── test_cli.py
```

---

## Requirements

- Python 3.9+
- A Google account with access to Google Drive
- A [Google Cloud project](https://console.cloud.google.com) with the **Google Drive API** enabled

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <your-repo-url>
cd mojo-downloader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env`:

```env
MOJO_USERNAME=your_mojo_email@example.com
MOJO_PASSWORD=your_mojo_password
GOOGLE_DRIVE_FOLDER_ID=your_drive_folder_id_here
```

The folder ID is the last segment of the folder's URL in Google Drive:
`https://drive.google.com/drive/folders/<FOLDER_ID>`

### 3. Set up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Download the JSON file and save it as `credentials.json` in the project folder
5. Ensure the **Google Drive API** is enabled for your project

### 4. (Optional) Configure failure email notifications

If the export fails after all retries, the script can send you an email. Add these to your `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password
NOTIFY_EMAIL=you@gmail.com
```

Leave any of these blank (or omit them entirely) to disable notifications — the script runs fine without them.

#### Getting a Gmail App Password

Regular Gmail passwords won't work if you have 2-Step Verification enabled (which you should). Use an App Password instead:

1. Go to your [Google Account](https://myaccount.google.com) → **Security**
2. Under **"How you sign in to Google"**, click **2-Step Verification** (must be enabled first)
3. Scroll to the bottom and click **App passwords**
4. Select app: **Mail**, device: **Other** (type a name like `mojo-downloader`)
5. Click **Generate** — copy the 16-character password shown
6. Paste it as `SMTP_PASSWORD` in your `.env` (no spaces)

> The App Password is only shown once. Store it in `.env` immediately.

### 5. Authorize (first run only)

```bash
python mojo_downloader.py
```

A browser tab will open asking you to sign in to Google and grant Drive access. After approving, `token.json` is saved and all future runs are fully headless.

---

## Running

```bash
python mojo_downloader.py
```

Output is written to both the terminal and `logs/mojo_downloader.log`.

## CLI Flags

| Flag | Description |
|---|---|
| `--test-notification` | Send a test failure email and exit. Use this to verify your SMTP config works before relying on it. |
| `--check-drive` | Check whether today's FSBO and Expired sheets already exist in Drive, then exit. |
| `--show-browser` | Launch Chromium with a visible window instead of headless. Useful for debugging login or navigation issues. |
| `--dry-run` | Run the browser automation and download exports, but skip the Drive upload. |
| `--force` | Skip the duplicate-sheet check. Useful when you need to re-run after a partial failure without deleting the existing sheets first. |

```bash
# Verify email notification works:
python mojo_downloader.py --test-notification

# Check if today's sheets are already on Drive:
python mojo_downloader.py --check-drive

# Debug browser steps with a visible window:
python mojo_downloader.py --show-browser

# Test the full download without uploading anything:
python mojo_downloader.py --dry-run

# Re-run after a partial failure (sheets already exist):
python mojo_downloader.py --force
```

---

## Linux Server Deployment

Run the setup script once on your server. It creates the virtual environment, installs all dependencies (including Playwright's Chromium system libraries), and registers a **nightly 5:00 AM cron job** automatically.

```bash
bash setup.sh
```

Then copy your credential files to the server:

```bash
scp credentials.json token.json .env user@your-server:/path/to/mojo-downloader/
```

Run once manually to verify everything works before relying on the cron schedule.

### n8n Integration

If you prefer n8n for scheduling instead of cron, use an **Execute Command** node:

```
/path/to/mojo-downloader/.venv/bin/python /path/to/mojo-downloader/mojo_downloader.py
```

Set environment variables in n8n's own env config rather than relying on `.env`.

---

## Logs

| File | Description |
|---|---|
| `logs/mojo_downloader.log` | Active log file |
| `logs/mojo_downloader.log.YYYY-MM-DD` | Rotated weekly archives |
| `logs/cron.log` | Captures output from the cron process itself |

Log files rotate every **7 days** and are kept for **~2 months** (8 rotated files). Older files are deleted automatically.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

| Test file | Coverage |
|---|---|
| `test_validation.py` | `validate_env()` — missing vars, missing credentials file |
| `test_drive.py` | `check_sheet_exists()`, `upload_to_drive()`, sheet name format |
| `test_logging.py` | `setup_logging()` — directory creation, handler config, rotation settings |
| `test_browser.py` | `_select_all_and_export()` — direct click, dropdown fallback, file saving |
| `test_retry.py` | `retry()` — success on first attempt, retry on failure, exhaustion behavior |
| `test_notification.py` | `send_failure_email()` — SMTP call, missing config skip, connection error handling, `--test-notification` flag |
| `test_cli.py` | CLI flags — `--check-drive`, `--force`, `--dry-run`, `--show-browser`, default behaviour |

---

## Security Notes

- `.env`, `credentials.json`, and `token.json` are all listed in `.gitignore` and must never be committed
- The Google OAuth token (`token.json`) is machine-independent — generate it once on your local machine and copy it to the server
- To revoke access, delete `token.json` and remove the app from your [Google Account permissions](https://myaccount.google.com/permissions)
