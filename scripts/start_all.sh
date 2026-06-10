#!/bin/bash
# start_all.sh — Start all XAU Bot services (survives SSH session close)
# Uses environment variables from .env with sensible defaults.

# ── Locate project root (one level up from this script) ────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Source .env if present ───────────────────────────────────────
if [[ -f "${BOT_ROOT}/.env" ]]; then
    # shellcheck source=/dev/null
    set -a; source "${BOT_ROOT}/.env"; set +a
    echo "[start_all] Loaded .env"
fi

# ── Resolve paths / ports with defaults ─────────────────────────
BOT_DIR="${BOT_DIR:-${BOT_ROOT}}"
[[ "${BOT_DIR}" != /* ]] && BOT_DIR="${BOT_ROOT}/${BOT_DIR}"

LOGS_DIR="${LOGS_DIR:-${BOT_DIR}/logs}"
[[ "${LOGS_DIR}" != /* ]] && LOGS_DIR="${BOT_DIR}/${LOGS_DIR}"

WINE_PREFIX="${WINE_PREFIX:-${HOME}/.wine-mt4}"
MT5_EXE="${MT5_EXE:-${WINE_PREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe}"

API_PORT="${API_PORT:-8443}"
UI_PORT="${UI_PORT:-8502}"
VNC_PORT="${VNC_PORT:-5900}"
VNC_WEB_PORT="${VNC_WEB_PORT:-6080}"

SSL_DOMAIN="${SSL_DOMAIN:-localhost}"
SSL_CERT_DIR="${SSL_CERT_DIR:-/etc/letsencrypt/live/${SSL_DOMAIN}}"

VENV_PYTHON="${BOT_DIR}/.venv/bin/python"
VENV_STREAMLIT="${BOT_DIR}/.venv/bin/streamlit"
VENV_UVICORN="${BOT_DIR}/.venv/bin/uvicorn"

# ── Create log directory ─────────────────────────────────────────
mkdir -p "${LOGS_DIR}"

echo "[start_all] BOT_DIR     : ${BOT_DIR}"
echo "[start_all] LOGS_DIR    : ${LOGS_DIR}"
echo "[start_all] WINE_PREFIX : ${WINE_PREFIX}"
echo "[start_all] API_PORT    : ${API_PORT}"
echo "[start_all] UI_PORT     : ${UI_PORT}"
echo "[start_all] VNC_WEB_PORT: ${VNC_WEB_PORT}"

# ── Start virtual display ────────────────────────────────────────
pkill Xvfb 2>/dev/null || true
sleep 1
nohup Xvfb :99 -screen 0 1024x768x16 > "${LOGS_DIR}/xvfb.log" 2>&1 &
sleep 2
export DISPLAY=:99
echo "[start_all] Xvfb started on :99"

# ── Start MT5 under Wine ─────────────────────────────────────────
export WINEPREFIX="${WINE_PREFIX}"
export WINEARCH=win64
export WINEDEBUG=-all

pkill -f terminal64.exe 2>/dev/null || true
sleep 1

if [[ -f "${MT5_EXE}" ]]; then
    nohup wine "${MT5_EXE}" > "${LOGS_DIR}/mt5.log" 2>&1 &
    MT5_PID=$!
    echo "[start_all] MT5 started: PID=${MT5_PID}"
else
    echo "[start_all] WARN: MT5 executable not found at: ${MT5_EXE}"
    echo "[start_all]       Skipping MT5 start. Run install_mt4_wine.sh if not installed."
fi
sleep 12

# ── Start VNC (for MT5 remote access) ────────────────────────────
pkill x11vnc 2>/dev/null || true
pkill websockify 2>/dev/null || true
sleep 1

nohup x11vnc \
    -display :99 \
    -nopw \
    -rfbport "${VNC_PORT}" \
    -forever \
    -quiet \
    > "${LOGS_DIR}/vnc.log" 2>&1 &
echo "[start_all] x11vnc started on port ${VNC_PORT}"

NOVNC_WEB=""
for candidate in /usr/share/novnc /usr/share/novnc/utils; do
    [[ -d "${candidate}" ]] && { NOVNC_WEB="${candidate}"; break; }
done

if [[ -n "${NOVNC_WEB}" ]]; then
    nohup websockify \
        --web="${NOVNC_WEB}" \
        "${VNC_WEB_PORT}" \
        "localhost:${VNC_PORT}" \
        > "${LOGS_DIR}/novnc.log" 2>&1 &
    echo "[start_all] noVNC started on port ${VNC_WEB_PORT}"
else
    echo "[start_all] WARN: noVNC web files not found — websockify not started"
fi

# ── Start FastAPI backend ────────────────────────────────────────
if [[ -x "${VENV_UVICORN}" ]]; then
    SSL_ARGS=""
    if [[ -f "${SSL_CERT_DIR}/privkey.pem" ]] && [[ -f "${SSL_CERT_DIR}/fullchain.pem" ]]; then
        SSL_ARGS="--ssl-keyfile ${SSL_CERT_DIR}/privkey.pem --ssl-certfile ${SSL_CERT_DIR}/fullchain.pem"
        echo "[start_all] SSL certificates found for ${SSL_DOMAIN}"
    else
        echo "[start_all] WARN: SSL certificates not found at ${SSL_CERT_DIR}"
        echo "[start_all]       API will start without TLS"
    fi

    nohup "${VENV_UVICORN}" app.main:app \
        --host 0.0.0.0 \
        --port "${API_PORT}" \
        ${SSL_ARGS} \
        --workers 1 \
        --log-level info \
        --app-dir "${BOT_DIR}/backend" \
        > "${LOGS_DIR}/api.log" 2>&1 &
    API_PID=$!
    echo "[start_all] API backend started: PID=${API_PID}  port=${API_PORT}"
else
    echo "[start_all] WARN: uvicorn not found at ${VENV_UVICORN}"
    echo "[start_all]       Run: .venv/bin/pip install uvicorn[standard]"
fi

# ── Start Streamlit UI ────────────────────────────────────────────
if [[ -x "${VENV_STREAMLIT}" ]]; then
    nohup "${VENV_STREAMLIT}" run "${BOT_DIR}/ui/app.py" \
        --server.port "${UI_PORT}" \
        --server.address 0.0.0.0 \
        --server.headless true \
        > "${LOGS_DIR}/ui.log" 2>&1 &
    UI_PID=$!
    echo "[start_all] Streamlit UI started: PID=${UI_PID}  port=${UI_PORT}"
else
    echo "[start_all] WARN: streamlit not found at ${VENV_STREAMLIT}"
fi

# ── Start trading bot ────────────────────────────────────────────
if [[ -x "${VENV_PYTHON}" ]]; then
    BOT_MODE_ARG="${BOT_MODE:-live}"
    nohup "${VENV_PYTHON}" "${BOT_DIR}/main.py" --mode "${BOT_MODE_ARG}" \
        > "${LOGS_DIR}/xau_bot.log" 2>&1 &
    BOT_PID=$!
    echo "[start_all] Trading bot started: PID=${BOT_PID}  mode=${BOT_MODE_ARG}"
else
    echo "[start_all] WARN: Python not found at ${VENV_PYTHON}"
    echo "[start_all]       Run: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "  All services started. MT5 needs ~30s to fully load."
echo ""
echo "  Access points:"
echo "  VNC   : http://${VPS_HOST:-<VPS_IP>}:${VNC_WEB_PORT}/vnc.html"
echo "  API   : https://${SSL_DOMAIN}:${API_PORT}/health"
echo "  UI    : http://${VPS_HOST:-<VPS_IP>}:${UI_PORT}"
echo ""
echo "  Then attach XAU_Bridge EA to XAUUSD chart in MT5."
echo "════════════════════════════════════════════════════════"
