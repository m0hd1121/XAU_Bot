"""
routers/logs.py
────────────────
Log access endpoints with full-text search and level filtering.
Also provides a WebSocket endpoint for real-time log tail streaming.

GET  /logs/list                     — available log file names
GET  /logs/{log_type}               — fetch lines with optional search/filter
GET  /logs/{log_type}/download      — download raw log file
WS   /logs/{log_type}/stream        — real-time tail stream over WebSocket
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse

from app.auth.security import get_current_user, require_admin
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Log file registry ─────────────────────────────────────────────────────────

_BOT_ROOT = settings.bot_root

LOG_FILES: dict[str, Path] = {
    "bot":      _BOT_ROOT / "logs" / "xau_bot.log",
    "strategy": _BOT_ROOT / "logs" / "strategy.log",
    "learning": _BOT_ROOT / "logs" / "learning.log",
    "error":    _BOT_ROOT / "logs" / "error.log",
    "api":      settings.api_log_file,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_log_lines(
    path: Path,
    tail: int = 200,
    search: Optional[str] = None,
    level: Optional[str] = None,
    offset_lines: int = 0,
) -> list[str]:
    """Read and filter log lines.  Returns the last `tail` matching lines."""
    if not path.exists():
        return []
    try:
        text = path.read_text(errors="replace")
        lines = text.splitlines()
        if search:
            lines = [line for line in lines if search.lower() in line.lower()]
        if level:
            upper = level.upper()
            lines = [line for line in lines if upper in line]
        if offset_lines:
            lines = lines[offset_lines:]
        return lines[-tail:]
    except Exception as exc:
        logger.warning("Failed to read log %s: %s", path, exc)
        return []


def _get_log_path(log_type: str) -> Path:
    path = LOG_FILES.get(log_type)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown log type '{log_type}'. Available: {list(LOG_FILES.keys())}",
        )
    return path


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.get("/list", summary="Available log files")
async def list_logs(_user=Depends(get_current_user)) -> dict:
    available = []
    for name, path in LOG_FILES.items():
        available.append({
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        })
    return {"logs": available}


@router.get(
    "/{log_type}",
    summary="Fetch log lines with optional search/level filter",
)
async def get_logs(
    log_type: str,
    tail:    int           = Query(200, ge=10, le=5000, description="Number of lines to return"),
    search:  Optional[str] = Query(None, description="Case-insensitive substring filter"),
    level:   Optional[str] = Query(None, description="Filter by log level (INFO, ERROR, etc.)"),
    offset:  int           = Query(0, ge=0, description="Skip first N matching lines"),
    _user=Depends(get_current_user),
) -> dict:
    path = _get_log_path(log_type)
    lines = _read_log_lines(path, tail=tail, search=search, level=level, offset_lines=offset)
    return {
        "log_type": log_type,
        "path": str(path),
        "lines": lines,
        "count": len(lines),
        "filters": {"search": search, "level": level, "tail": tail},
    }


@router.get(
    "/{log_type}/download",
    summary="Download full log file",
    response_class=FileResponse,
)
async def download_log(
    log_type: str,
    _user=Depends(require_admin),
) -> FileResponse:
    path = _get_log_path(log_type)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log file not found")
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="text/plain",
    )


# ── WebSocket log streaming ───────────────────────────────────────────────────

@router.websocket("/{log_type}/stream")
async def stream_log(websocket: WebSocket, log_type: str) -> None:
    """
    Stream new log lines in real time.
    Sends new content every second whenever the file changes.
    Authentication via query param `token` (Bearer token).
    """
    # Basic token validation for WebSocket (cannot use standard headers)
    token = websocket.query_params.get("token")
    if token:
        try:
            from app.auth.security import decode_token, TOKEN_TYPE_ACCESS
            decode_token(token, TOKEN_TYPE_ACCESS)
        except Exception:
            await websocket.close(code=4001)
            return

    path = LOG_FILES.get(log_type)
    if path is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    last_size = 0

    # Send last 50 lines on connect
    if path.exists():
        last_size = path.stat().st_size
        lines = _read_log_lines(path, tail=50)
        if lines:
            await websocket.send_text("\n".join(lines))

    try:
        while True:
            await asyncio.sleep(1)
            if not path.exists():
                continue
            current_size = path.stat().st_size
            if current_size > last_size:
                try:
                    with open(path, errors="replace") as f:
                        f.seek(last_size)
                        new_content = f.read()
                    last_size = current_size
                    if new_content.strip():
                        await websocket.send_text(new_content)
                except Exception as exc:
                    logger.warning("Log stream read error: %s", exc)
            elif current_size < last_size:
                # File was rotated
                last_size = 0
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Log stream WebSocket closed: %s", exc)
