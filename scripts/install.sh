#!/usr/bin/env bash
# =============================================================
# install.sh — Fresh VPS setup for the XAU/USD Trading Bot
#              Tested on Ubuntu 24.04 LTS
#
# Usage:
#   sudo bash scripts/install.sh
#   sudo bash scripts/install.sh --restore /path/to/bundle.tar.gz
#
# What it does:
#   1. Installs system packages (Python 3.12, git, Xvfb, noVNC, etc.)
#   2. Installs WineHQ stable from the official winehq.org repository
#   3. Clones the bot repository from GitHub
#   4. Creates Python venv and installs requirements
#   5. Creates required directories (data, logs, reports, backups)
#   6. Copies .env.example to .env if .env doesn't exist
#   7. Installs and enables xaubot.service systemd unit
#   8. Configures UFW firewall
#   9. Optionally restores from a migration bundle (--restore flag)
#
# Run as: sudo bash scripts/install.sh [--restore /path/to/bundle.tar.gz]
# =============================================================
set -euo pipefail

# ── Constants ────────────────────────────────────────────────────
GITHUB_REPO="${GITHUB_REPO:-https://github.com/m0hd1121/xau_bot.git}"
GIT_BRANCH="claude/xauusd-price-action-bot-T80IJ"
BOT_USER="${SUDO_USER:-botuser}"
BOT_DIR="/home/${BOT_USER}/xau_bot"
VENV_DIR="${BOT_DIR}/.venv"
SYSTEMD_SERVICE="xaubot"

# ── Parse arguments ─────────────────────────────────────────────
RESTORE_BUNDLE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --restore)
            RESTORE_BUNDLE="${2:-}"
            shift 2
            ;;
        *)
            echo "Usage: sudo bash scripts/install.sh [--restore /path/to/bundle.tar.gz]"
            exit 1
            ;;
    esac
done

# ── Colour helpers ───────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

header() { echo -e "\n${BOLD}${CYAN}══ $* ══${RESET}"; }
info()   { echo -e "  ${GREEN}✔${RESET}  $*"; }
warn()   { echo -e "  ${YELLOW}⚠${RESET}  $*" >&2; }
error()  { echo -e "  ${RED}✗${RESET}  $*" >&2; exit 1; }
step()   { echo -e "\n${BOLD}[$*]${RESET}"; }

# ── Root check ───────────────────────────────────────────────────
if [[ "${EUID}" -ne 0 ]]; then
    error "This script must be run as root. Use: sudo bash $0 $*"
fi

# ── Detect Ubuntu 24.04 ──────────────────────────────────────────
if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    source /etc/os-release
    if [[ "${ID}" != "ubuntu" ]]; then
        warn "This script is designed for Ubuntu. Detected: ${ID}. Proceeding anyway…"
    fi
fi

echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║   XAU/USD Price Action Bot — VPS Installer        ║"
echo "  ║   Ubuntu 24.04 LTS                                 ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Track what was done ──────────────────────────────────────────
STEPS_DONE=()
STEPS_WARNED=()

# ─────────────────────────────────────────────────────────────────
# STEP 1: System packages
# ─────────────────────────────────────────────────────────────────
header "STEP 1: System Packages"
step "Updating apt cache"
apt-get update -qq

step "Installing core packages"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    git \
    curl \
    wget \
    ca-certificates \
    gnupg \
    lsb-release \
    build-essential \
    libssl-dev \
    libffi-dev \
    software-properties-common \
    apt-transport-https \
    ufw \
    2>/dev/null

info "Core packages installed"

step "Installing display / VNC packages"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    xvfb \
    x11vnc \
    websockify \
    novnc \
    x11-utils \
    2>/dev/null || warn "Some display packages unavailable — VNC may not work"

info "Display packages installed"

step "Installing certbot for SSL"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    certbot \
    2>/dev/null || warn "certbot not available — install manually for SSL"

STEPS_DONE+=("System packages")

# ─────────────────────────────────────────────────────────────────
# STEP 2: Wine (WineHQ stable)
# ─────────────────────────────────────────────────────────────────
header "STEP 2: Wine (WineHQ Stable)"

if command -v wine &>/dev/null && wine --version 2>/dev/null | grep -q "wine-"; then
    WINE_VER="$(wine --version 2>/dev/null)"
    info "Wine already installed: ${WINE_VER}"
    STEPS_DONE+=("Wine (already present: ${WINE_VER})")
