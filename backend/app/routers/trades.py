"""
routers/trades.py
──────────────────
Trade management endpoints — iOS-compatible.

GET  /trades/open                      — list active open trades as [TradeRecord]
GET  /trades/history                   — paginated history (page/page_size params)
GET  /trades/{ticket}                  — single trade detail
POST /trades/{ticket}/close            — close full position
POST /trades/{ticket}/close-partial    — close partial position (?percent=0.5)
PATCH /trades/{ticket}/modify          — modify SL / TP
GET  /trades/{ticket}/explain          — AI narrative for a completed trade
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.security import get_current_user, require_operator
from app.services.bot_service import bot_service, _normalize_trade

logger = logging.getLogger(__name__)
router = APIRouter()


# ── DB-trade normalizer ────────────────────────────────────────────────────────

def _normalize_db_trade(t: dict) -> dict:
    """Map raw SQLite trade row to iOS TradeRecord CodingKeys."""
    direction = str(t.get("direction", t.get("type", "BUY"))).upper()
    if direction not in ("BUY", "SELL"):
        direction = "BUY"
    return {
        "ticket":         int(t.get("trade_id", t.get("ticket", 0))),
        "symbol":         str(t.get("symbol", "XAUUSD")),
        "direction":      direction,
        "lots":           float(t.get("lots", t.get("volume", 0.0))),
        "open_price":     float(t.get("open_price", t.get("price_open", 0.0))),
        "current_price":  None,
        "stop_loss":      t.get("sl"),
        "take_profit":    t.get("tp"),
        "open_time":      str(t.get("open_time", "")),
        "close_time":     t.get("close_time"),
        "close_price":    t.get("close_price"),
        "pnl":            float(t.get("pnl", 0.0)),
        "pips":           t.get("pips"),
        "commission":     float(t.get("commission", 0.0)),
        "swap":           float(t.get("swap", 0.0)),
        "session":        t.get("session"),
        "regime":         t.get("regime"),
        "confidence":     t.get("confidence"),
        "trigger_type":   t.get("trigger_type"),
        "sweep_detected": t.get("sweep_detected"),
        "zone_quality":   t.get("zone_quality"),
        "rr":             t.get("pnl_r", t.get("rr")),
        "status":         "closed",
        "ai_explanation": None,
    }


def _action_ok(trade_id: int, msg: str) -> dict:
    return {"success": True, "message": msg, "data": None}


def _action_fail(msg: str) -> dict:
    return {"success": False, "message": msg, "data": None}


# ── iOS request schemas ────────────────────────────────────────────────────────

class ModifyTradeRequest(BaseModel):
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/open", summary="List currently open trades")
async def list_open_trades(_user=Depends(get_current_user)) -> list:
    """Returns a plain [TradeRecord] array as iOS expects."""
    trades = bot_service.get_open_trades()
    return [_normalize_trade(t) for t in trades]


@router.get("/history", summary="Paginated trade history")
async def trade_history(
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(25, ge=1, le=500),
    outcome:    Optional[str] = Query(None, description="WIN | LOSS | BE"),
    session:    Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    _user=Depends(get_current_user),
) -> dict:
    offset = (page - 1) * page_size
    trades = bot_service.get_trade_history(
        limit=page_size, offset=offset,
        outcome=outcome, session=session,
        start_date=start_date, end_date=end_date,
    )
    total = bot_service.count_trades_filtered(
        outcome=outcome, session=session,
        start_date=start_date, end_date=end_date,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    wins      = sum(1 for t in trades if str(t.get("outcome", "")).upper() == "WIN")
    win_rate  = round(wins / len(trades), 4) if trades else 0.0
    total_pnl = round(sum(float(t.get("pnl", 0.0)) for t in trades), 2)
    return {
        "trades":      [_normalize_db_trade(t) for t in trades],
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
        "win_rate":    win_rate,
        "total_pnl":   total_pnl,
    }


@router.get("/{ticket}", summary="Single trade detail")
async def trade_detail(ticket: int, _user=Depends(get_current_user)) -> dict:
    trade = bot_service.get_trade_by_id(ticket)
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Trade {ticket} not found")
    return _normalize_db_trade(trade)


@router.post("/{ticket}/close", summary="Close a trade (full)")
async def close_trade(ticket: int, _user=Depends(require_operator)) -> dict:
    result = bot_service.close_trade(ticket, partial=False, pct=1.0)
    if result["ok"]:
        return _action_ok(ticket, f"Close request queued for trade #{ticket}")
    return _action_fail("Failed to queue close request")


@router.post("/{ticket}/close-partial", summary="Partially close a trade")
async def close_trade_partial(
    ticket:  int,
    percent: float = Query(0.5, ge=0.01, le=0.99),
    _user=Depends(require_operator),
) -> dict:
    result = bot_service.close_trade(ticket, partial=True, pct=percent)
    if result["ok"]:
        return _action_ok(ticket, f"Partial close ({percent*100:.0f}%) queued for #{ticket}")
    return _action_fail("Failed to queue partial close")


@router.patch("/{ticket}/modify", summary="Modify SL/TP")
async def modify_trade(
    ticket: int,
    req:    ModifyTradeRequest,
    _user=Depends(require_operator),
) -> dict:
    if req.stop_loss is None and req.take_profit is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Provide stop_loss or take_profit")
    result = bot_service.modify_trade(ticket, sl=req.stop_loss, tp=req.take_profit)
    if result["ok"]:
        return _action_ok(ticket, f"Modify request queued for trade #{ticket}")
    return _action_fail("Failed to queue modify request")


@router.get("/{ticket}/explain", summary="AI explanation for a completed trade")
async def explain_trade(ticket: int, _user=Depends(get_current_user)) -> dict:
    return bot_service.get_trade_ai_explanation(ticket)
