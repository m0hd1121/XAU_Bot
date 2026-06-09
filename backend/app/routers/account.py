"""
routers/account.py
───────────────────
Broker / MT5 account management endpoints.

GET  /account/current          — return live account snapshot (balance, equity, etc.)
GET  /account/list             — list saved account IDs
POST /account/add              — save new broker credentials
DELETE /account/{id}           — remove saved account
POST /account/{id}/reconnect   — signal bot to reconnect using saved credentials
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.security import get_current_user, require_admin
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

BOT_ROOT           = settings.bot_root
_ACCOUNT_SNAP_FILE = BOT_ROOT / "data" / "account_snapshot.json"
_ACCOUNTS_FILE     = BOT_ROOT / "data" / "accounts.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_accounts() -> dict:
    if not _ACCOUNTS_FILE.exists():
        return {}
    try:
        return json.loads(_ACCOUNTS_FILE.read_text())
    except Exception:
        return {}


def _write_accounts(data: dict) -> None:
    _ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ACCOUNTS_FILE.write_text(json.dumps(data, indent=2))


def _read_snapshot() -> Optional[dict]:
    if not _ACCOUNT_SNAP_FILE.exists():
        return None
    try:
        return json.loads(_ACCOUNT_SNAP_FILE.read_text())
    except Exception:
        return None


def _snap_to_ios(snap: dict) -> dict:
    """Normalise whatever the bot writes to the AccountInfo fields iOS expects."""
    return {
        "account_number": str(snap.get("account_number", snap.get("login", "—"))),
        "broker":         str(snap.get("broker",  snap.get("company", "Unknown"))),
        "server":         str(snap.get("server",  "—")),
        "currency":       str(snap.get("currency", "USD")),
        "leverage":       int(snap.get("leverage", 100)),
        "balance":        float(snap.get("balance",    0.0)),
        "equity":         float(snap.get("equity",     0.0)),
        "margin":         float(snap.get("margin",     0.0)),
        "free_margin":    float(snap.get("free_margin", snap.get("margin_free", 0.0))),
        "margin_level":   snap.get("margin_level"),
        "connected":      bool(snap.get("connected", True)),
        "latency_ms":     snap.get("latency_ms"),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/current", summary="Current MT5 account snapshot")
async def account_current(_user=Depends(get_current_user)) -> dict:
    """
    Returns the latest account snapshot written by the bot.
    Returns 404 if the bot hasn't connected to MT5 yet.
    """
    snap = _read_snapshot()
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account snapshot available — bot not connected to MT5",
        )
    return _snap_to_ios(snap)


@router.get("/list", summary="List saved broker account IDs")
async def account_list(_user=Depends(get_current_user)) -> dict:
    accounts = _read_accounts()
    return {"accounts": list(accounts.keys()), "count": len(accounts)}


@router.post("/add", summary="Save broker account credentials")
async def add_account(payload: dict, _user=Depends(require_admin)) -> dict:
    """
    Stores broker credentials so the bot can connect to MT5.
    Expected fields: server, login, password
    """
    server   = payload.get("server", "").strip()
    login    = payload.get("login", "").strip()
    password = payload.get("password", "").strip()

    if not server or not login or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fields 'server', 'login', and 'password' are required",
        )

    account_id = f"{login}@{server}"
    accounts = _read_accounts()
    accounts[account_id] = {
        "server":   server,
        "login":    login,
        "password": password,
    }
    _write_accounts(accounts)

    # Write the active account to a file the bot can read on next start
    active_path = BOT_ROOT / "data" / "active_account.json"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps({
        "server": server, "login": login, "password": password
    }))

    logger.info("Account added: %s", account_id)
    return {"ok": True, "message": f"Account {account_id} saved. Restart the bot to connect."}


@router.delete("/{account_id:path}", summary="Remove a saved broker account")
async def delete_account(account_id: str, _user=Depends(require_admin)) -> dict:
    accounts = _read_accounts()
    if account_id not in accounts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    del accounts[account_id]
    _write_accounts(accounts)
    logger.info("Account removed: %s", account_id)
    return {"ok": True, "message": f"Account {account_id} removed"}


@router.post("/{account_id:path}/reconnect", summary="Signal bot to reconnect to this account")
async def reconnect_account(account_id: str, _user=Depends(require_admin)) -> dict:
    accounts = _read_accounts()
    if account_id not in accounts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    creds = accounts[account_id]
    active_path = BOT_ROOT / "data" / "active_account.json"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps(creds))

    # Write a reconnect flag the bot polls
    (BOT_ROOT / ".reconnect").touch()

    logger.info("Reconnect triggered for account: %s", account_id)
    return {"ok": True, "message": f"Reconnecting to {account_id}…"}