else
    step "Adding WineHQ repository and installing Wine"

    # Enable 32-bit architecture
    dpkg --add-architecture i386 2>/dev/null || true

    # Add WineHQ GPG key
    mkdir -pm755 /etc/apt/keyrings
    curl -fsSL https://dl.winehq.org/wine-builds/winehq.key \
        | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key

    # Add WineHQ repository for Ubuntu
    UBUNTU_CODENAME="$(lsb_release -cs 2>/dev/null || echo 'noble')"
    echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/winehq-archive.key] \
https://dl.winehq.org/wine-builds/ubuntu/ ${UBUNTU_CODENAME} main" \
        > /etc/apt/sources.list.d/winehq.list

    apt-get update -qq

    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        --install-recommends winehq-stable \
        2>/dev/null || {
        warn "WineHQ stable unavailable for ${UBUNTU_CODENAME} — trying wine from universe"
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wine wine64 2>/dev/null || \
            warn "Wine installation failed — MT5 will not function until Wine is installed"
    }

    if command -v wine &>/dev/null; then
        WINE_VER="$(wine --version 2>/dev/null || echo 'unknown')"
        info "Wine installed: ${WINE_VER}"
        STEPS_DONE+=("Wine: ${WINE_VER}")
    else
        warn "Wine not installed — please install manually"
        STEPS_WARNED+=("Wine not installed")
    fi
fi

# ─────────────────────────────────────────────────────────────────
# STEP 3: Clone repository
# ─────────────────────────────────────────────────────────────────
header "STEP 3: Clone Repository"

# Ensure the bot user exists
if ! id "${BOT_USER}" &>/dev/null; then
    step "Creating user: ${BOT_USER}"
    useradd -m -s /bin/bash "${BOT_USER}"
    info "User ${BOT_USER} created"
fi

BOT_HOME="/home/${BOT_USER}"

if [[ -d "${BOT_DIR}/.git" ]]; then
    info "Repository already cloned at ${BOT_DIR}"
    step "Pulling latest changes"
    sudo -u "${BOT_USER}" git -C "${BOT_DIR}" fetch --quiet origin || warn "git fetch failed"
    sudo -u "${BOT_USER}" git -C "${BOT_DIR}" checkout "${GIT_BRANCH}" 2>/dev/null || \
        warn "Could not switch to branch ${GIT_BRANCH}"
    sudo -u "${BOT_USER}" git -C "${BOT_DIR}" pull --quiet origin "${GIT_BRANCH}" 2>/dev/null || \
        warn "git pull failed — using local version"
    STEPS_DONE+=("Repository: updated in place")
else
    step "Cloning ${GITHUB_REPO} (branch: ${GIT_BRANCH})"
    sudo -u "${BOT_USER}" git clone \
        --branch "${GIT_BRANCH}" \
        --single-branch \
        "${GITHUB_REPO}" \
        "${BOT_DIR}" 2>/dev/null || {
        warn "git clone failed. Possible causes:"
        warn "  - Repository URL not set (edit GITHUB_REPO in this script)"
        warn "  - Network/SSH key issue"
        warn "Creating directory structure manually for --restore flow…"
        mkdir -p "${BOT_DIR}"
        chown -R "${BOT_USER}:${BOT_USER}" "${BOT_DIR}"
    }
    STEPS_DONE+=("Repository cloned to ${BOT_DIR}")
fi

# ─────────────────────────────────────────────────────────────────
# STEP 4: Python virtual environment
# ─────────────────────────────────────────────────────────────────
header "STEP 4: Python Virtual Environment"

if [[ -f "${VENV_DIR}/bin/python" ]]; then
    info "Virtual environment already exists at ${VENV_DIR}"
else
    step "Creating venv with python3.12"
    sudo -u "${BOT_USER}" python3.12 -m venv "${VENV_DIR}"
    info "Virtual environment created"
fi

step "Upgrading pip"
sudo -u "${BOT_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip --quiet

REQUIREMENTS="${BOT_DIR}/requirements.txt"
if [[ -f "${REQUIREMENTS}" ]]; then
    step "Installing Python requirements"
    sudo -u "${BOT_USER}" "${VENV_DIR}/bin/pip" install -r "${REQUIREMENTS}" --quiet
    info "Python requirements installed"
    STEPS_DONE+=("Python venv + requirements")
