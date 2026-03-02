#!/usr/bin/env bash
# setup.sh — Install dependencies and register the nightly cron job.
# Run once on the Linux server: bash setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
PLAYWRIGHT="$VENV_DIR/bin/playwright"

# Cron: every night at 1:00 AM.
# stdout/stderr are redirected to logs/cron.log to catch errors that occur
# before the Python logger initialises (e.g. missing imports).
CRON_SCHEDULE="0 1 * * *"
CRON_CMD="$PYTHON $SCRIPT_DIR/mojo_downloader.py >> $SCRIPT_DIR/logs/cron.log 2>&1"
CRON_JOB="$CRON_SCHEDULE $CRON_CMD"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()    { echo "[INFO]  $*"; }
success() { echo "[OK]    $*"; }
warn()    { echo "[WARN]  $*"; }
die()     { echo "[ERROR] $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Python 3
# ---------------------------------------------------------------------------

info "Checking for Python 3..."
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print('%d.%d' % sys.version_info[:2])")
    success "Found Python $PY_VERSION"
else
    die "Python 3 is not installed. Install it with: sudo apt install python3 python3-venv python3-pip"
fi

# Require Python 3.9+
python3 -c "
import sys
if sys.version_info < (3, 9):
    print('[ERROR] Python 3.9 or newer is required (found %d.%d).' % sys.version_info[:2])
    sys.exit(1)
"

# ---------------------------------------------------------------------------
# 2. Virtual environment
# ---------------------------------------------------------------------------

if [ ! -f "$PIP" ]; then
    if [ -d "$VENV_DIR" ]; then
        warn "Incomplete virtual environment found — recreating..."
        rm -rf "$VENV_DIR"
    else
        info "Creating virtual environment at $VENV_DIR..."
    fi
    python3 -m venv "$VENV_DIR"
    success "Virtual environment created."
else
    success "Virtual environment already exists."
fi

# ---------------------------------------------------------------------------
# 3. Python dependencies
# ---------------------------------------------------------------------------

info "Installing Python dependencies..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r "$SCRIPT_DIR/requirements.txt"
success "Python dependencies installed."

# ---------------------------------------------------------------------------
# 4. Playwright + Chromium system dependencies
# ---------------------------------------------------------------------------

info "Installing Playwright Chromium and its system dependencies..."
info "(This step installs system packages and may prompt for sudo.)"
"$PLAYWRIGHT" install --with-deps chromium
success "Playwright Chromium installed."

# ---------------------------------------------------------------------------
# 5. Logs directory
# ---------------------------------------------------------------------------

mkdir -p "$SCRIPT_DIR/logs"
success "Logs directory ready at $SCRIPT_DIR/logs"

# ---------------------------------------------------------------------------
# 6. Cron job
# ---------------------------------------------------------------------------

info "Checking for existing cron entry..."

# Load current crontab, silently handle the case where none exists yet.
CURRENT_CRONTAB=$(crontab -l 2>/dev/null || true)

if echo "$CURRENT_CRONTAB" | grep -qF "$SCRIPT_DIR/mojo_downloader.py"; then
    warn "Cron job already registered — skipping."
else
    info "Adding cron job: $CRON_JOB"
    (echo "$CURRENT_CRONTAB"; echo "$CRON_JOB") | crontab -
    success "Cron job registered."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
echo "========================================"
echo " Setup complete!"
echo "========================================"
echo " Script  : $SCRIPT_DIR/mojo_downloader.py"
echo " Runs at : 1:00 AM every night"
echo " Logs    : $SCRIPT_DIR/logs/"
echo ""
echo " Next steps:"
echo "   1. Copy credentials.json and token.json into $SCRIPT_DIR"
echo "   2. Copy or create your .env file in $SCRIPT_DIR"
echo "   3. Run manually once to verify: $PYTHON $SCRIPT_DIR/mojo_downloader.py"
echo "========================================"
