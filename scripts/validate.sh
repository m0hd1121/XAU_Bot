#!/usr/bin/env bash
# =============================================================
# validate.sh — Post-migration / post-install validation for
#               the XAU/USD Price Action Trading Bot.
#
# Usage:
#   bash scripts/validate.sh
#
# Outputs a structured PASS / FAIL / WARN report for:
#   1.  Python venv and key packages importable
#   2.  config.yaml valid YAML with required keys
#   3.  Data directory structure
#   4.  Broker file bridge (XAU_Accounts.json freshness)
#   5.  Bot process running (PID check)
#   6.  API health endpoint
#   7.  UI health endpoint
#   8.  Learning DB (if learning.enabled)
#   9.  Log file writable
#   10. Disk space >= 500 MB free
# =============================================================
set -uo pipefail  # no -e so we can collect all results

# ── Locate project root ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Load .env if present ────────────────────────────────────────
if [[ -f "${BOT_ROOT}/.env" ]]; then
    # shellcheck source=/dev/null
    set -a; source "${BOT_ROOT}/.env"; set +a
fi

# ── Resolve paths with defaults ─────────────────────────────────
DATA_DIR="${DATA_DIR:-${BOT_ROOT}/data}"
LOGS_DIR="${LOGS_DIR:-${BOT_ROOT}/logs}"
REPORTS_DIR="${REPORTS_DIR:-${BOT_ROOT}/reports}"
MT5_FILES_PATH="${MT5_FILES_PATH:-/home/botuser/.wine-mt4/drive_c/Program Files/MetaTrader 5/MQL5/Files}"
API_PORT="${API_PORT:-8443}"
UI_PORT="${UI_PORT:-8502}"
VENV_DIR="${VENV_DIR:-${BOT_ROOT}/.venv}"