else
    warn "requirements.txt not found at ${REQUIREMENTS} — skipping package install"
    STEPS_WARNED+=("requirements.txt not found")
fi

# Install FastAPI/uvicorn for the backend
step "Installing backend dependencies (fastapi, uvicorn)"
sudo -u "${BOT_USER}" "${VENV_DIR}/bin/pip" install \
    fastapi uvicorn[standard] httpx python-jose[cryptography] passlib[bcrypt] \
    sqlalchemy aiosqlite structlog python-multipart \
    --quiet 2>/dev/null || warn "Some backend packages failed to install"

# Also install backend requirements if they exist
BACKEND_REQUIREMENTS="${BOT_DIR}/backend/requirements.txt"
if [[ -f "${BACKEND_REQUIREMENTS}" ]]; then
    sudo -u "${BOT_USER}" "${VENV_DIR}/bin/pip" install -r "${BACKEND_REQUIREMENTS}" --quiet 2>/dev/null || \
        warn "Backend requirements install had warnings"
fi

# ─────────────────────────────────────────────────────────────────
# STEP 5: Create directories
# ─────────────────────────────────────────────────────────────────
header "STEP 5: Create Data Directories"

for dir in data logs reports backups; do
    TARGET="${BOT_DIR}/${dir}"
    mkdir -p "${TARGET}"
    chown -R "${BOT_USER}:${BOT_USER}" "${TARGET}"
    info "Created: ${TARGET}"
done

STEPS_DONE+=("Data directories")

# ─────────────────────────────────────────────────────────────────
# STEP 6: Environment file
# ─────────────────────────────────────────────────────────────────
header "STEP 6: Environment File"

ENV_FILE="${BOT_DIR}/.env"
ENV_EXAMPLE="${BOT_DIR}/.env.example"

if [[ -f "${ENV_FILE}" ]]; then
    info ".env already exists — keeping existing configuration"
elif [[ -f "${ENV_EXAMPLE}" ]]; then
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    chown "${BOT_USER}:${BOT_USER}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    info "Copied .env.example to .env"
    warn "IMPORTANT: Edit ${ENV_FILE} and fill in your credentials!"
    STEPS_WARNED+=(".env needs configuration")
else
    warn ".env.example not found — .env not created. Run the bot after setting up .env manually."
    STEPS_WARNED+=(".env.example not found")
fi

STEPS_DONE+=("Environment file")

# ─────────────────────────────────────────────────────────────────
# STEP 7: Systemd service
# ─────────────────────────────────────────────────────────────────
header "STEP 7: Systemd Service"

# Look for xaubot.service in standard locations
SERVICE_SRC=""
for loc in \
    "${BOT_DIR}/scripts/xaubot.service" \
    "${BOT_DIR}/xaubot.service" \
    "${BOT_DIR}/backend/systemd/xaubot.service"; do
    [[ -f "${loc}" ]] && { SERVICE_SRC="${loc}"; break; }
done

SERVICE_DST="/etc/systemd/system/${SYSTEMD_SERVICE}.service"

if [[ -n "${SERVICE_SRC}" ]]; then
    step "Installing service from ${SERVICE_SRC}"
    cp "${SERVICE_SRC}" "${SERVICE_DST}"
else
    step "Generating xaubot.service"
    cat > "${SERVICE_DST}" <<SERVICE
[Unit]
Description=XAU/USD Price Action Trading Bot
After=network.target

[Service]
Type=simple
User=${BOT_USER}
WorkingDirectory=${BOT_DIR}
EnvironmentFile=${BOT_DIR}/.env
ExecStartPre=${VENV_DIR}/bin/python -c "import yaml"
ExecStart=${VENV_DIR}/bin/python main.py --mode live
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=xaubot

# Resource limits
LimitNOFILE=65536
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SERVICE
fi

systemctl daemon-reload
systemctl enable "${SYSTEMD_SERVICE}" 2>/dev/null || warn "Failed to enable service — check service file"
info "Service ${SYSTEMD_SERVICE} installed and enabled"
STEPS_DONE+=("Systemd service: ${SYSTEMD_SERVICE}")

