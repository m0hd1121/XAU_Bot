"""
routers/backup.py
──────────────────
Backup and export endpoints.

POST /backup/create              — create tar.gz of DB + config (+ optional logs)
GET  /backup                     — list all backups with metadata
GET  /backup/download/{name}     — download a backup archive
DELETE /backup/{name}            — delete a backup
POST /backup/restore/{name}      — restore DB and config from a backup
GET  /backup/export/trades       — export full trade history as CSV
GET  /backup/export/analytics    — export performance summary as JSON
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.security import require_admin
from app.config import settings
from app.services.bot_service import bot_service

logger = logging.getLogger(__name__)
router = APIRouter()

BACKUP_DIR = settings.backup_dir
BOT_ROOT   = settings.bot_root


# ── Schemas ───────────────────────────────────────────────────────────────────

class BackupCreateRequest(BaseModel):
    include_logs: bool = False
    notes: Optional[str] = None


class BackupInfo(BaseModel):
    filename: str
    size_bytes: int
    created_at: str
    checksum_sha256: Optional[str] = None
    notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(name: str) -> str:
    """Reject path traversal attempts."""
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid backup name",
        )
    return name


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", summary="List all backup archives")
async def list_backups(_user=Depends(require_admin)) -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = []
    for f in sorted(BACKUP_DIR.glob("*.tar.gz"), reverse=True):
        backups.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": datetime.fromtimestamp(
                f.stat().st_ctime, tz=timezone.utc
            ).isoformat(),
        })
    return {"backups": backups, "count": len(backups)}


@router.post("/create", summary="Create a new backup archive")
async def create_backup(
    req: BackupCreateRequest,
    user=Depends(require_admin),
) -> dict:
    """
    Creates a tar.gz archive containing:
      • config.yaml
      • data/ directory (includes learning.db and any JSON state files)
      • logs/ (optional, excluded by default to keep backups small)
    Records the backup in the BackupRecord table.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"xaubot_backup_{ts}.tar.gz"
    backup_path = BACKUP_DIR / filename

    include_paths = [
        BOT_ROOT / "config.yaml",
        BOT_ROOT / "data",
    ]
    if req.include_logs:
        include_paths.append(BOT_ROOT / "logs")

    try:
        with tarfile.open(backup_path, "w:gz") as tar:
            for item in include_paths:
                if item.exists():
                    tar.add(item, arcname=item.name)
    except Exception as exc:
        backup_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {exc}",
        )

    size = backup_path.stat().st_size
    checksum = _checksum(backup_path)

    # Persist record in API DB
    try:
        from app.database import db_session
        from app.models.models import BackupRecord
        async with db_session() as db:
            record = BackupRecord(
                filename=filename,
                size_bytes=size,
                includes_db=True,
                includes_config=True,
                includes_logs=req.include_logs,
                created_by=user.username,
                notes=req.notes,
                checksum_sha256=checksum,
            )
            db.add(record)
    except Exception as exc:
        logger.warning("Failed to write BackupRecord: %s", exc)

    # Rotate old backups
    _rotate_backups()

    logger.info("Backup created filename=%s size=%d user=%s", filename, size, user.username)
    return {
        "ok": True,
        "filename": filename,
        "size_bytes": size,
        "checksum_sha256": checksum,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _rotate_backups() -> None:
    """Keep only the most recent N backups; delete older ones."""
    files = sorted(BACKUP_DIR.glob("*.tar.gz"), reverse=True)
    for old in files[settings.max_backups_to_keep:]:
        try:
            old.unlink()
            logger.info("Old backup deleted: %s", old.name)
        except Exception as exc:
            logger.warning("Failed to delete old backup %s: %s", old.name, exc)


@router.get("/download/{name}", summary="Download a backup archive")
async def download_backup(
    name: str,
    _user=Depends(require_admin),
) -> StreamingResponse:
    _safe_name(name)
    path = BACKUP_DIR / name
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")

    def _stream():
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _stream(),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Content-Length": str(path.stat().st_size),
        },
    )


@router.delete("/{name}", summary="Delete a backup archive")
async def delete_backup(
    name: str,
    user=Depends(require_admin),
) -> dict:
    _safe_name(name)
    path = BACKUP_DIR / name
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    path.unlink()
    logger.info("Backup deleted filename=%s user=%s", name, user.username)
    return {"ok": True, "filename": name}


@router.post("/restore/{name}", summary="Restore DB and config from a backup")
async def restore_backup(
    name: str,
    user=Depends(require_admin),
) -> dict:
    """
    Extracts config.yaml and the data/ directory from the backup.
    The bot must be stopped before restoring.
    After restore, the bot needs to be restarted manually.
    """
    _safe_name(name)
    path = BACKUP_DIR / name
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")

    # Safety check: bot should not be running during restore
    if await bot_service.is_bot_running():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stop the bot before restoring a backup",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        try:
            with tarfile.open(path, "r:gz") as tar:
                tar.extractall(tmp)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to extract backup: {exc}",
            )

        # Restore config.yaml
        cfg_src = tmp / "config.yaml"
        if cfg_src.exists():
            shutil.copy2(cfg_src, BOT_ROOT / "config.yaml")

        # Restore data directory
        data_src = tmp / "data"
        if data_src.exists():
            data_dst = BOT_ROOT / "data"
            data_dst.mkdir(parents=True, exist_ok=True)
            for item in data_src.iterdir():
                shutil.copy2(item, data_dst / item.name)

    # Update record
    try:
        from app.database import db_session
        from app.models.models import BackupRecord
        from sqlalchemy import update
        async with db_session() as db:
            await db.execute(
                update(BackupRecord)
                .where(BackupRecord.filename == name)
                .values(restored_at=datetime.now(tz=timezone.utc))
            )
    except Exception:
        pass

    logger.warning("Backup restored filename=%s user=%s", name, user.username)
    return {
        "ok": True,
        "filename": name,
        "message": "Backup restored. Restart the bot to apply changes.",
    }


@router.get("/export/trades", summary="Export full trade history as CSV")
async def export_trades(_user=Depends(require_admin)) -> StreamingResponse:
    trades = bot_service.get_trade_history(limit=100_000)
    buf = io.StringIO()
    if trades:
        writer = csv.DictWriter(buf, fieldnames=list(trades[0].keys()))
        writer.writeheader()
        writer.writerows(trades)
    buf.seek(0)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="xaubot_trades_{ts}.csv"'},
    )


@router.get("/export/analytics", summary="Export full analytics report as JSON")
async def export_analytics(_user=Depends(require_admin)) -> StreamingResponse:
    data = {
        "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        "metrics": bot_service.get_performance_metrics(),
        "equity_curve": bot_service.get_equity_curve(),
        "drawdown_series": bot_service.get_drawdown_series(),
        "learning": bot_service.get_learning_stats(),
        "pattern_stats": bot_service.get_pattern_stats(min_samples=5),
        "regime_history": bot_service.get_regime_history(limit=500),
    }
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    payload = json.dumps(data, indent=2, default=str).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="xaubot_analytics_{ts}.json"'},
    )
