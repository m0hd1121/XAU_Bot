#!/usr/bin/env bash
# check_agents.sh — Quick environment diagnostic for the agent subsystem.
# Run this on the VPS if agents 2 or 3 fail to start.
# Usage:  bash scripts/check_agents.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== XAU Bot Agent Environment Check ==="
echo "Repo root : $REPO_ROOT"
echo "Python    : $VENV_PY"
echo ""

if [[ ! -x "$VENV_PY" ]]; then
    echo "ERROR: venv Python not found at $VENV_PY"
    exit 1
fi

echo "Python version: $("$VENV_PY" --version 2>&1)"
echo ""

echo "--- Core packages ---"
"$VENV_PY" -c "
packages = ['pandas', 'numpy', 'requests', 'yfinance', 'psutil', 'yaml', 'aiosqlite']
for pkg in packages:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, '__version__', '(no version attr)')
        print(f'  OK  {pkg} {ver}')
    except ImportError as e:
        print(f'  MISSING  {pkg}: {e}')
"

echo ""
echo "--- Agent imports ---"
cd "$REPO_ROOT"
"$VENV_PY" -c "
import sys
sys.path.insert(0, '.')
agents = [
    ('agent1', 'agents.agent1_researcher', 'Agent1ResearcherAgent'),
    ('agent2', 'agents.agent2_intelligence', 'Agent2IntelligenceAgent'),
    ('agent3', 'agents.agent3_trader', 'Agent3TraderAgent'),
]
for name, module, cls in agents:
    try:
        import importlib
        m = importlib.import_module(module)
        getattr(m, cls)
        print(f'  OK  {name} ({module})')
    except Exception as e:
        print(f'  FAIL {name}: {e}')
"

echo ""
echo "--- Agent log tails ---"
for N in 1 2 3; do
    LOG="$REPO_ROOT/logs/agent${N}.log"
    if [[ -f "$LOG" ]]; then
        echo "== agent${N}.log (last 20 lines) =="
        tail -20 "$LOG"
    else
        echo "== agent${N}.log: not found (agent never started) =="
    fi
    echo ""
done

echo "--- DB status ---"
DB="$REPO_ROOT/data/agents.db"
if [[ -f "$DB" ]]; then
    "$VENV_PY" -c "
import sqlite3, json
conn = sqlite3.connect('$DB')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT agent_id, status, current_task, last_heartbeat FROM agent_state ORDER BY agent_id').fetchall()
if not rows:
    print('  (no agent_state rows in DB)')
for r in rows:
    import time
    age = time.time() - r['last_heartbeat']
    print(f'  {r[\"agent_id\"]}: status={r[\"status\"]} task=\"{r[\"current_task\"]}\" heartbeat={age:.0f}s ago')
conn.close()
"
else
    echo "  agents.db not found at $DB"
fi

echo ""
echo "=== Done ==="
