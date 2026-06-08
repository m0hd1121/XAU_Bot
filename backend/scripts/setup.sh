#!/usr/bin/env bash
# ============================================================
# XAU Bot Control API — Complete VPS Setup Script
#
# Usage:
#   sudo bash setup.sh [OPTIONS]
#
# Options:
#   --user   USERNAME   System user to run services as  (default: ubuntu)
#   --port   PORT       API listening port              (default: 8443)
#   --domain DOMAIN     Domain or IP for SSL CN         (default: $(hostname))
#
# What this script does:
#   1. Installs system dependencies (Python 3.10+, openssl, ufw)
#   2. Creates a Python virtual environment for the backend
#   3. Installs Python dependencies from requirements.txt
#   4. Generates a self-signed TLS certificate (replace with Let's Encrypt)
#   5. Creates .env with random secrets
#   6. Creates required directories and sets ownership
#   7. Installs and starts systemd services (xaubot-api, xaubot-worker)
#   8. Configures ufw firewall
#   9. Bootstraps the admin user in the API database
#   10. Configures sudo NOPASSWD for systemctl restart for managed services
#
# After running:
#   • Change the admin password:  POST /api/v1/auth/change-password
#   • Replace self-signed cert with Let's Encrypt for production
#   • Configure APNs credentials in .env for push notifications
# ============================================================

set -euo pipefail

# ── Auto-detect project root from script location ─────────────────────────────
# Works regardless of what the cloned folder is named (XAU_Bot, xau_bot, etc.)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "${SCRIPT_DIR}")"   # backend/scripts/../  = backend/
BOT_DIR="$(dirname "${BACKEND_DIR}")"      # backend/../           = project root

# ── Defaults ──────────────────────────────────────────────────────────────────
# Default user = whoever owns the project directory
INSTALL_USER="$(stat -c '%U' "${BOT_DIR}" 2>/dev/null || echo 'ubuntu')"
API_PORT="8443"
DOMAIN="$(hostname 2>/dev/null || echo 'xaubot')"

# Parse flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)   INSTALL_USER="$2"; shift 2 ;;
        --port)   API_PORT="$2";     shift 2 ;;
        --domain) DOMAIN="$2";       shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done
VENV="${BACKEND_DIR}/.venv"
SSL_DIR="/etc/ssl/xaubot"
LOG_DIR="${BACKEND_DIR}/logs"
DATA_DIR="${BACKEND_DIR}/data"
BACKUP_DIR="${BACKEND_DIR}/backups"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     XAU Bot Control API — VPS Setup              ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  User:     ${INSTALL_USER}"
echo "  Bot dir:  ${BOT_DIR}"
echo "  API port: ${API_PORT}"
echo "  Domain:   ${DOMAIN}"
echo ""

# ── Require root ──────────────────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: Run this script as root (sudo bash setup.sh)"
    exit 1
fi

# ── System dependencies ───────────────────────────────────────────────────────
echo "[1/10] Installing system packages..."
apt-get update -qq

# Install base packages (always available)
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-pip \
    openssl libssl-dev libffi-dev \
    git curl wget \
    ufw \
    build-essential \
    systemd 2>/dev/null || true

# Try to install Python 3.11 specifically; fall back gracefully
if apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-dev 2>/dev/null; then
    PYTHON_BIN="python3.11"
    echo "  Python 3.11 installed from default repos."
else
    echo "  Python 3.11 not in default repos — trying deadsnakes PPA..."
    apt-get install -y --no-install-recommends software-properties-common 2>/dev/null || true
    if add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null && \
       apt-get update -qq && \
       apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-dev 2>/dev/null; then
        PYTHON_BIN="python3.11"
        echo "  Python 3.11 installed from deadsnakes PPA."
    else
        # Fall back to whatever python3 is available (3.10, 3.12, etc.)
        PYTHON_BIN="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)"
        echo "  Using available Python: ${PYTHON_BIN}"
    fi
fi

