#!/usr/bin/env bash
# =============================================================
# backup.sh — Create a timestamped compressed backup of the
#             XAU/USD trading bot state (data, logs, reports,
#             config, .env).
#
# Usage:
#   bash scripts/backup.sh
#   bash scripts/backup.sh /custom/backup/dir
#
# Output:
#   <BACKUP_DIR>/xaubot_backup_YYYYMMDD_HHMMSS.tar.gz
#   <BACKUP_DIR>/xaubot_backup_YYYYMMDD_HHMMSS.manifest.json
#   <BACKUP_DIR>/xaubot_backup_YYYYMMDD_HHMMSS.sha256
# =============================================================
set -euo pipefail

# ── Locate project root (one level up from this script) ────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Load .env if present ────────────────────────────────────────
if [[ -f "${BOT_ROOT}/.env" ]]; then
    # shellcheck source=/dev/null
    set -a; source "${BOT_ROOT}/.env"; set +a
    echo "[backup] Loaded .env from ${BOT_ROOT}/.env"
fi

# ── Resolve settings with defaults ─────────────────────────────
BACKUP_DIR="${1:-${BACKUP_DIR:-${BOT_ROOT}/backups}}"
DATA_DIR="${DATA_DIR:-${BOT_ROOT}/data}"
LOGS_DIR="${LOGS_DIR:-${BOT_ROOT}/logs}"
REPORTS_DIR="${REPORTS_DIR:-${BOT_ROOT}/reports}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

