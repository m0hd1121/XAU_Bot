#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DASH_DIR="$REPO_ROOT/dashboard"
LOG_DIR="$REPO_ROOT/logs"

mkdir -p "$LOG_DIR"

# ── Resolve the backend API URL ───────────────────────────────────────────────
# Priority: 1) NEXT_PUBLIC_API_URL env var  2) .env.dashboard file  3) auto-detect
if [[ -z "${NEXT_PUBLIC_API_URL:-}" ]]; then
  ENV_FILE="$REPO_ROOT/.env.dashboard"
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
  fi
fi

if [[ -z "${NEXT_PUBLIC_API_URL:-}" ]]; then
  # Fall back to the machine's primary public IP on port 8443
  PUBLIC_IP="$(curl -sf --max-time 3 https://api.ipify.org || hostname -I | awk '{print $1}')"
  export NEXT_PUBLIC_API_URL="http://${PUBLIC_IP}:8443"
  echo "==> NEXT_PUBLIC_API_URL not set — auto-detected: $NEXT_PUBLIC_API_URL"
else
  export NEXT_PUBLIC_API_URL
  echo "==> Using NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL"
fi

echo "==> Building dashboard..."
cd "$DASH_DIR"
npm ci --prefer-offline
npm run build

# Verify standalone output exists
if [[ ! -f ".next/standalone/server.js" ]]; then
  echo "ERROR: .next/standalone/server.js not found — build may have failed" >&2
  exit 1
fi

# Verify static files were copied (build script does this, but double-check)
if [[ ! -d ".next/standalone/.next/static" ]]; then
  echo "==> Copying static files into standalone directory..."
  cp -r .next/static .next/standalone/.next/static
fi

if [[ -d "public" ]]; then
  cp -r public .next/standalone/public 2>/dev/null || true
fi

echo "==> Restarting PM2 dashboard process..."
if pm2 describe xau-dashboard > /dev/null 2>&1; then
  pm2 delete xau-dashboard
fi

pm2 start pm2.config.js
pm2 save

echo ""
echo "==> Dashboard deployed successfully."
echo "    URL: http://$(hostname -I | awk '{print $1}'):3000"
pm2 show xau-dashboard | grep -E "status|uptime|restarts" || true
