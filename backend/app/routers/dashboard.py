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

@router.get("/snapshot", response_model=AccountSnapshot, summary="Full dashboard snapshot")
async def get_dashboard_snapshot(
    _current_user=Depends(get_current_user),
) -> AccountSnapshot:
    """
    Returns a comprehensive snapshot of the bot's current state.
    Safe to poll at high frequency; bot_service reads from cached files.
    """
    return await bot_service.get_dashboard_snapshot()
