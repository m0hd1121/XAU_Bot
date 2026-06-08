"""
routers/learning.py
────────────────────
Self-learning engine stats and inspection endpoints.

GET /learning/stats               — trade count, pattern count, enabled status
GET /learning/patterns            — significant pattern stats (filterable)
GET /learning/patterns/{key}      — single pattern stats + recent trades
GET /learning/regime-history      — recent regime timeline
GET /learning/validation-results  — walk-forward / OOS validation results
GET /learning/confidence-weights  — top confidence weight adjustments
GET /learning/events              — recent learning event log
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.security import get_current_user
from app.services.bot_service import bot_service, _query_all, _query_one

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stats", summary="Learning engine overview stats")
async def learning_stats(_user=Depends(get_current_user)) -> dict:
    """Returns trade count, significant pattern count, last validation result."""
    return bot_service.get_learning_stats()


@router.get("/patterns", summary="Pattern statistics (significant trades only by default)")
async def patterns(
    min_samples: int = Query(10, ge=0, description="Minimum sample count"),
    min_abs_r:   float = Query(0.0, ge=0.0, description="Minimum absolute expectancy_r"),
    limit:       int = Query(100, ge=1, le=500),
    _user=Depends(get_current_user),
) -> dict:
    rows = _query_all(
        "SELECT * FROM pattern_stats "
        "WHERE sample_count >= ? AND abs(expectancy_r) >= ? "
        "ORDER BY abs(expectancy_r) DESC LIMIT ?",
        (min_samples, min_abs_r, limit),
    )
    return {"patterns": rows, "count": len(rows)}


@router.get("/patterns/{pattern_key}", summary="Single pattern stats with recent trade outcomes")
async def pattern_detail(
    pattern_key: str,
    _user=Depends(get_current_user),
) -> dict:
    stats_rows = _query_all(
        "SELECT * FROM pattern_stats WHERE pattern_key = ?", (pattern_key,)
    )
    if not stats_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern '{pattern_key}' not found",
        )
    recent_trades = _query_all(
        "SELECT t.outcome, t.pnl_r, t.pnl, t.session, t.quality_score, t.open_time "
        "FROM trades t "
        "JOIN trade_features f ON t.trade_id = f.trade_id "
        "WHERE f.pattern_key = ? "
        "ORDER BY t.recorded_at DESC LIMIT 50",
        (pattern_key,),
    )
    return {
        "stats": stats_rows[0],
        "recent_trades": recent_trades,
        "recent_trade_count": len(recent_trades),
    }


@router.get("/regime-history", summary="Market regime timeline")
async def regime_history(
    limit: int = Query(200, ge=1, le=1000),
    _user=Depends(get_current_user),
) -> dict:
    rows = bot_service.get_regime_history(limit=limit)
    return {"data": rows, "count": len(rows)}


@router.get("/validation-results", summary="Walk-forward and OOS validation results")
async def validation_results(
    limit: int = Query(20, ge=1, le=200),
    _user=Depends(get_current_user),
) -> dict:
    rows = bot_service.get_validation_results(limit=limit)
    return {"data": rows, "count": len(rows)}


@router.get("/confidence-weights", summary="Top confidence weight adjustments by feature")
async def confidence_weights(
    limit: int = Query(50, ge=1, le=500),
    _user=Depends(get_current_user),
) -> dict:
    rows = _query_all(
        "SELECT feature_name, feature_value, regime, weight, sample_count, last_updated "
        "FROM confidence_weights ORDER BY sample_count DESC, ABS(weight - 0.5) DESC LIMIT ?",
        (limit,),
    )
    return {"data": rows, "count": len(rows)}


@router.get("/events", summary="Recent learning engine events")
async def learning_events(
    limit: int = Query(50, ge=1, le=500),
    _user=Depends(get_current_user),
) -> dict:
    rows = bot_service.get_learning_events(limit=limit)
    return {"data": rows, "count": len(rows)}


@router.get("/confidence-evolution", summary="How confidence evolved over trades")
async def confidence_evolution(
    limit: int = Query(200, ge=10, le=2000),
    _user=Depends(get_current_user),
) -> dict:
    """
    Returns the initial_confidence field from each trade in chronological order,
    allowing the iOS app to plot how the model's confidence has evolved.
    """
    rows = _query_all(
        "SELECT trade_id, open_time, outcome, initial_confidence, pnl_r "
        "FROM trades WHERE initial_confidence IS NOT NULL "
        "ORDER BY recorded_at ASC LIMIT ?",
        (limit,),
    )
    return {"data": rows, "count": len(rows)}