# Resolve relative paths
[[ "${DATA_DIR}"    != /* ]] && DATA_DIR="${BOT_ROOT}/${DATA_DIR}"
[[ "${LOGS_DIR}"    != /* ]] && LOGS_DIR="${BOT_ROOT}/${LOGS_DIR}"
[[ "${REPORTS_DIR}" != /* ]] && REPORTS_DIR="${BOT_ROOT}/${REPORTS_DIR}"

# ── Report state ─────────────────────────────────────────────────
PASS=0; FAIL=0; WARN=0
RESULTS=()    # array of "STATUS|CHECK|DETAIL"

pass() {
    local check="$1" detail="${2:-}"
    RESULTS+=("PASS|${check}|${detail}")
    (( PASS++ )) || true
}

fail() {
    local check="$1" detail="${2:-}"
    RESULTS+=("FAIL|${check}|${detail}")
    (( FAIL++ )) || true
}

warn_check() {
    local check="$1" detail="${2:-}"
    RESULTS+=("WARN|${check}|${detail}")
    (( WARN++ )) || true
}

# ─────────────────────────────────────────────────────────────────
# CHECK 1: Python venv + key imports
# ─────────────────────────────────────────────────────────────────
PYTHON_BIN=""
# Prefer .venv in BOT_ROOT
for candidate in \
    "${BOT_ROOT}/.venv/bin/python" \
    "${BOT_ROOT}/venv/bin/python" \
    "${BOT_ROOT}/.venv/bin/python3" \
    "$(command -v python3 2>/dev/null || true)"; do
    [[ -x "${candidate}" ]] && { PYTHON_BIN="${candidate}"; break; }
done

if [[ -z "${PYTHON_BIN}" ]]; then
    fail "Python venv" "No Python executable found"
else
    PYTHON_VER="$("${PYTHON_BIN}" --version 2>&1)"
    pass "Python executable" "${PYTHON_VER} → ${PYTHON_BIN}"

    IMPORT_ERRORS=()
    for pkg in yaml pandas numpy requests; do
        "${PYTHON_BIN}" -c "import ${pkg}" 2>/dev/null || IMPORT_ERRORS+=("${pkg}")
    done

    if [[ ${#IMPORT_ERRORS[@]} -eq 0 ]]; then
        pass "Python packages" "yaml, pandas, numpy, requests all importable"
    else
        fail "Python packages" "Cannot import: ${IMPORT_ERRORS[*]}"
    fi

    # Check bot module importable
    if "${PYTHON_BIN}" -c "import sys; sys.path.insert(0,'${BOT_ROOT}'); import xau_bot" 2>/dev/null; then
        pass "Bot module (xau_bot)" "importable"
    else
        warn_check "Bot module (xau_bot)" "Cannot import — may indicate missing dependencies or path issue"
    fi
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 2: config.yaml valid YAML with required keys
# ─────────────────────────────────────────────────────────────────
CONFIG="${BOT_ROOT}/config.yaml"
REQUIRED_KEYS=("bot" "risk" "strategy" "broker" "logging" "backtest")

if [[ ! -f "${CONFIG}" ]]; then
    fail "config.yaml" "File not found: ${CONFIG}"
else
    if [[ -n "${PYTHON_BIN}" ]]; then
        MISSING_KEYS=()
        PARSE_RESULT="$("${PYTHON_BIN}" -c "
import sys, yaml
try:
    with open('${CONFIG}') as f:
        cfg = yaml.safe_load(f)
    required = ${REQUIRED_KEYS[*]@Q}
    missing = [k for k in required.split() if k not in cfg]
    if missing:
        print('MISSING:' + ','.join(missing))
    else:
        print('OK')
except Exception as e:
    print('ERROR:' + str(e))
" 2>&1)" || PARSE_RESULT="ERROR:parse failed"

        if [[ "${PARSE_RESULT}" == "OK" ]]; then
            pass "config.yaml" "Valid YAML, all required keys present"
        elif [[ "${PARSE_RESULT}" == MISSING:* ]]; then
            MISSING="${PARSE_RESULT#MISSING:}"
            fail "config.yaml" "Missing keys: ${MISSING}"
        else
            fail "config.yaml" "Parse error: ${PARSE_RESULT}"
        fi
    else
        # Fallback: check for key names with grep
        MISSING_KEYS=()
        for key in "${REQUIRED_KEYS[@]}"; do
            grep -q "^${key}:" "${CONFIG}" 2>/dev/null || MISSING_KEYS+=("${key}")
        done
        if [[ ${#MISSING_KEYS[@]} -eq 0 ]]; then
            pass "config.yaml" "File exists, required top-level keys found (python not available for full parse)"
        else
            fail "config.yaml" "Missing keys: ${MISSING_KEYS[*]}"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 3: Data directory structure
# ─────────────────────────────────────────────────────────────────
for dir_var in "${DATA_DIR}" "${LOGS_DIR}" "${REPORTS_DIR}"; do
    dir_name="$(basename "${dir_var}")"
    if [[ -d "${dir_var}" ]]; then
        FILE_COUNT="$(find "${dir_var}" -maxdepth 1 -type f 2>/dev/null | wc -l)"
        pass "Directory: ${dir_name}/" "exists, ${FILE_COUNT} file(s)"
    else
        warn_check "Directory: ${dir_name}/" "Not found: ${dir_var} (will be created on first run)"
    fi
done

# ─────────────────────────────────────────────────────────────────
# CHECK 4: Broker file bridge (XAU_Accounts.json)
# ─────────────────────────────────────────────────────────────────
# The DWX bridge EA writes account info to XAU_Accounts.json.
# If it was written in the last 60 seconds, MT5 + EA are running.
ACCOUNTS_JSON="${MT5_FILES_PATH}/XAU_Accounts.json"

if [[ ! -d "${MT5_FILES_PATH}" ]]; then
    warn_check "MT5 files path" "Directory not found: ${MT5_FILES_PATH} (normal if MT5 not installed yet)"
elif [[ ! -f "${ACCOUNTS_JSON}" ]]; then
    warn_check "XAU_Accounts.json" "Not found — MT5 + XAU_Bridge EA may not be running"
else
    # Check file age (seconds since last modification)
    FILE_AGE=$(( $(date +%s) - $(stat -c %Y "${ACCOUNTS_JSON}" 2>/dev/null || echo 0) ))
    if [[ ${FILE_AGE} -lt 60 ]]; then
        pass "XAU_Accounts.json (DWX bridge)" "Fresh (${FILE_AGE}s old) — MT5 + EA running"
    elif [[ ${FILE_AGE} -lt 300 ]]; then
        warn_check "XAU_Accounts.json (DWX bridge)" "Stale (${FILE_AGE}s old) — MT5 may be starting up"
    else
        fail "XAU_Accounts.json (DWX bridge)" "Very stale (${FILE_AGE}s old) — MT5 + XAU_Bridge EA not running"
    fi
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 5: Bot process running
# ─────────────────────────────────────────────────────────────────
# Look for python main.py OR the systemd service
BOT_PID=""

# Check systemd
if systemctl is-active --quiet xaubot 2>/dev/null; then
    BOT_PID="$(systemctl show xaubot --property=MainPID --value 2>/dev/null || echo '')"
    pass "Bot process (systemd)" "xaubot.service is active, PID=${BOT_PID}"
else
    # Fallback: look for python main.py
    BOT_PID="$(pgrep -f "python.*main\.py" 2>/dev/null | head -1 || true)"
    if [[ -n "${BOT_PID}" ]]; then
        pass "Bot process" "Running as PID=${BOT_PID}"
    else
        warn_check "Bot process" "Not running (expected during fresh install; start with: sudo systemctl start xaubot)"
    fi
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 6: API health endpoint
# ─────────────────────────────────────────────────────────────────
if [[ -n "${API_PORT:-}" ]]; then
    API_URL="https://localhost:${API_PORT}/health"
    HTTP_CODE="$(curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "${API_URL}" 2>/dev/null || echo "000")"
    if [[ "${HTTP_CODE}" == "200" ]]; then
        pass "API endpoint (${API_URL})" "HTTP ${HTTP_CODE}"
    elif [[ "${HTTP_CODE}" == "000" ]]; then
        warn_check "API endpoint (${API_URL})" "Not reachable (connection refused — may be starting up)"
    else
        warn_check "API endpoint (${API_URL})" "HTTP ${HTTP_CODE}"
    fi
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 7: UI health endpoint
# ─────────────────────────────────────────────────────────────────
if [[ -n "${UI_PORT:-}" ]]; then
    UI_URL="http://localhost:${UI_PORT}"
    HTTP_CODE="$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "${UI_URL}" 2>/dev/null || echo "000")"
    if [[ "${HTTP_CODE}" =~ ^(200|302|303)$ ]]; then
        pass "UI endpoint (${UI_URL})" "HTTP ${HTTP_CODE}"
    elif [[ "${HTTP_CODE}" == "000" ]]; then
        warn_check "UI endpoint (${UI_URL})" "Not reachable (connection refused — may be starting up)"
    else
        warn_check "UI endpoint (${UI_URL})" "HTTP ${HTTP_CODE}"
    fi
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 8: Learning DB (if learning.enabled in config)
# ─────────────────────────────────────────────────────────────────
LEARNING_ENABLED="false"
if [[ -f "${CONFIG}" ]] && [[ -n "${PYTHON_BIN}" ]]; then
    LEARNING_ENABLED="$("${PYTHON_BIN}" -c "
import yaml
try:
    c = yaml.safe_load(open('${CONFIG}'))
    print(str(c.get('learning', {}).get('enabled', False)).lower())
except Exception:
    print('false')
" 2>/dev/null || echo "false")"
fi

if [[ "${LEARNING_ENABLED}" == "true" ]]; then
    # Get db_path from config or use default
    LEARNING_DB=""
    if [[ -n "${PYTHON_BIN}" ]]; then
        LEARNING_DB="$("${PYTHON_BIN}" -c "
import yaml, os
try:
    c = yaml.safe_load(open('${CONFIG}'))
    db = c.get('learning', {}).get('db_path', 'data/learning.db')
    if not os.path.isabs(db):
        db = os.path.join('${BOT_ROOT}', db)
    print(db)
except Exception:
    print('${DATA_DIR}/learning.db')
" 2>/dev/null)" || LEARNING_DB="${DATA_DIR}/learning.db"
    else
        LEARNING_DB="${DATA_DIR}/learning.db"
    fi

    if [[ -f "${LEARNING_DB}" ]]; then
        DB_SIZE="$(du -sh "${LEARNING_DB}" 2>/dev/null | cut -f1)"
        pass "Learning DB" "${LEARNING_DB} (${DB_SIZE})"
    else
        warn_check "Learning DB" "Not found: ${LEARNING_DB} (will be created on first run)"
    fi
else
    pass "Learning DB" "learning.enabled=false — skipped"
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 9: Log file writable
# ─────────────────────────────────────────────────────────────────
mkdir -p "${LOGS_DIR}" 2>/dev/null || true
TEST_LOG="${LOGS_DIR}/.validate_write_test_$$"
if touch "${TEST_LOG}" 2>/dev/null; then
    rm -f "${TEST_LOG}"
    pass "Log directory writable" "${LOGS_DIR}"
else
    fail "Log directory writable" "Cannot write to ${LOGS_DIR} — check permissions"
fi

# ─────────────────────────────────────────────────────────────────
# CHECK 10: Disk space >= 500 MB free
# ─────────────────────────────────────────────────────────────────
# Check free space on the filesystem containing BOT_ROOT
FREE_KB="$(df -k "${BOT_ROOT}" 2>/dev/null | awk 'NR==2 {print $4}')"
FREE_MB=$(( ${FREE_KB:-0} / 1024 ))

if [[ ${FREE_MB} -ge 500 ]]; then
    pass "Disk space" "${FREE_MB} MB free on $(df -k "${BOT_ROOT}" 2>/dev/null | awk 'NR==2 {print $1}')"
elif [[ ${FREE_MB} -ge 100 ]]; then
    warn_check "Disk space" "Only ${FREE_MB} MB free — consider cleaning logs/backups"
else
    fail "Disk space" "Only ${FREE_MB} MB free — bot may fail to write data"
fi

# ─────────────────────────────────────────────────────────────────
# Print report
# ─────────────────────────────────────────────────────────────────
echo ""
echo "======================================================================"
echo "  XAU/USD Bot — Validation Report"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "  Host: $(hostname)"
echo "======================================================================"
echo ""
printf "  %-6s  %-42s  %s\n" "STATUS" "CHECK" "DETAIL"
echo "  ──────  ──────────────────────────────────────────  ────────────────"

for result in "${RESULTS[@]}"; do
    STATUS="${result%%|*}"
    REST="${result#*|}"
    CHECK="${REST%%|*}"
    DETAIL="${REST#*|}"

    case "${STATUS}" in
        PASS) COLOUR='\033[0;32m' ;;
        FAIL) COLOUR='\033[0;31m' ;;
        WARN) COLOUR='\033[1;33m' ;;
        *)    COLOUR='\033[0m'    ;;
    esac
    RESET='\033[0m'
    printf "  ${COLOUR}%-6s${RESET}  %-42s  %s\n" "${STATUS}" "${CHECK}" "${DETAIL}"
done

echo ""
echo "======================================================================"
echo "  Results: ${PASS} PASS  |  ${WARN} WARN  |  ${FAIL} FAIL"
echo "======================================================================"
echo ""

if [[ ${FAIL} -gt 0 ]]; then
    echo "  ACTION REQUIRED: ${FAIL} check(s) failed. Review FAIL items above."
    echo ""
fi

if [[ ${WARN} -gt 0 ]]; then
    echo "  WARNINGS: ${WARN} check(s) need attention. Review WARN items above."
    echo ""
fi

if [[ ${FAIL} -eq 0 ]] && [[ ${WARN} -eq 0 ]]; then
    echo "  All checks passed. The bot installation looks healthy!"
    echo ""
fi

# Exit with non-zero if any FAIL
[[ ${FAIL} -eq 0 ]]
