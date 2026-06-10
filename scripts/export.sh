#!/usr/bin/env bash
# =============================================================
# export.sh — Create a complete, self-contained migration bundle
#             that can be transferred to a new VPS and restored
#             with scripts/restore.sh.
#
# Usage:
#   bash scripts/export.sh                    # output to ./backups/
#   bash scripts/export.sh /path/to/output    # custom output dir
#
# Output:
#   <output_dir>/xaubot_migration_YYYYMMDD_HHMMSS.tar.gz
#   <output_dir>/xaubot_migration_YYYYMMDD_HHMMSS.sha256
# =============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Load .env if present ────────────────────────────────────────
if [[ -f "${BOT_ROOT}/.env" ]]; then
    # shellcheck source=/dev/null
    set -a; source "${BOT_ROOT}/.env"; set +a
fi

# ── Settings ────────────────────────────────────────────────────
OUTPUT_DIR="${1:-${BACKUP_DIR:-${BOT_ROOT}/backups}}"
[[ "${OUTPUT_DIR}" != /* ]] && OUTPUT_DIR="${BOT_ROOT}/${OUTPUT_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BUNDLE_NAME="xaubot_migration_${TIMESTAMP}"
STAGING_DIR="${OUTPUT_DIR}/.export_staging_${TIMESTAMP}"

info()  { echo "[export] $(date '+%H:%M:%S') INFO  $*"; }
warn()  { echo "[export] $(date '+%H:%M:%S') WARN  $*" >&2; }
error() { echo "[export] $(date '+%H:%M:%S') ERROR $*" >&2; }

# ── Create staging area ─────────────────────────────────────────
mkdir -p "${OUTPUT_DIR}"
mkdir -p "${STAGING_DIR}"

# Cleanup staging on exit/error
trap 'rm -rf "${STAGING_DIR}" 2>/dev/null || true' EXIT

info "======================================================================"
info "XAU/USD Bot Migration Export"
info "======================================================================"
info "Bundle name : ${BUNDLE_NAME}"
info "Output dir  : ${OUTPUT_DIR}"
info "======================================================================"

# ── Step 1: Run backup.sh to get a fresh backup ─────────────────
info "Step 1/4: Creating fresh backup…"
BACKUP_ARCHIVE="$(bash "${SCRIPT_DIR}/backup.sh" "${STAGING_DIR}")"
BACKUP_BASENAME="$(basename "${BACKUP_ARCHIVE}")"
BACKUP_STEM="${BACKUP_BASENAME%.tar.gz}"

if [[ ! -f "${BACKUP_ARCHIVE}" ]]; then
    error "backup.sh did not produce an archive at: ${BACKUP_ARCHIVE}"
    exit 1
fi
info "  Fresh backup: ${BACKUP_BASENAME}"

# ── Step 2: Write RESTORE_INSTRUCTIONS.txt ──────────────────────
info "Step 2/4: Writing RESTORE_INSTRUCTIONS.txt…"

BOT_VERSION="unknown"
if command -v python3 &>/dev/null; then
    BOT_VERSION="$(python3 -c "
import sys
sys.path.insert(0, '${BOT_ROOT}')
try:
    import yaml
    c = yaml.safe_load(open('${BOT_ROOT}/config.yaml'))
    print(c.get('bot', {}).get('version', 'unknown'))
except Exception:
    print('unknown')
" 2>/dev/null)" || BOT_VERSION="unknown"
fi

GIT_BRANCH="$(git -C "${BOT_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'claude/xauusd-price-action-bot-T80IJ')"
GIT_COMMIT="$(git -C "${BOT_ROOT}" rev-parse HEAD 2>/dev/null || echo 'N/A')"

cat > "${STAGING_DIR}/RESTORE_INSTRUCTIONS.txt" <<INSTRUCTIONS
====================================================================
  XAU/USD Trading Bot — Migration Bundle Restore Instructions
====================================================================

Bundle created : $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source host    : $(hostname)
Bot version    : ${BOT_VERSION}
Git branch     : ${GIT_BRANCH}
Git commit     : ${GIT_COMMIT}

====================================================================
PREREQUISITES
====================================================================
  * Ubuntu 24.04 LTS VPS (fresh or existing install)
  * Minimum: 2 GB RAM, 20 GB free disk space
  * sudo access or root on the new VPS
  * Domain / DNS already pointing to new VPS IP (for SSL)
  * Ports 22, 8443, 8502, 6080 open in your cloud firewall panel

====================================================================
STEP 1 — Transfer the bundle to the new VPS
====================================================================
  # Run on your LOCAL machine:
  scp xaubot_migration_*.tar.gz botuser@<NEW_VPS_IP>:/tmp/

  # Verify integrity after transfer:
  ssh botuser@<NEW_VPS_IP> "sha256sum /tmp/xaubot_migration_*.tar.gz"
  # Compare with the .sha256 file shipped alongside this bundle.

====================================================================
STEP 2 — Install fresh environment on the new VPS
====================================================================
  ssh botuser@<NEW_VPS_IP>

  # Option A — full automated install + restore (recommended):
  curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/XAU_Bot/${GIT_BRANCH}/scripts/install.sh \
       -o /tmp/install.sh
  sudo bash /tmp/install.sh --restore /tmp/xaubot_migration_*.tar.gz

  # Option B — if the repo is already cloned at ~/xau_bot:
  sudo bash ~/xau_bot/scripts/install.sh --restore /tmp/xaubot_migration_*.tar.gz

  # install.sh will:
  #   1. Install all system packages (Python 3.12, Wine, Xvfb, noVNC, etc.)
  #   2. Clone the repository (branch: ${GIT_BRANCH})
  #   3. Create the Python venv and install requirements
  #   4. Call restore.sh with the bundle to restore your data
  #   5. Install and enable the xaubot.service systemd unit
  #   6. Configure UFW firewall rules

====================================================================
STEP 3 — Manual restore (if NOT using install.sh --restore)
====================================================================
  # Assumes repo is already cloned to /home/botuser/xau_bot
  bash /home/botuser/xau_bot/scripts/restore.sh /tmp/xaubot_migration_*.tar.gz

====================================================================
STEP 4 — Validate the installation
====================================================================
  bash /home/botuser/xau_bot/scripts/validate.sh

  # Review the PASS/FAIL/WARN report.
  # Address any FAIL items before starting the bot.

====================================================================
STEP 5 — Update configuration for the new VPS
====================================================================
  nano /home/botuser/xau_bot/.env

  # Key values to update:
  #   VPS_HOST=<new VPS IP>
  #   SSL_DOMAIN=<your domain>
  #   SSL_CERT_DIR=/etc/letsencrypt/live/<your domain>

  # Obtain SSL certificate (if not transferring from old VPS):
  sudo certbot certonly --standalone -d <your domain>

====================================================================
STEP 6 — Start the bot
====================================================================
  sudo systemctl daemon-reload
  sudo systemctl enable xaubot
  sudo systemctl start xaubot
  sudo systemctl status xaubot

  # Follow live logs:
  sudo journalctl -u xaubot -f

  # Access the dashboard:
  #   API  : https://<domain>:8443/health
  #   UI   : http://<domain>:8502
  #   VNC  : http://<domain>:6080/vnc.html

====================================================================
ROLLBACK PROCEDURE
====================================================================
  restore.sh automatically creates a pre-restore safety backup before
  overwriting any data. Find it in:
    /home/botuser/xau_bot/backups/pre_restore_*.tar.gz

  To roll back to the state before this restoration:
    bash /home/botuser/xau_bot/scripts/restore.sh \
         /home/botuser/xau_bot/backups/pre_restore_<timestamp>.tar.gz

====================================================================
SUPPORT / DEBUG
====================================================================
  Bot logs    : /home/botuser/xau_bot/logs/xau_bot.log
  API logs    : /home/botuser/xau_bot/logs/api.log
  MT5 logs    : /home/botuser/xau_bot/logs/mt5.log
  Service     : sudo journalctl -u xaubot -n 100
  Validate    : bash /home/botuser/xau_bot/scripts/validate.sh

====================================================================
INSTRUCTIONS

# ── Step 3: Write migration_meta.json ──────────────────────────
info "Step 3/4: Writing migration_meta.json…"

# Gather system info
SOURCE_IP="$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || echo 'unknown')"
PYTHON_VER="$(python3 --version 2>/dev/null | awk '{print $2}' || echo 'unknown')"
OS_INFO="$(uname -sr)"

cat > "${STAGING_DIR}/migration_meta.json" <<JSON
{
  "format_version": "1.1",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": {
    "hostname": "$(hostname)",
    "ip": "${SOURCE_IP}",
    "os": "${OS_INFO}",
    "user": "$(whoami)",
    "bot_dir": "${BOT_ROOT}"
  },
  "software": {
    "bot_version": "${BOT_VERSION}",
    "git_branch": "${GIT_BRANCH}",
    "git_commit": "${GIT_COMMIT}",
    "python_version": "${PYTHON_VER}"
  },
  "feature_flags": {
    "broker_type": "${BROKER_TYPE:-dwx}",
    "bot_mode": "${BOT_MODE:-live}",
    "bot_symbol": "${BOT_SYMBOL:-XAUUSD!}",
    "api_port": ${API_PORT:-8443},
    "ui_port": ${UI_PORT:-8502},
    "vnc_port": ${VNC_PORT:-5900},
    "vnc_web_port": ${VNC_WEB_PORT:-6080},
    "ssl_domain": "${SSL_DOMAIN:-}",
    "dwx_magic": ${DWX_MAGIC:-88888}
  },
  "backup_file": "${BACKUP_BASENAME}",
  "restore_command": "bash scripts/restore.sh <path_to_this_bundle>"
}
JSON
info "  migration_meta.json written"

# ── Step 4: Bundle everything together ──────────────────────────
info "Step 4/4: Creating final migration bundle…"

BUNDLE_FILE="${OUTPUT_DIR}/${BUNDLE_NAME}.tar.gz"

# List all files in staging that should be bundled
BUNDLE_FILES=()
BUNDLE_FILES+=("${BACKUP_BASENAME}")
[[ -f "${STAGING_DIR}/${BACKUP_STEM}.manifest.json" ]] && BUNDLE_FILES+=("${BACKUP_STEM}.manifest.json")
[[ -f "${STAGING_DIR}/${BACKUP_STEM}.sha256" ]]        && BUNDLE_FILES+=("${BACKUP_STEM}.sha256")
BUNDLE_FILES+=("RESTORE_INSTRUCTIONS.txt")
BUNDLE_FILES+=("migration_meta.json")

set +e
tar -czf "${BUNDLE_FILE}" \
    -C "${STAGING_DIR}" \
    "${BUNDLE_FILES[@]}" \
    2>/dev/null
TAR_EXIT=$?
set -e
[[ ${TAR_EXIT} -gt 1 ]] && { error "tar failed with exit code ${TAR_EXIT}"; exit 1; }
[[ ${TAR_EXIT} -eq 1 ]] && warn "tar exited with code 1 (minor file-change warning; bundle is usable)"

# ── Compute final SHA256 ─────────────────────────────────────────
BUNDLE_SHA256="$(sha256sum "${BUNDLE_FILE}" | awk '{print $1}')"
echo "${BUNDLE_SHA256}  ${BUNDLE_NAME}.tar.gz" > "${OUTPUT_DIR}/${BUNDLE_NAME}.sha256"

BUNDLE_SIZE="$(du -sh "${BUNDLE_FILE}" | cut -f1)"

# staging cleanup handled by trap
info "======================================================================"
info "Export complete!"
info "  Bundle  : ${BUNDLE_FILE}"
info "  Size    : ${BUNDLE_SIZE}"
info "  SHA256  : ${BUNDLE_SHA256}"
info "======================================================================"
info "Transfer to new VPS:"
info "  scp '${BUNDLE_FILE}' botuser@<NEW_VPS_IP>:/tmp/"
info ""
info "Then on the new VPS:"
info "  sudo bash scripts/install.sh --restore /tmp/${BUNDLE_NAME}.tar.gz"
info "======================================================================"

# Print sha256 + path on stdout for capture / verification
echo "${BUNDLE_SHA256}  ${BUNDLE_FILE}"