# ─────────────────────────────────────────────────────────────────
# STEP 8: UFW Firewall
# ─────────────────────────────────────────────────────────────────
header "STEP 8: UFW Firewall"

if command -v ufw &>/dev/null; then
    step "Configuring UFW rules"
    ufw allow 22/tcp    comment "SSH" 2>/dev/null || true
    ufw allow 8443/tcp  comment "XAUBot API (HTTPS)" 2>/dev/null || true
    ufw allow 8502/tcp  comment "XAUBot UI (Streamlit)" 2>/dev/null || true
    ufw allow 6080/tcp  comment "noVNC (MT5 remote access)" 2>/dev/null || true

    # Enable UFW non-interactively
    ufw --force enable 2>/dev/null || warn "ufw enable failed (may already be enabled)"

    info "UFW rules applied: 22, 8443, 8502, 6080"
    STEPS_DONE+=("UFW firewall rules")
else
    warn "UFW not available — configure firewall manually"
    STEPS_WARNED+=("UFW not configured")
fi

# ─────────────────────────────────────────────────────────────────
# STEP 9 (optional): Restore from bundle
# ─────────────────────────────────────────────────────────────────
if [[ -n "${RESTORE_BUNDLE}" ]]; then
    header "STEP 9: Restore from Bundle"

    if [[ ! -f "${RESTORE_BUNDLE}" ]]; then
        error "Restore bundle not found: ${RESTORE_BUNDLE}"
    fi

    RESTORE_SCRIPT="${BOT_DIR}/scripts/restore.sh"
    if [[ -f "${RESTORE_SCRIPT}" ]]; then
        step "Running restore.sh with bundle: $(basename "${RESTORE_BUNDLE}")"
        sudo -u "${BOT_USER}" bash "${RESTORE_SCRIPT}" "${RESTORE_BUNDLE}" || \
            warn "Restore completed with warnings — review output above"
        info "Restore finished"
        STEPS_DONE+=("Data restored from: $(basename "${RESTORE_BUNDLE}")")
    else
        warn "restore.sh not found at ${RESTORE_SCRIPT} — skipping restore"
        STEPS_WARNED+=("restore.sh not found for bundle restore")
    fi
fi

# ─────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}  Installation Summary                                 ║${RESET}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════╝${RESET}"
echo ""

echo -e "${GREEN}Completed steps:${RESET}"
for s in "${STEPS_DONE[@]}"; do
    echo -e "  ${GREEN}✔${RESET}  ${s}"
done

if [[ ${#STEPS_WARNED[@]} -gt 0 ]]; then
    echo ""
    echo -e "${YELLOW}Warnings / manual actions needed:${RESET}"
    for w in "${STEPS_WARNED[@]}"; do
        echo -e "  ${YELLOW}⚠${RESET}  ${w}"
    done
fi

echo ""
echo -e "${BOLD}Installation details:${RESET}"
echo "  Bot directory   : ${BOT_DIR}"
echo "  Python venv     : ${VENV_DIR}"
echo "  Service name    : ${SYSTEMD_SERVICE}"
echo "  Bot user        : ${BOT_USER}"
echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo "  1. Edit the environment file:"
echo "       nano ${BOT_DIR}/.env"
echo "     Set: VPS_HOST, SSL_DOMAIN, SSL_CERT_DIR, and any broker credentials"
echo ""
echo "  2. Obtain SSL certificate (if not yet done):"
echo "       sudo certbot certonly --standalone -d <your-domain>"
echo ""
echo "  3. Install MT5 under Wine (if not yet done):"
echo "       bash ${BOT_DIR}/scripts/install_mt4_wine.sh"
echo ""
echo "  4. Run validation:"
echo "       bash ${BOT_DIR}/scripts/validate.sh"
echo ""
echo "  5. Start the bot:"
echo "       sudo systemctl start ${SYSTEMD_SERVICE}"
echo "       sudo journalctl -u ${SYSTEMD_SERVICE} -f"
echo ""
echo "  6. Access the dashboard:"
echo "       API : https://<domain>:8443/health"
echo "       UI  : http://<domain>:8502"
echo "       VNC : http://<domain>:6080/vnc.html"
echo ""
echo -e "${GREEN}Installation complete!${RESET}"
echo ""
