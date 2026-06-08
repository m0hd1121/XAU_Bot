#!/usr/bin/env bash
# ============================================================
# XAU Bot Control API — Deployment Script
#
# Usage:
#   bash deploy.sh [--branch main] [--skip-git] [--port 8443]
#
# What this does:
#   1. Pull latest code from git (unless --skip-git)
#   2. Update Python dependencies
#   3. Run a pre-flight import check
#   4. Restart the API service via systemd
#   5. Wait and verify health check passes
#   6. Print service status
# ============================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BRANCH="main"
SKIP_GIT=0
API_PORT="8443"
SERVICE_NAME="xaubot-api"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch)   BRANCH="$2";    shift 2 ;;
        --port)     API_PORT="$2";  shift 2 ;;
        --skip-git) SKIP_GIT=1;     shift   ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Resolve paths relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(cd "${BACKEND_DIR}/.." && pwd)"
VENV="${BACKEND_DIR}/.venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     XAU Bot API — Deployment             ║"
echo "╚══════════════════════════════════════════╝"
echo "  Backend dir: ${BACKEND_DIR}"
echo "  Venv:        ${VENV}"
echo "  Branch:      ${BRANCH}"
echo "  Port:        ${API_PORT}"
echo ""

# ── Check venv exists ─────────────────────────────────────────────────────────
if [[ ! -f "${VENV}/bin/python" ]]; then
    echo "ERROR: Virtual environment not found at ${VENV}"
    echo "Run setup.sh first."
    exit 1
fi

# ── Git pull ───────────────────────────────────────────────────────────────────
if [[ "${SKIP_GIT}" -eq 0 ]]; then
    echo "[1/5] Pulling latest code (branch: ${BRANCH})..."
    if git -C "${REPO_DIR}" rev-parse --git-dir > /dev/null 2>&1; then
        git -C "${REPO_DIR}" fetch origin
        git -C "${REPO_DIR}" checkout "${BRANCH}"
        git -C "${REPO_DIR}" pull --ff-only origin "${BRANCH}"
        echo "  Code updated. Latest commit:"
        git -C "${REPO_DIR}" log --oneline -1
    else
        echo "  Not a git repo — skipping pull."
    fi
else
    echo "[1/5] Skipping git pull (--skip-git)"
fi

# ── Update dependencies ───────────────────────────────────────────────────────
echo "[2/5] Updating Python dependencies..."
"${VENV}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" -q --upgrade
echo "  Dependencies up to date."

# ── Pre-flight import check ───────────────────────────────────────────────────
echo "[3/5] Running pre-flight import check..."
cd "${BACKEND_DIR}"
if ! "${VENV}/bin/python" -c "from app.main import app; print('  Import OK')" 2>&1; then
    echo "ERROR: Import check failed — aborting deployment."
    echo "Fix the error above and re-run deploy.sh"
    exit 1
fi

# ── Restart service ───────────────────────────────────────────────────────────
echo "[4/5] Restarting ${SERVICE_NAME}..."
if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    sudo systemctl restart "${SERVICE_NAME}"
    echo "  Service restarted."
else
    echo "  Service not active — starting it..."
    sudo systemctl start "${SERVICE_NAME}" || true
fi

# ── Health check ──────────────────────────────────────────────────────────────
echo "[5/5] Verifying health..."
MAX_RETRIES=10
RETRY_DELAY=2
HEALTHY=0

for i in $(seq 1 "${MAX_RETRIES}"); do
    sleep "${RETRY_DELAY}"
    STATUS=$(curl -sk "https://localhost:${API_PORT}/health" \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" \
        2>/dev/null || echo "error")
    if [[ "${STATUS}" == "ok" ]]; then
        HEALTHY=1
        echo "  Health check passed (attempt ${i}/${MAX_RETRIES})"
        break
    fi
    echo "  Attempt ${i}/${MAX_RETRIES}: status=${STATUS}"
done

if [[ "${HEALTHY}" -eq 0 ]]; then
    echo ""
    echo "ERROR: Health check failed after ${MAX_RETRIES} attempts"
    echo "Check logs:"
    echo "  journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    echo "  tail -50 ${BACKEND_DIR}/logs/api.log"
    exit 1
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║       Deployment Successful!             ║"
echo "╚══════════════════════════════════════════╝"
echo ""
systemctl status "${SERVICE_NAME}" --no-pager --lines=5 || true
echo ""
echo "  API: https://localhost:${API_PORT}"
echo "  Logs: journalctl -u ${SERVICE_NAME} -f"
echo ""