# Resolve relative paths against BOT_ROOT
[[ "${DATA_DIR}" != /* ]]    && DATA_DIR="${BOT_ROOT}/${DATA_DIR}"
[[ "${LOGS_DIR}" != /* ]]    && LOGS_DIR="${BOT_ROOT}/${LOGS_DIR}"
[[ "${REPORTS_DIR}" != /* ]] && REPORTS_DIR="${BOT_ROOT}/${REPORTS_DIR}"
[[ "${BACKUP_DIR}" != /* ]]  && BACKUP_DIR="${BOT_ROOT}/${BACKUP_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
HOSTNAME_SAFE="$(hostname | tr '.' '_')"
BACKUP_NAME="xaubot_backup_${TIMESTAMP}"
BACKUP_STAGING="${BACKUP_DIR}/.staging_${TIMESTAMP}"

# ── Pretty printer ──────────────────────────────────────────────
info()  { echo "[backup] $(date '+%H:%M:%S') INFO  $*"; }
warn()  { echo "[backup] $(date '+%H:%M:%S') WARN  $*" >&2; }
error() { echo "[backup] $(date '+%H:%M:%S') ERROR $*" >&2; }

# ── Create backup directory ─────────────────────────────────────
mkdir -p "${BACKUP_DIR}"
mkdir -p "${BACKUP_STAGING}"

info "======================================================================"
info "XAU/USD Bot Backup"
info "======================================================================"
info "Backup name   : ${BACKUP_NAME}"
info "Source root   : ${BOT_ROOT}"
info "Backup dir    : ${BACKUP_DIR}"
info "Retention     : ${BACKUP_RETENTION_DAYS} days"
info "======================================================================"

# ── Collect files to archive ────────────────────────────────────
# Build a list of paths relative to BOT_ROOT so the tar is portable
# regardless of where the bot is installed.
INCLUDE_ARGS=()

add_if_exists() {
    local full_path="$1"
    local rel_path="${full_path#${BOT_ROOT}/}"
    if [[ -e "${full_path}" ]]; then
        INCLUDE_ARGS+=("${rel_path}")
        info "  [+] ${rel_path}"
    else
        warn "  [-] skipped (not found): ${rel_path}"
    fi
}

info "Collecting items to back up…"
add_if_exists "${DATA_DIR}"
add_if_exists "${LOGS_DIR}"
add_if_exists "${REPORTS_DIR}"
add_if_exists "${BOT_ROOT}/config.yaml"
add_if_exists "${BOT_ROOT}/.env"

if [[ ${#INCLUDE_ARGS[@]} -eq 0 ]]; then
    error "Nothing to back up — check DATA_DIR / LOGS_DIR paths"
    rmdir "${BACKUP_STAGING}" 2>/dev/null || true
    exit 1
fi

# ── Write manifest.json ─────────────────────────────────────────
info "Writing manifest.json…"
BOT_VERSION="unknown"
if command -v python3 &>/dev/null; then
    BOT_VERSION="$(python3 -c "
import sys, os
sys.path.insert(0, '${BOT_ROOT}')
try:
    import yaml
    c = yaml.safe_load(open('${BOT_ROOT}/config.yaml'))
    print(c.get('bot', {}).get('version', 'unknown'))
except Exception:
    print('unknown')
" 2>/dev/null)" || BOT_VERSION="unknown"
fi

GIT_COMMIT="$(git -C "${BOT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo 'N/A')"
GIT_BRANCH="$(git -C "${BOT_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'N/A')"

# Build JSON array of included paths
PATHS_JSON="["
first=1
for p in "${INCLUDE_ARGS[@]}"; do
    [[ ${first} -eq 0 ]] && PATHS_JSON+=", "
    PATHS_JSON+="\"${p}\""
    first=0
done
PATHS_JSON+="]"

cat > "${BACKUP_STAGING}/manifest.json" <<JSON
{
  "backup_name": "${BACKUP_NAME}",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hostname": "$(hostname)",
  "bot_version": "${BOT_VERSION}",
  "git_commit": "${GIT_COMMIT}",
  "git_branch": "${GIT_BRANCH}",
  "backup_retention_days": ${BACKUP_RETENTION_DAYS},
  "included_paths": ${PATHS_JSON},
  "created_by": "$(whoami)",
  "bot_root": "${BOT_ROOT}"
}
JSON
info "  manifest.json written"

# ── Create the tar.gz ───────────────────────────────────────────
ARCHIVE="${BACKUP_STAGING}/${BACKUP_NAME}.tar.gz"
info "Compressing archive (this may take a moment)…"
# tar exits 1 if some files changed during archiving; treat as warning, not fatal
set +e
tar -czf "${ARCHIVE}" \
    -C "${BOT_ROOT}" \
    "${INCLUDE_ARGS[@]}" \
    2>/dev/null
TAR_EXIT=$?
set -e

if [[ ${TAR_EXIT} -gt 1 ]]; then
    error "tar failed with exit code ${TAR_EXIT}"
    rm -rf "${BACKUP_STAGING}"
    exit 1
elif [[ ${TAR_EXIT} -eq 1 ]]; then
    warn "tar exited with code 1 (some files changed during archiving; archive is still usable)"
fi

ARCHIVE_SIZE="$(du -sh "${ARCHIVE}" | cut -f1)"
info "Archive created: ${ARCHIVE} (${ARCHIVE_SIZE})"

# ── Write SHA-256 checksum ──────────────────────────────────────
info "Computing SHA-256 checksum…"
SHA256_FILE="${BACKUP_STAGING}/${BACKUP_NAME}.sha256"
(cd "${BACKUP_STAGING}" && sha256sum "${BACKUP_NAME}.tar.gz" > "${BACKUP_NAME}.sha256")
SHA256_VALUE="$(awk '{print $1}' "${SHA256_FILE}")"
info "  SHA256: ${SHA256_VALUE}"

# ── Move everything into the final backup directory ─────────────
mv "${BACKUP_STAGING}/${BACKUP_NAME}.tar.gz"   "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
mv "${BACKUP_STAGING}/manifest.json"            "${BACKUP_DIR}/${BACKUP_NAME}.manifest.json"
mv "${BACKUP_STAGING}/${BACKUP_NAME}.sha256"    "${BACKUP_DIR}/${BACKUP_NAME}.sha256"
rmdir "${BACKUP_STAGING}" 2>/dev/null || true

info "Backup files written:"
info "  ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
info "  ${BACKUP_DIR}/${BACKUP_NAME}.manifest.json"
info "  ${BACKUP_DIR}/${BACKUP_NAME}.sha256"

# ── Apply retention policy ──────────────────────────────────────
info "Applying retention policy (keep last ${BACKUP_RETENTION_DAYS} days)…"
DELETED=0
while IFS= read -r old_archive; do
    old_name="$(basename "${old_archive}" .tar.gz)"
    rm -f "${BACKUP_DIR}/${old_name}.tar.gz"
    rm -f "${BACKUP_DIR}/${old_name}.manifest.json"
    rm -f "${BACKUP_DIR}/${old_name}.sha256"
    info "  Deleted old backup: ${old_name}"
    (( DELETED++ )) || true
done < <(find "${BACKUP_DIR}" -maxdepth 1 -name 'xaubot_backup_*.tar.gz' \
            -mtime "+${BACKUP_RETENTION_DAYS}" 2>/dev/null | sort)

if [[ ${DELETED} -eq 0 ]]; then
    info "  No old backups to delete"
else
    info "  Deleted ${DELETED} old backup(s)"
fi

info "======================================================================"
info "Backup complete!"
info "  ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz  (${ARCHIVE_SIZE})"
info "======================================================================"

# Print final archive path on stdout (for capture by export.sh)
echo "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
