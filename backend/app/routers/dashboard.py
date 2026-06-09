"""
routers/dashboard.py
─────────────────────
Real-time account snapshot endpoint consumed by the iOS home screen.

GET /dashboard/snapshot  — full dashboard payload:
  • Account balance, equity, margin used / free
  • Daily / weekly / monthly PnL (absolute + percentage)
  • Open trades count
  • Bot operational status (running, paused, mode, PID, uptime)
  • Learning engine status + trade count
  • Broker connectivity
  • Last sync timestamp
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.security import get_current_user
from app.services.bot_service import bot_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response schema (shared with WebSocket worker) ────────────────────────────

class AccountSnapshot(BaseModel):
    # Account financials
    balance: float
    equity: float
    margin_used: float
    margin_free: float
    margin_level_pct: Optional[float] = None

    # PnL
    daily_pnl: float
    daily_pnl_pct: float
    weekly_pnl: float
    weekly_pnl_pct: float
    monthly_pnl: float
    monthly_pnl_pct: float
    total_pnl: float

    # Trades
    open_trades_count: int
    pending_orders_count: int
    total_trades_all_time: int
    win_rate_recent: Optional[float] = None

    # Bot status
    bot_running: bool
    bot_paused: bool
    bot_mode: str
    bot_pid: Optional[int] = None
    bot_uptime_seconds: Optional[int] = None
    emergency_stopped: bool
    maintenance_mode: bool

    # Learning
    learning_enabled: bool
    learning_trade_count: int
    learning_last_analysis: Optional[str] = None

    # Connectivity
    broker_connected: bool
    last_heartbeat: Optional[datetime] = None
    last_trade_time: Optional[datetime] = None
    last_sync_time: datetime
    api_version: str = "1.0.0"


# ── Endpoint ──────────────────────────────────────────────────────────────────

_SAFE_STATUS = {
    "running": False, "paused": False, "maintenance_mode": False,
    "emergency_stopped": False, "learning_enabled": False,
    "pid": None, "mode": "backtest",
    "last_heartbeat": None, "last_trade_at": None,
    "open_trades_count": 0, "daily_pnl": 0.0, "equity": 0.0,
}


@router.get("/bot-status", summary="Bot status for control panel")
async def get_bot_status(
    _current_user=Depends(get_current_user),
) -> dict:
    """Returns the BotStatus payload consumed by the iOS Bot Control screen."""
    from datetime import timezone
    import asyncio

    now = datetime.now(tz=timezone.utc).isoformat()

    # Wrap everything — any exception returns a safe default so the iOS
    # screen loads instead of hanging on a 500.
    try:
        s = await asyncio.wait_for(bot_service.get_bot_status(), timeout=5.0)
    except Exception:
        s = {}

    try:
        snap      = bot_service.get_account_snapshot()
        equity    = float(snap.get("equity",    0.0))
        daily_pnl = float(snap.get("daily_pnl", 0.0))
        open_count = len(bot_service.get_open_trades())
    except Exception:
        equity = daily_pnl = 0.0
        open_count = 0

    return {
        **_SAFE_STATUS,
        "running":           bool(s.get("running",           False)),
        "paused":            bool(s.get("paused",            False)),
        "maintenance_mode":  bool(s.get("maintenance_mode",  False)),
        "emergency_stopped": bool(s.get("emergency_stopped", False)),
        "learning_enabled":  bool(s.get("learning_enabled",  False)),
        "pid":               s.get("pid"),
        "mode":              str(s.get("mode", "backtest")),
        "open_trades_count": open_count,
        "daily_pnl":         daily_pnl,
        "equity":            equity,
        "updated_at":        now,
    }


@router.get("/snapshot", response_model=AccountSnapshot, summary="Full dashboard snapshot")
async def get_dashboard_snapshot(
    _current_user=Depends(get_current_user),
) -> AccountSnapshot:
    """
    Returns a comprehensive snapshot of the bot's current state.
    Safe to poll at high frequency; bot_service reads from cached files.
    """
    return await bot_service.get_dashboard_snapshot()
