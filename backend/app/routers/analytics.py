"""
routers/analytics.py
─────────────────────
Deep analytics endpoints computed directly from the learning.db trade records.

GET /analytics/equity-curve      — running equity over time
GET /analytics/daily-returns     — per-day PnL aggregate
GET /analytics/monthly-returns   — per-month PnL + win rate
GET /analytics/drawdown          — drawdown series + max drawdown
GET /analytics/summary           — win rate, profit factor, expectancy, Sharpe, etc.
GET /analytics/session           — performance breakdown by trading session
GET /analytics/regime            — performance breakdown by market regime
GET /analytics/distribution      — PnL histogram buckets
GET /analytics/streaks           — longest win/loss streak analysis
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.security import get_current_user
from app.services.bot_service import bot_service, _query_all

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def _sharpe_ratio(returns: list[float]) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    return _safe_div(mean, std)


def _max_drawdown(equity: list[float]) -> tuple[float, float]:
    if not equity:
        return 0.0, 0.0
    peak = equity[0]
    max_dd = 0.0
    for eq in equity:
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2), round(_safe_div(max_dd, peak) * 100, 4) if peak else 0.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/equity-curve", summary="Running equity curve from all trades")
async def equity_curve(_user=Depends(get_current_user)) -> dict:
    curve = bot_service.get_equity_curve()
    return {"data": curve, "count": len(curve)}


@router.get("/drawdown", summary="Drawdown series and max drawdown statistics")
async def drawdown_series(_user=Depends(get_current_user)) -> dict:
    series = bot_service.get_drawdown_series()
    max_dd = max((p["drawdown_pct"] for p in series), default=0.0)
    return {
        "data": series,
        "max_drawdown_pct": round(max_dd, 4),
        "count": len(series),
    }


@router.get("/daily-returns", summary="Per-day PnL aggregate")
async def daily_returns(
    limit: int = Query(90, ge=1, le=365),
    _user=Depends(get_current_user),
) -> dict:
    rows = _query_all(
        "SELECT date(open_time) AS d, "
        "  SUM(pnl) AS daily_pnl, "
        "  COUNT(*) AS trades, "
        "  SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) AS wins "
        "FROM trades WHERE open_time IS NOT NULL "
        "GROUP BY d ORDER BY d DESC LIMIT ?",
        (limit,),
    )
    for r in rows:
        r["win_rate"] = round(_safe_div(r["wins"], r["trades"]), 4)
        r["daily_pnl"] = round(r["daily_pnl"] or 0.0, 2)
    return {"data": rows, "count": len(rows)}


@router.get("/monthly-returns", summary="Per-month PnL and win rate")
async def monthly_returns(_user=Depends(get_current_user)) -> dict:
    rows = _query_all(
        "SELECT strftime('%Y-%m', open_time) AS month, "
        "  SUM(pnl) AS pnl, "
        "  COUNT(*) AS trades, "
        "  SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) AS wins, "
        "  AVG(pnl_r) AS avg_r, "
        "  SUM(CASE WHEN pnl>0 THEN pnl ELSE 0 END) AS gross_profit, "
        "  ABS(SUM(CASE WHEN pnl<0 THEN pnl ELSE 0 END)) AS gross_loss "
        "FROM trades WHERE open_time IS NOT NULL "
        "GROUP BY month ORDER BY month ASC"
    )
    for r in rows:
        r["win_rate"] = round(_safe_div(r["wins"], r["trades"]), 4)
        r["profit_factor"] = round(_safe_div(r["gross_profit"], r["gross_loss"], 0.0), 3)
        r["pnl"] = round(r["pnl"] or 0.0, 2)
        r["avg_r"] = round(r["avg_r"] or 0.0, 4)
    return {"data": rows, "count": len(rows)}


@router.get("/summary", summary="Full performance statistics")
async def performance_summary(_user=Depends(get_current_user)) -> dict:
    """
    Returns: win rate, profit factor, expectancy (R), Sharpe ratio,
    max drawdown, average trade, average winner/loser, payoff ratio.
    """
    rows = _query_all(
        "SELECT pnl, pnl_r, outcome FROM trades ORDER BY recorded_at ASC"
    )
    if not rows:
        return {"no_data": True, "total_trades": 0}

    total  = len(rows)
    wins   = sum(1 for r in rows if r.get("outcome") == "WIN")
    losses = sum(1 for r in rows if r.get("outcome") == "LOSS")
    be     = total - wins - losses

    pnl_list = [r.get("pnl") or 0.0 for r in rows]
    r_list   = [r.get("pnl_r") or 0.0 for r in rows]

    gross_w = sum(p for p in pnl_list if p > 0)
    gross_l = abs(sum(p for p in pnl_list if p < 0))

    # Build equity list for drawdown calculation
    initial = bot_service.read_config().get("risk", {}).get("initial_capital", 10000.0)
    equity_list: list[float] = []
    eq = initial
    for p in pnl_list:
        eq += p
        equity_list.append(eq)

    max_dd_abs, max_dd_pct = _max_drawdown(equity_list)

    avg_win_trade  = _safe_div(gross_w, wins)
    avg_loss_trade = _safe_div(gross_l, losses)
    expectancy_r   = sum(r_list) / total if total else 0.0
    sharpe         = _sharpe_ratio(pnl_list)

    return {
        "total_trades":    total,
        "winning_trades":  wins,
        "losing_trades":   losses,
        "breakeven_trades": be,
        "win_rate":        round(_safe_div(wins, total), 4),
        "loss_rate":       round(_safe_div(losses, total), 4),
        "profit_factor":   round(_safe_div(gross_w, gross_l, 0.0), 3),
        "expectancy_r":    round(expectancy_r, 4),
        "avg_trade_pnl":   round(sum(pnl_list) / total, 2),
        "avg_winner_pnl":  round(avg_win_trade, 2),
        "avg_loser_pnl":   round(avg_loss_trade, 2),
        "payoff_ratio":    round(_safe_div(avg_win_trade, avg_loss_trade), 3),
        "sharpe_ratio":    round(sharpe, 4),
        "max_drawdown_usd": max_dd_abs,
        "max_drawdown_pct": max_dd_pct,
        "total_pnl":       round(sum(pnl_list), 2),
        "gross_profit":    round(gross_w, 2),
        "gross_loss":      round(gross_l, 2),
        "final_equity":    round(equity_list[-1], 2) if equity_list else initial,
        "return_pct":      round(_safe_div(sum(pnl_list), initial) * 100, 4),
    }


@router.get("/session", summary="Performance breakdown by trading session")
async def session_analysis(_user=Depends(get_current_user)) -> dict:
    rows = _query_all(
        "SELECT session, "
        "  COUNT(*) AS trades, "
        "  SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) AS wins, "
        "  SUM(pnl) AS total_pnl, "
        "  AVG(pnl_r) AS avg_r, "
        "  SUM(CASE WHEN pnl>0 THEN pnl ELSE 0 END) AS gross_profit, "
        "  ABS(SUM(CASE WHEN pnl<0 THEN pnl ELSE 0 END)) AS gross_loss "
        "FROM trades WHERE session IS NOT NULL "
        "GROUP BY session ORDER BY total_pnl DESC"
    )
    for r in rows:
        r["win_rate"] = round(_safe_div(r["wins"], r["trades"]), 4)
        r["profit_factor"] = round(_safe_div(r["gross_profit"], r["gross_loss"], 0.0), 3)
        r["avg_r"] = round(r["avg_r"] or 0.0, 4)
        r["total_pnl"] = round(r["total_pnl"] or 0.0, 2)
    return {"data": rows, "count": len(rows)}


@router.get("/regime", summary="Performance breakdown by market regime")
async def regime_analysis(_user=Depends(get_current_user)) -> dict:
    rows = _query_all(
        "SELECT f.regime, "
        "  COUNT(t.id) AS trades, "
        "  SUM(CASE WHEN t.outcome='WIN' THEN 1 ELSE 0 END) AS wins, "
        "  SUM(t.pnl) AS total_pnl, "
        "  AVG(t.pnl_r) AS avg_r, "
        "  SUM(CASE WHEN t.pnl>0 THEN t.pnl ELSE 0 END) AS gross_profit, "
        "  ABS(SUM(CASE WHEN t.pnl<0 THEN t.pnl ELSE 0 END)) AS gross_loss "
        "FROM trades t "
        "JOIN trade_features f ON t.trade_id = f.trade_id "
        "WHERE f.regime IS NOT NULL "
        "GROUP BY f.regime ORDER BY total_pnl DESC"
    )
    for r in rows:
        r["win_rate"] = round(_safe_div(r["wins"], r["trades"]), 4)
        r["profit_factor"] = round(_safe_div(r["gross_profit"], r["gross_loss"], 0.0), 3)
        r["avg_r"] = round(r["avg_r"] or 0.0, 4)
        r["total_pnl"] = round(r["total_pnl"] or 0.0, 2)
    return {"data": rows, "count": len(rows)}


@router.get("/distribution", summary="Trade PnL distribution histogram")
async def pnl_distribution(
    bins: int = Query(20, ge=5, le=100),
    _user=Depends(get_current_user),
) -> dict:
    """Returns histogram bucket counts for iOS chart rendering."""
    rows = _query_all(
        "SELECT pnl FROM trades WHERE pnl IS NOT NULL ORDER BY pnl ASC"
    )
    if not rows:
        return {"buckets": [], "bins": bins, "total_trades": 0}

    values = [r["pnl"] for r in rows]
    min_val = min(values)
    max_val = max(values)

    if min_val == max_val:
        return {
            "buckets": [{"bin_index": 0, "lo": min_val, "hi": max_val,
                         "count": len(values), "label": f"{min_val:.2f}"}],
            "bins": 1,
            "total_trades": len(values),
        }

    width = (max_val - min_val) / bins
    buckets: list[dict] = []
    for i in range(bins):
        lo = min_val + i * width
        hi = lo + width
        count = sum(1 for v in values if lo <= v < hi)
        buckets.append({
            "bin_index": i,
            "lo": round(lo, 2),
            "hi": round(hi, 2),
            "count": count,
            "label": f"{lo:.1f}–{hi:.1f}",
            "is_profit": lo >= 0,
        })
    # Last bucket includes the max value
    if buckets:
        buckets[-1]["count"] += sum(1 for v in values if v == max_val)

    return {"buckets": buckets, "bins": bins, "total_trades": len(values)}


@router.get("/streaks", summary="Win/loss streak analysis")
async def streak_analysis(_user=Depends(get_current_user)) -> dict:
    rows = _query_all(
        "SELECT outcome FROM trades ORDER BY recorded_at ASC"
    )
    if not rows:
        return {"total_trades": 0}

    outcomes = [r["outcome"] for r in rows]
    max_win_streak = max_loss_streak = 0
    cur_win = cur_loss = 0

    for o in outcomes:
        if o == "WIN":
            cur_win += 1
            cur_loss = 0
        elif o == "LOSS":
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = cur_loss = 0
        max_win_streak  = max(max_win_streak, cur_win)
        max_loss_streak = max(max_loss_streak, cur_loss)

    # Current streak from the end
    cur_type = outcomes[-1] if outcomes else None
    streak = 0
    for o in reversed(outcomes):
        if o == cur_type:
            streak += 1
        else:
            break

    return {
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "current_streak_type": cur_type,
        "current_streak_length": streak,
        "total_trades": len(outcomes),
    }
