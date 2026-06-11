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
import re
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
    "trading":  _BOT_ROOT / "logs" / "xau_bot.log",   # alias
    "api":      settings.api_log_file,
    "trades":   _BOT_ROOT / "logs" / "trades.csv",
    "strategy": _BOT_ROOT / "logs" / "strategy.log",
    "learning": _BOT_ROOT / "logs" / "learning.log",
    "error":    _BOT_ROOT / "logs" / "error.log",
    "agent1":   _BOT_ROOT / "logs" / "agent1.log",
    "agent2":   _BOT_ROOT / "logs" / "agent2.log",
    "agent3":   _BOT_ROOT / "logs" / "agent3.log",
    "vps":      settings.api_log_file,                 # alias to api log
    "auth":     settings.api_log_file,                 # alias to api log
}

# Matches: "2026-06-09 10:09:07  INFO      __main__  message text"
_LOG_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s{2,}(\w+)\s{2,}(\S+)\s{2,}(.+)$'
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_line(line: str, fallback_level: str = "INFO") -> dict:
    """Parse a structured log line into {timestamp, level, source, message}."""
    m = _LOG_RE.match(line.strip())
    if m:
        return {
            "timestamp": m.group(1),
            "level":     m.group(2).upper(),
            "source":    m.group(3),
            "message":   m.group(4),
            "extra":     None,
        }
    # Unstructured line (e.g. trades CSV row or raw output)
    return {
        "timestamp": "",
        "level":     fallback_level,
        "source":    "raw",
        "message":   line.strip(),
        "extra":     None,
    }


def _read_and_parse(
    path: Path,
    search: Optional[str],
    level: Optional[str],
    page: int,
    page_size: int,
    is_csv: bool = False,
) -> tuple[list[dict], int]:
    """Read log file, parse lines, filter, paginate. Returns (entries, total)."""
    if not path.exists():
        return [], 0
    try:
        text  = path.read_text(errors="replace")
        lines = [l for l in text.splitlines() if l.strip()]

        # Skip CSV header
        if is_csv and lines and lines[0].startswith("ticket,"):
            lines = lines[1:]

        # Parse
        entries = [_parse_line(l, fallback_level="TRADE" if is_csv else "INFO") for l in lines]

        # Filter by level
        if level:
            upper = level.upper()
            entries = [e for e in entries if e["level"] == upper]

        # Filter by search
        if search:
            low = search.lower()
            entries = [e for e in entries if low in e["message"].lower()
                                             or low in e["logger"].lower()]

        # Reverse so newest first
        entries = list(reversed(entries))

        total  = len(entries)
        offset = (page - 1) * page_size
        page_entries = entries[offset: offset + page_size]
        return page_entries, total
    except Exception as exc:
        logger.warning("Failed to read log %s: %s", path, exc)
        return [], 0


def _read_log_lines(path: Path, tail: int = 50) -> list[str]:
    """Return the last `tail` lines from a file."""
    try:
        text = path.read_text(errors="replace")
        lines = [l for l in text.splitlines() if l.strip()]
        return lines[-tail:]
    except Exception:
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
    "",
    summary="Fetch parsed log entries (iOS-compatible)",
)
async def get_logs_query(
    type:      str           = Query("bot", description="Log type: bot | api | trades | strategy | learning | error"),
    level:     Optional[str] = Query(None,  description="Filter by level: INFO | WARNING | ERROR | CRITICAL"),
    search:    Optional[str] = Query(None,  description="Case-insensitive substring filter"),
    page:      int           = Query(1,     ge=1),
    page_size: int           = Query(50,    ge=1, le=500),
    _user=Depends(get_current_user),
) -> dict:
    """iOS-compatible endpoint: GET /logs?type=bot&page=1&page_size=50"""
    path     = _get_log_path(type)
    is_csv   = path.suffix == ".csv"
    entries, total = _read_and_parse(path, search=search, level=level,
                                      page=page, page_size=page_size, is_csv=is_csv)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "logs":       entries,
        "total":      total,
        "page":       page,
        "page_size":  page_size,
        "total_pages": total_pages,
    }


@router.get(
    "/{log_type}",
    summary="Fetch parsed log entries by path param",
)
async def get_logs_path(
    log_type:  str,
    level:     Optional[str] = Query(None),
    search:    Optional[str] = Query(None),
    page:      int           = Query(1,  ge=1),
    page_size: int           = Query(50, ge=1, le=500),
    _user=Depends(get_current_user),
) -> dict:
    path     = _get_log_path(log_type)
    is_csv   = path.suffix == ".csv"
    entries, total = _read_and_parse(path, search=search, level=level,
                                      page=page, page_size=page_size, is_csv=is_csv)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "logs":       entries,
        "total":      total,
        "page":       page,
        "page_size":  page_size,
        "total_pages": total_pages,
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
