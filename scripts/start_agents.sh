#!/usr/bin/env bash
# start_agents.sh — Start all three autonomous trading agents
#
# Usage:
#   bash scripts/start_agents.sh           # start all three agents
#   bash scripts/start_agents.sh 1         # start only agent 1
#
# Each agent runs under nohup and writes its PID to /tmp/xaubot_agent{N}.pid
# Logs go to logs/agent{N}.log (also configured in the systemd unit files).
#
# To stop all agents:
#   for N in 1 2 3; do
#     pid_file="/tmp/xaubot_agent${N}.pid"
#     [[ -f "$pid_file" ]] && kill "$(cat "$pid_file")" && rm "$pid_file"
#   done

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${BOT_ROOT}/.venv/bin/python"
LOGS_DIR="${BOT_ROOT}/logs"

# ── Source .env if present ────────────────────────────────────────────────────
if [[ -f "${BOT_ROOT}/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${BOT_ROOT}/.env"
    set +a
    echo "[start_agents] Loaded .env"
fi

# ── Ensure log directory exists ───────────────────────────────────────────────
mkdir -p "${LOGS_DIR}"

# ── Validate Python ───────────────────────────────────────────────────────────
if [[ ! -x "${PYTHON}" ]]; then
    echo "[start_agents] ERROR: Python not found at ${PYTHON}" >&2
    echo "  Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# ── Determine which agents to start ──────────────────────────────────────────
if [[ $# -ge 1 ]]; then
    AGENTS=("$1")
else
    AGENTS=(1 2 3)
fi

# ── Helper: check if an agent is already running ─────────────────────────────
_is_running() {
    local n="$1"
    local pid_file="/tmp/xaubot_agent${n}.pid"
    if [[ -f "${pid_file}" ]]; then
        local pid
        pid="$(cat "${pid_file}")"
        if kill -0 "${pid}" 2>/dev/null; then
            return 0   # running
        else
            rm -f "${pid_file}"
        fi
    fi
    return 1   # not running
}

# ── Helper: start one agent ───────────────────────────────────────────────────
_start_agent() {
    local n="$1"
    local log_file="${LOGS_DIR}/agent${n}.log"
    local pid_file="/tmp/xaubot_agent${n}.pid"

    if _is_running "${n}"; then
        echo "[start_agents] Agent ${n} is already running (PID $(cat "${pid_file}"))"
        return 0
    fi

    echo "[start_agents] Starting Agent ${n}..."
    nohup "${PYTHON}" "${BOT_ROOT}/agents/run_agent.py" "${n}" \
        >> "${log_file}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${pid_file}"
    echo "[start_agents] Agent ${n} started (PID ${pid}, log: ${log_file})"
}

# ── Start agents in sequence, waiting between each ───────────────────────────
STARTED=()
for N in "${AGENTS[@]}"; do
    _start_agent "${N}"
    STARTED+=("${N}")
    # Wait 5 seconds between starts so each agent can initialise its DB state
    # before the next one tries to read it (skipped after the last agent)
    if [[ "${N}" != "${AGENTS[-1]}" ]]; then
        echo "[start_agents] Waiting 5 seconds before starting next agent..."
        sleep 5
    fi
done

# ── Status summary ────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  XAU Bot Agent Status"
echo "=========================================="
for N in 1 2 3; do
    pid_file="/tmp/xaubot_agent${N}.pid"
    if [[ -f "${pid_file}" ]]; then
        pid="$(cat "${pid_file}")"
        if kill -0 "${pid}" 2>/dev/null; then
            echo "  Agent ${N}: RUNNING  (PID ${pid})"
        else
            echo "  Agent ${N}: DEAD     (stale PID file)"
        fi
    else
        echo "  Agent ${N}: STOPPED"
    fi
done
echo "=========================================="
echo ""
echo "Logs:"
for N in "${STARTED[@]}"; do
    echo "  Agent ${N}: ${LOGS_DIR}/agent${N}.log"
done
echo ""
echo "To stop all agents:"
echo "  for N in 1 2 3; do"
echo "    pid_file=\"/tmp/xaubot_agent\${N}.pid\""
echo "    [[ -f \"\$pid_file\" ]] && kill \"\$(cat \"\$pid_file\")\" && rm \"\$pid_file\""
echo "  done"
