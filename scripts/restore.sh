#!/usr/bin/env bash
# =============================================================
# restore.sh — Restore an XAU/USD bot from a migration bundle.
#
# Usage:
#   bash scripts/restore.sh /path/to/xaubot_migration_*.tar.gz
#   bash scripts/restore.sh --dry-run /path/to/bundle.tar.gz
#
# What it does:
#   1. Verifies SHA-256 integrity of the bundle
#   2. Creates a safety backup of current state (pre-restore)
#   3. Extracts the migration bundle to a temp directory
#   4. Extracts the inner backup archive
#   5. Restores: data/, logs/, reports/, config.yaml, .env
#   6. Runs validate.sh at the end
#
# Safety: The pre-restore backup is kept in backups/pre_restore_*
# so you can always roll back by running restore.sh on it.
# =============================================================
set -euo pipefail

# ── Locate project root ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Pretty printer ──────────────────────────────────────────────
info()    { echo "[restore] $(date '+%H:%M:%S') INFO  $*"; }
warn()    { echo "[restore] $(date '+%H:%M:%S') WARN  $*" >&2; }
error()   { echo "[restore] $(date '+%H:%M:%S') ERROR $*" >&2; exit 1; }
success() { echo "[restore] $(date '+%H:%M:%S') OK    $*"; }

# ── Parse arguments ─────────────────────────────────────────────
DRY_RUN=0
BUNDLE_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -*)
            error "Unknown option: $1  Usage: bash scripts/restore.sh [--dry-run] /path/to/bundle.tar.gz"
            ;;
        *)
            BUNDLE_FILE="$1"
            shift
            ;;
    esac
done

if [[ -z "${BUNDLE_FILE}" ]]; then
    echo "Usage: bash scripts/restore.sh [--dry-run] /path/to/xaubot_migration_*.tar.gz"
    exit 1
fi

if [[ ! -f "${BUNDLE_FILE}" ]]; then
    error "Bundle file not found: ${BUNDLE_FILE}"
fi

BUNDLE_ABS="$(realpath "${BUNDLE_FILE}")"
BUNDLE_BASENAME="$(basename "${BUNDLE_ABS}")"

# ── Load .env if present ────────────────────────────────────────
if [[ -f "${BOT_ROOT}/.env" ]]; then
    set -a; source "${BOT_ROOT}/.env"; set +a
    info "Loaded .env from ${BOT_ROOT}/.env"
fi

# ── Resolve directories ─────────────────────────────────────────
DATA_DIR="${DATA_DIR:-${BOT_ROOT}/data}"
LOGS_DIR="${LOGS_DIR:-${BOT_ROOT}/logs}"
REPORTS_DIR="${REPORTS_DIR:-${BOT_ROOT}/reports}"
BACKUP_DIR="${BACKUP_DIR:-${BOT_ROOT}/backups}"