# Verify minimum version (3.10+)
PY_VER=$("${PYTHON_BIN}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("${PYTHON_BIN}" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("${PYTHON_BIN}" -c "import sys; print(sys.version_info.minor)")

if [[ "${PY_MAJOR}" -lt 3 ]] || [[ "${PY_MAJOR}" -eq 3 && "${PY_MINOR}" -lt 10 ]]; then
    echo "ERROR: Python 3.10 or newer is required. Found Python ${PY_VER}."
    echo "       Run: sudo apt install python3.11  (or upgrade your Ubuntu version)"
    exit 1
fi

echo "  Using Python ${PY_VER} (${PYTHON_BIN})"
echo "  System packages installed."

# ── Python virtual environment ────────────────────────────────────────────────
echo "[2/10] Creating Python virtual environment..."
"${PYTHON_BIN}" -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade pip wheel setuptools -q
echo "  Venv created at ${VENV}"

# ── Install Python dependencies ───────────────────────────────────────────────
echo "[3/10] Installing Python dependencies..."
"${VENV}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" -q
echo "  Dependencies installed."

# ── TLS certificate ───────────────────────────────────────────────────────────
echo "[4/10] Setting up TLS certificate..."
mkdir -p "${SSL_DIR}"
chmod 750 "${SSL_DIR}"

if [[ ! -f "${SSL_DIR}/private.key" ]]; then
    openssl req -x509 -newkey rsa:4096 \
        -keyout "${SSL_DIR}/private.key" \
        -out    "${SSL_DIR}/cert.pem"    \
        -days   3650                     \
        -nodes                           \
        -subj   "/CN=${DOMAIN}/O=XAUBot Trading/C=US" \
        2>/dev/null
    chmod 600 "${SSL_DIR}/private.key"
    chmod 644 "${SSL_DIR}/cert.pem"
    echo "  Self-signed certificate created (valid 10 years)."
    echo "  NOTE: Replace with Let's Encrypt cert for production use."
else
    echo "  TLS certificate already exists — skipping."
fi
# Give the service user read access to the cert files
chown -R "${INSTALL_USER}:${INSTALL_USER}" "${SSL_DIR}"

# ── Environment configuration ─────────────────────────────────────────────────
echo "[5/10] Creating .env configuration..."
if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
    SECRET_KEY=$(openssl rand -hex 32)
    PASSWORD_PEPPER=$(openssl rand -hex 32)
    INITIAL_ADMIN_PW="XAUBot@$(openssl rand -hex 6 | tr '[:lower:]' '[:upper:]')!"

    cat > "${BACKEND_DIR}/.env" << EOF
# ── XAU Bot Control API environment config ──────────────────
# Generated by setup.sh — review and customize before production

# Server
API_HOST=0.0.0.0
API_PORT=${API_PORT}
DEBUG=false
ENVIRONMENT=production
LOG_LEVEL=INFO

# Secrets — NEVER share these
SECRET_KEY=${SECRET_KEY}
PASSWORD_PEPPER=${PASSWORD_PEPPER}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
BIOMETRIC_TOKEN_EXPIRE_DAYS=90

# CORS — restrict to your iOS app origin in production
CORS_ORIGINS=*

# Database (API's own SQLite — separate from bot's learning.db)
DATABASE_URL=sqlite+aiosqlite:///${DATA_DIR}/api.db

# XAU Bot paths
BOT_ROOT=${BOT_DIR}
BOT_CONFIG_PATH=${BOT_DIR}/config.yaml
BOT_LEARNING_DB=${BOT_DIR}/data/learning.db
BOT_LOG_FILE=${BOT_DIR}/logs/xau_bot.log
BOT_TRADES_CSV=${BOT_DIR}/logs/trades.csv
BOT_PID_FILE=${BOT_DIR}/bot.pid
BOT_MAIN_SCRIPT=${BOT_DIR}/main.py
BOT_VENV_PYTHON=${BOT_DIR}/venv/bin/python

# Systemd service names
BOT_SERVICE_NAME=xaubot
API_SERVICE_NAME=xaubot-api
WORKER_SERVICE_NAME=xaubot-worker

# Backup
BACKUP_DIR=${BACKUP_DIR}
MAX_BACKUPS_TO_KEEP=20

# Rate limiting
RATE_LIMIT_GENERAL=60
RATE_LIMIT_AUTH=5
RATE_LIMIT_WINDOW_SECONDS=60

# Brute-force lockout
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_SECONDS=900

# APNs (Apple Push Notifications) — configure after obtaining credentials
APNS_BUNDLE_ID=com.xaubot.app
APNS_USE_SANDBOX=true
# APNS_KEY_ID=XXXXXXXXXX
# APNS_TEAM_ID=XXXXXXXXXX
# APNS_KEY_PATH=/home/${INSTALL_USER}/XAU_Bot/backend/apns_key.p8

# Redis (optional — improves rate limit accuracy across multiple workers)
# REDIS_URL=redis://localhost:6379/0

# Admin bootstrap
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=${INITIAL_ADMIN_PW}

# Logging
API_LOG_FILE=${LOG_DIR}/api.log

# WebSocket
WS_DASHBOARD_INTERVAL_SECONDS=1.0
WS_TRADES_INTERVAL_SECONDS=5.0
WS_MAX_CONNECTIONS=10
EOF
    chown "${INSTALL_USER}:${INSTALL_USER}" "${BACKEND_DIR}/.env"
    chmod 600 "${BACKEND_DIR}/.env"
    echo "  .env created. Initial admin password: ${INITIAL_ADMIN_PW}"
    echo "  IMPORTANT: Change this password on first login!"
else
    echo "  .env already exists — skipping."
fi

# ── Directories ───────────────────────────────────────────────────────────────
echo "[6/10] Creating directories..."
mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${BACKUP_DIR}"
mkdir -p "${BOT_DIR}/data"     # bot's data directory
mkdir -p "${BOT_DIR}/logs"     # bot's log directory
chown -R "${INSTALL_USER}:${INSTALL_USER}" "${BACKEND_DIR}"
chown -R "${INSTALL_USER}:${INSTALL_USER}" "${BOT_DIR}/data"
chown -R "${INSTALL_USER}:${INSTALL_USER}" "${BOT_DIR}/logs"
echo "  Directories created and ownership set."

# ── sudo NOPASSWD for systemctl restart ──────────────────────────────────────
echo "[7/10] Configuring sudoers for service management..."
SUDOERS_FILE="/etc/sudoers.d/xaubot-api"
cat > "${SUDOERS_FILE}" << EOF
# Allow xaubot-api to restart managed services without a password
${INSTALL_USER} ALL=(root) NOPASSWD: /bin/systemctl restart xaubot-api
${INSTALL_USER} ALL=(root) NOPASSWD: /bin/systemctl restart xaubot-worker
${INSTALL_USER} ALL=(root) NOPASSWD: /bin/systemctl restart xaubot
${INSTALL_USER} ALL=(root) NOPASSWD: /bin/systemctl stop xaubot
${INSTALL_USER} ALL=(root) NOPASSWD: /bin/systemctl start xaubot
EOF
chmod 440 "${SUDOERS_FILE}"
echo "  Sudoers configured at ${SUDOERS_FILE}"

# ── systemd services ──────────────────────────────────────────────────────────
echo "[8/10] Installing systemd services..."
SYSTEMD_DIR="${BACKEND_DIR}/systemd"

# Shared sed substitutions — replace every hardcoded path/user in the template
# with the actual detected values regardless of folder name or username.
patch_service() {
    sed \
        -e "s|/home/ubuntu/XAU_Bot|${BOT_DIR}|g" \
        -e "s|/home/ubuntu|/home/${INSTALL_USER}|g" \
        -e "s|User=ubuntu|User=${INSTALL_USER}|g" \
        -e "s|Group=ubuntu|Group=${INSTALL_USER}|g" \
        -e "s|8443|${API_PORT}|g" \
        "$1"
}

# API service
patch_service "${SYSTEMD_DIR}/xaubot-api.service" \
    > /etc/systemd/system/xaubot-api.service

# Worker service (if exists)
if [[ -f "${SYSTEMD_DIR}/xaubot-worker.service" ]]; then
    patch_service "${SYSTEMD_DIR}/xaubot-worker.service" \
        > /etc/systemd/system/xaubot-worker.service
fi

systemctl daemon-reload
systemctl enable xaubot-api

echo "  Starting xaubot-api service..."
if systemctl start xaubot-api; then
    echo "  xaubot-api service started successfully."
else
    echo ""
    echo "  WARNING: xaubot-api failed to start. Showing last 20 log lines:"
    journalctl -u xaubot-api -n 20 --no-pager || true
    echo ""
    echo "  The service is ENABLED — it will try again on reboot."
    echo "  Fix the issue above, then run: sudo systemctl start xaubot-api"
    echo "  (Setup will continue so remaining steps still complete)"
    echo ""
fi

# ── Firewall ──────────────────────────────────────────────────────────────────
echo "[9/10] Configuring firewall (ufw)..."
ufw --force reset     > /dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow "${API_PORT}/tcp"  comment "XAU Bot API"
ufw --force enable
echo "  Firewall configured: SSH + port ${API_PORT} open."

# ── Bootstrap admin user ──────────────────────────────────────────────────────
echo "[10/10] Bootstrapping admin user..."
sleep 2  # Give API a moment to start and create DB

cd "${BACKEND_DIR}"
# Run as the service user so api.db is owned by that user from the start
sudo -u "${INSTALL_USER}" "${VENV}/bin/python" - << 'PYEOF'
import asyncio, sys, os
sys.path.insert(0, os.getcwd())
os.chdir(os.getcwd())

async def main():
    from app.database import init_db
    await init_db()
    print("Database initialised — admin user bootstrapped.")

asyncio.run(main())
PYEOF

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                  Setup Complete!                             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  API URL:      https://${DOMAIN}:${API_PORT}"
echo "  Health check: curl -k https://localhost:${API_PORT}/health"
echo ""
echo "  Admin credentials are in: ${BACKEND_DIR}/.env"
echo "  (INITIAL_ADMIN_USERNAME / INITIAL_ADMIN_PASSWORD)"
echo ""
echo "  Next steps:"
echo "  1. Change the admin password via POST /api/v1/auth/change-password"
echo "  2. Replace self-signed cert in ${SSL_DIR} with a valid certificate"
echo "  3. Add APNs credentials to .env for iOS push notifications"
echo "  4. Set CORS_ORIGINS to your iOS app origin in .env"
echo "  5. Optionally configure Redis for distributed rate limiting"
echo ""
echo "  Logs:          journalctl -u xaubot-api -f"
echo "  Service status: systemctl status xaubot-api"
echo ""
