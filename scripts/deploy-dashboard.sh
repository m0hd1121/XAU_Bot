#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DASH_DIR="$REPO_ROOT/dashboard"
LOG_DIR="$REPO_ROOT/logs"

mkdir -p "$LOG_DIR"

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