[[ "${DATA_DIR}"    != /* ]] && DATA_DIR="${BOT_ROOT}/${DATA_DIR}"
[[ "${LOGS_DIR}"    != /* ]] && LOGS_DIR="${BOT_ROOT}/${LOGS_DIR}"
[[ "${REPORTS_DIR}" != /* ]] && REPORTS_DIR="${BOT_ROOT}/${REPORTS_DIR}"
[[ "${BACKUP_DIR}"  != /* ]] && BACKUP_DIR="${BOT_ROOT}/${BACKUP_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORK_DIR="${BACKUP_DIR}/.restore_work_${TIMESTAMP}"

# ── Dry-run banner ──────────────────────────────────────────────
if [[ ${DRY_RUN} -eq 1 ]]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║                  DRY-RUN MODE (no changes)               ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
fi

info "======================================================================"
info "XAU/USD Bot Restore"
info "======================================================================"
info "Bundle     : ${BUNDLE_BASENAME}"
info "Bot root   : ${BOT_ROOT}"
info "Dry run    : ${DRY_RUN}"
info "======================================================================"

# ── Cleanup on exit ─────────────────────────────────────────────
trap 'rm -rf "${WORK_DIR}" 2>/dev/null || true' EXIT

mkdir -p "${BACKUP_DIR}"
mkdir -p "${WORK_DIR}"

# ── Step 1: Verify SHA-256 ──────────────────────────────────────
info "Step 1/7: Verifying bundle integrity…"

# Look for a .sha256 file alongside the bundle
SHA256_FILE="${BUNDLE_ABS%.tar.gz}.sha256"
if [[ -f "${SHA256_FILE}" ]]; then
    info "  Found checksum file: $(basename "${SHA256_FILE}")"
    EXPECTED_HASH="$(awk '{print $1}' "${SHA256_FILE}")"
    ACTUAL_HASH="$(sha256sum "${BUNDLE_ABS}" | awk '{print $1}')"
    if [[ "${EXPECTED_HASH}" != "${ACTUAL_HASH}" ]]; then
        error "SHA-256 mismatch! Bundle may be corrupted or tampered with.
  Expected : ${EXPECTED_HASH}
  Actual   : ${ACTUAL_HASH}"
    fi
    success "SHA-256 verified: ${ACTUAL_HASH}"
else
    warn "No .sha256 file found alongside bundle — skipping integrity check"
    warn "Expected: ${SHA256_FILE}"
fi

# ── Step 2: Inspect bundle contents ─────────────────────────────
info "Step 2/7: Inspecting bundle contents…"
BUNDLE_CONTENTS="$(tar -tzf "${BUNDLE_ABS}" 2>/dev/null)"

# Determine if this is a migration bundle or a direct backup archive
if echo "${BUNDLE_CONTENTS}" | grep -q "migration_meta.json"; then
    BUNDLE_TYPE="migration"
    info "  Detected: migration bundle"
else
    BUNDLE_TYPE="backup"
    info "  Detected: direct backup archive"
fi

if [[ ${DRY_RUN} -eq 1 ]]; then
    info "  Contents:"
    echo "${BUNDLE_CONTENTS}" | sed 's/^/    /'
fi

# ── Step 3: Safety backup of current state ──────────────────────
info "Step 3/7: Creating pre-restore safety backup…"

PRE_RESTORE_BACKUP="${BACKUP_DIR}/pre_restore_${TIMESTAMP}"
mkdir -p "${PRE_RESTORE_BACKUP}"

SAFETY_ITEMS=()
[[ -d "${DATA_DIR}" ]]              && SAFETY_ITEMS+=("data")
[[ -d "${LOGS_DIR}" ]]              && SAFETY_ITEMS+=("logs")
[[ -d "${REPORTS_DIR}" ]]           && SAFETY_ITEMS+=("reports")
[[ -f "${BOT_ROOT}/config.yaml" ]]  && SAFETY_ITEMS+=("config.yaml")
[[ -f "${BOT_ROOT}/.env" ]]         && SAFETY_ITEMS+=(".env")

if [[ ${#SAFETY_ITEMS[@]} -gt 0 ]]; then
    if [[ ${DRY_RUN} -eq 1 ]]; then
        info "  [DRY-RUN] Would create safety backup at: ${PRE_RESTORE_BACKUP}"
        for item in "${SAFETY_ITEMS[@]}"; do
            info "  [DRY-RUN]   ${item}"
        done
    else
        set +e
        tar -czf "${PRE_RESTORE_BACKUP}.tar.gz" \
            -C "${BOT_ROOT}" \
            "${SAFETY_ITEMS[@]}" \
            2>/dev/null
        TAR_EXIT=$?
        set -e
        [[ ${TAR_EXIT} -le 1 ]] && success "Safety backup created: ${PRE_RESTORE_BACKUP}.tar.gz" \
                                 || warn "Safety backup had warnings (exit code ${TAR_EXIT}) — proceeding"
    fi
else
    info "  No existing data found — skipping safety backup"
fi

# ── Step 4: Extract bundle ───────────────────────────────────────
info "Step 4/7: Extracting bundle…"

if [[ ${DRY_RUN} -eq 1 ]]; then
    info "  [DRY-RUN] Would extract '${BUNDLE_BASENAME}' to work directory"
else
    tar -xzf "${BUNDLE_ABS}" -C "${WORK_DIR}"
    success "Bundle extracted to work directory"
fi

# ── Step 5: Locate inner backup archive ─────────────────────────
info "Step 5/7: Locating backup archive inside bundle…"

INNER_BACKUP=""
if [[ ${DRY_RUN} -eq 0 ]]; then
    if [[ "${BUNDLE_TYPE}" == "migration" ]]; then
        # Migration bundle: look for xaubot_backup_*.tar.gz inside
        INNER_BACKUP="$(find "${WORK_DIR}" -maxdepth 1 -name 'xaubot_backup_*.tar.gz' | head -1)"
    else
        # Direct backup bundle
        INNER_BACKUP="${BUNDLE_ABS}"
    fi

    if [[ -z "${INNER_BACKUP}" ]] || [[ ! -f "${INNER_BACKUP}" ]]; then
        error "Could not find inner backup archive in bundle. Contents: $(ls -la "${WORK_DIR}")"
    fi
    info "  Inner backup: $(basename "${INNER_BACKUP}")"

    # Show manifest if available
    MANIFEST="$(find "${WORK_DIR}" -maxdepth 1 -name '*.manifest.json' | head -1)"
    if [[ -n "${MANIFEST}" ]]; then
        info "  Manifest contents:"
        cat "${MANIFEST}" | sed 's/^/    /'
    fi
else
    # In dry-run, determine what would be the inner backup
    if [[ "${BUNDLE_TYPE}" == "migration" ]]; then
        INNER_NAME="$(echo "${BUNDLE_CONTENTS}" | grep 'xaubot_backup_.*\.tar\.gz' | head -1)"
        info "  [DRY-RUN] Would use inner backup: ${INNER_NAME}"
    else
        info "  [DRY-RUN] Would use bundle directly as backup archive"
    fi
fi

# ── Step 6: Restore files ────────────────────────────────────────
info "Step 6/7: Restoring files…"

EXTRACT_DIR="${WORK_DIR}/restore_extract"

if [[ ${DRY_RUN} -eq 1 ]]; then
    # In dry-run, show what would be restored from the archive
    ARCHIVE_FOR_PREVIEW="${BUNDLE_ABS}"
    if [[ "${BUNDLE_TYPE}" == "migration" ]]; then
        ARCHIVE_FOR_PREVIEW="$(echo "${BUNDLE_CONTENTS}" | grep 'xaubot_backup_.*\.tar\.gz' | head -1)"
        info "  [DRY-RUN] Would restore from inner backup: ${ARCHIVE_FOR_PREVIEW}"
    fi
    info "  [DRY-RUN] Would restore the following to ${BOT_ROOT}:"

    # Preview top-level items
    tar -tzf "${BUNDLE_ABS}" 2>/dev/null | grep -E '^(data|logs|reports|config\.yaml|\.env)' \
        | sed 's/^/    [DRY-RUN] RESTORE  /' || true

    info "  [DRY-RUN] Destinations:"
    info "    data/       → ${DATA_DIR}"
    info "    logs/       → ${LOGS_DIR}"
    info "    reports/    → ${REPORTS_DIR}"
    info "    config.yaml → ${BOT_ROOT}/config.yaml"
    info "    .env        → ${BOT_ROOT}/.env"
else
    mkdir -p "${EXTRACT_DIR}"
    tar -xzf "${INNER_BACKUP}" -C "${EXTRACT_DIR}"

    # Restore individual components with clear progress
    restore_item() {
        local src_rel="$1"   # relative path inside archive
        local dst="$2"       # absolute destination
        local src="${EXTRACT_DIR}/${src_rel}"
        if [[ -e "${src}" ]]; then
            mkdir -p "$(dirname "${dst}")"
            if [[ -d "${src}" ]]; then
                # Directory: merge (rsync-style with cp)
                mkdir -p "${dst}"
                cp -a "${src}/." "${dst}/"
            else
                cp -a "${src}" "${dst}"
            fi
            success "Restored: ${src_rel} → ${dst}"
        else
            warn "Not found in archive: ${src_rel} (skipping)"
        fi
    }

    restore_item "data"        "${DATA_DIR}"
    restore_item "logs"        "${LOGS_DIR}"
    restore_item "reports"     "${REPORTS_DIR}"
    restore_item "config.yaml" "${BOT_ROOT}/config.yaml"
    restore_item ".env"        "${BOT_ROOT}/.env"
fi

# ── Step 7: Run validate.sh ──────────────────────────────────────
info "Step 7/7: Running post-restore validation…"

VALIDATE_SCRIPT="${SCRIPT_DIR}/validate.sh"
if [[ -f "${VALIDATE_SCRIPT}" ]]; then
    if [[ ${DRY_RUN} -eq 1 ]]; then
        info "  [DRY-RUN] Would run: bash ${VALIDATE_SCRIPT}"
    else
        echo ""
        bash "${VALIDATE_SCRIPT}" || warn "Validation completed with warnings/failures — review above"
        echo ""
    fi
else
    warn "validate.sh not found at ${VALIDATE_SCRIPT} — skipping validation"
fi

# ── Summary ──────────────────────────────────────────────────────
echo ""
info "======================================================================"
if [[ ${DRY_RUN} -eq 1 ]]; then
    info "DRY-RUN complete — no changes were made"
    info "Remove --dry-run to perform the actual restore"
else
    info "Restore complete!"
    [[ -f "${PRE_RESTORE_BACKUP}.tar.gz" ]] && \
        info "  Pre-restore safety backup: ${PRE_RESTORE_BACKUP}.tar.gz"
    info ""
    info "Next steps:"
    info "  1. Review the validation report above"
    info "  2. Update .env if the VPS IP or domain has changed"
    info "  3. sudo systemctl start xaubot"
    info "  4. sudo journalctl -u xaubot -f"
fi
info "======================================================================"
