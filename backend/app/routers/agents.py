"""
agents.py — FastAPI router for the multi-agent trading system.

Endpoints:
  GET  /agents/status                        — all agents' state
  GET  /agents/{agent_id}/status             — single agent state
  GET  /agents/{agent_id}/metrics            — extended metrics
  POST /agents/{agent_id}/pause              — send pause command
  POST /agents/{agent_id}/resume             — send resume command
  POST /agents/{agent_id}/restart            — send restart command
  POST /agents/{agent_id}/stop               — send stop command

  GET  /agents/strategies/candidates         — list strategy candidates
  GET  /agents/strategies/validated          — validated strategies
  POST /agents/strategies/{genome_hash}/promote — promote to live
  POST /agents/strategies/{genome_hash}/reject  — reject a strategy

  GET  /agents/intelligence/latest           — latest market intel
  GET  /agents/intelligence/history          — last N intel snapshots

  GET  /agents/decisions/recent              — recent trade decisions
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

# ── Repo-root path injection ──────────────────────────────────────────────────
# backend/app/routers/ → backend/app/ → backend/ → repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from agents.shared_db import (
    connect,
    get_all_agent_states,
    get_agent_state,
    get_strategy_candidates,
    get_latest_market_intel,
    get_recent_trade_decisions,
    promote_strategy,
    upsert_strategy_candidate,
)
from agents.message_bus import (
    publish,
    CH_SYSTEM,
    EV_AGENT_PAUSE,
    EV_AGENT_RESUME,
    EV_AGENT_STOP,
    EV_AGENT_RESTART,
)
from app.auth.security import require_auth
from app.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────────────────


class AgentStatusResponse(BaseModel):
    agent_id: str
    status: str
    current_task: str
    last_heartbeat: float
    uptime_seconds: float
    metrics: dict[str, Any]


class StrategyCandidate(BaseModel):
    id: int
    genome_hash: str
    status: str
    fitness: dict[str, Any]
    generation: int
    created_at: float
    notes: str


class MarketIntelResponse(BaseModel):
    timestamp: float
    regime: str
    trend: str
    risk_score: float
    confidence: float
    technical: dict[str, Any]
    fundamental: dict[str, Any]
    session: str


class TradeDecisionResponse(BaseModel):
    id: int
    timestamp: float
    decision: str
    reason: str
    trade_id: Optional[str]
    explanation: dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/agents", tags=["Agents"])

VALID_AGENTS = {"agent1", "agent2", "agent3"}

# ── DB path helper ────────────────────────────────────────────────────────────


def _db_path() -> Path:
    return settings.bot_root / "data" / "agents.db"


def _open_db():
    """Open agents.db and return a connection; raise 503 on failure."""
    db = _db_path()
    try:
        conn = connect(db)
        return conn
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Agents database unavailable: {exc}",
        )


# ── Shared validation ─────────────────────────────────────────────────────────


def _validate_agent(agent_id: str) -> str:
    if agent_id not in VALID_AGENTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent_id}'. Valid values: {sorted(VALID_AGENTS)}",
        )
    return agent_id


def _row_to_status(row: dict) -> AgentStatusResponse:
    now = time.time()
    uptime_start = row.get("uptime_start") or 0.0
    uptime = now - uptime_start if uptime_start else 0.0
    return AgentStatusResponse(
        agent_id=row["agent_id"],
        status=row["status"],
        current_task=row.get("current_task", ""),
        last_heartbeat=row.get("last_heartbeat", 0.0),
        uptime_seconds=round(uptime, 1),
        metrics=row.get("metrics", {}),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agent status endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/status", response_model=dict[str, AgentStatusResponse])
async def all_agents_status(_user=Depends(require_auth)):
    """Return live state for all three agents, keyed by agent_id."""
    conn = _open_db()
    try:
        rows = get_all_agent_states(conn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    # Include placeholder rows for agents that haven't written a heartbeat yet
    result: dict[str, AgentStatusResponse] = {}
    seen = {r["agent_id"] for r in rows}
    for row in rows:
        result[row["agent_id"]] = _row_to_status(row)
    for agent_id in VALID_AGENTS - seen:
        result[agent_id] = AgentStatusResponse(
            agent_id=agent_id,
            status="stopped",
            current_task="",
            last_heartbeat=0.0,
            uptime_seconds=0.0,
            metrics={},
        )
    return result


@router.get("/{agent_id}/status", response_model=AgentStatusResponse)
async def single_agent_status(
    agent_id: str,
    _user=Depends(require_auth),
):
    """Return live state for a single agent."""
    _validate_agent(agent_id)
    conn = _open_db()
    try:
        row = get_agent_state(conn, agent_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    if row is None:
        return AgentStatusResponse(
            agent_id=agent_id,
            status="stopped",
            current_task="",
            last_heartbeat=0.0,
            uptime_seconds=0.0,
            metrics={},
        )
    return _row_to_status(row)


@router.get("/{agent_id}/metrics")
async def agent_metrics(
    agent_id: str,
    _user=Depends(require_auth),
) -> dict[str, Any]:
    """Return the full metrics dict for a single agent."""
    _validate_agent(agent_id)
    conn = _open_db()
    try:
        row = get_agent_state(conn, agent_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No state found for {agent_id}")

    now = time.time()
    uptime_start = row.get("uptime_start") or 0.0
    seconds_since_heartbeat = now - (row.get("last_heartbeat") or 0.0)

    return {
        "agent_id": agent_id,
        "status": row["status"],
        "current_task": row.get("current_task", ""),
        "last_heartbeat": row.get("last_heartbeat", 0.0),
        "seconds_since_heartbeat": round(seconds_since_heartbeat, 1),
        "uptime_seconds": round(now - uptime_start, 1) if uptime_start else 0.0,
        "metrics": row.get("metrics", {}),
        "updated_at": row.get("updated_at", 0.0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent control commands
# ─────────────────────────────────────────────────────────────────────────────


def _send_control(agent_id: str, event_type: str) -> str:
    """Publish a control event to the system channel; return event ID."""
    db = _db_path()
    try:
        event_id = publish(
            CH_SYSTEM,
            event_type,
            {"target_agent": agent_id},
            published_by="api",
            db_path=db,
            ttl_seconds=300,
        )
        return event_id
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to publish control event: {exc}",
        )


@router.post("/{agent_id}/pause")
async def pause_agent(
    agent_id: str,
    _user=Depends(require_auth),
) -> dict[str, str]:
    _validate_agent(agent_id)
    event_id = _send_control(agent_id, EV_AGENT_PAUSE)
    return {"status": "ok", "command": "pause", "agent_id": agent_id, "event_id": event_id}


@router.post("/{agent_id}/resume")
async def resume_agent(
    agent_id: str,
    _user=Depends(require_auth),
) -> dict[str, str]:
    _validate_agent(agent_id)
    event_id = _send_control(agent_id, EV_AGENT_RESUME)
    return {"status": "ok", "command": "resume", "agent_id": agent_id, "event_id": event_id}


@router.post("/{agent_id}/stop")
async def stop_agent(
    agent_id: str,
    _user=Depends(require_auth),
) -> dict[str, str]:
    _validate_agent(agent_id)
    event_id = _send_control(agent_id, EV_AGENT_STOP)
    return {"status": "ok", "command": "stop", "agent_id": agent_id, "event_id": event_id}


@router.post("/{agent_id}/restart")
async def restart_agent(
    agent_id: str,
    _user=Depends(require_auth),
) -> dict[str, Any]:
    """Send AGENT_RESTART event on the bus, then attempt a systemctl restart."""
    _validate_agent(agent_id)
    event_id = _send_control(agent_id, EV_AGENT_RESTART)

    systemctl_result: dict[str, Any] = {"attempted": False}
    service_name = f"xaubot-{agent_id}"
    try:
        result = subprocess.run(
            ["systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            timeout=15,
        )
        systemctl_result = {
            "attempted": True,
            "service": service_name,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        # systemctl not available (dev environment)
        systemctl_result = {
            "attempted": False,
            "reason": "systemctl not available — event published only",
        }
    except subprocess.TimeoutExpired:
        systemctl_result = {
            "attempted": True,
            "service": service_name,
            "returncode": -1,
            "reason": "systemctl timed out",
        }
    except Exception as exc:
        systemctl_result = {
            "attempted": True,
            "service": service_name,
            "returncode": -1,
            "reason": str(exc),
        }

    return {
        "status": "ok",
        "command": "restart",
        "agent_id": agent_id,
        "event_id": event_id,
        "systemctl": systemctl_result,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Strategy candidate endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/strategies/candidates", response_model=list[StrategyCandidate])
async def list_strategy_candidates(
    status: Optional[str] = Query(None, description="Filter by status (pending, validating, validated, rejected, shadow, promoted)"),
    limit: int = Query(50, ge=1, le=200),
    _user=Depends(require_auth),
):
    """List strategy candidates produced by Agent 1."""
    conn = _open_db()
    try:
        rows = get_strategy_candidates(conn, status=status, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    return [
        StrategyCandidate(
            id=r["id"],
            genome_hash=r["genome_hash"],
            status=r["status"],
            fitness=r["fitness"],
            generation=r["generation"],
            created_at=r["created_at"],
            notes=r.get("notes", ""),
        )
        for r in rows
    ]


@router.get("/strategies/validated", response_model=list[StrategyCandidate])
async def list_validated_strategies(
    limit: int = Query(50, ge=1, le=200),
    _user=Depends(require_auth),
):
    """List strategies with status 'validated' — ready for human review."""
    conn = _open_db()
    try:
        rows = get_strategy_candidates(conn, status="validated", limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    return [
        StrategyCandidate(
            id=r["id"],
            genome_hash=r["genome_hash"],
            status=r["status"],
            fitness=r["fitness"],
            generation=r["generation"],
            created_at=r["created_at"],
            notes=r.get("notes", ""),
        )
        for r in rows
    ]


@router.post("/strategies/{genome_hash}/promote")
async def promote_strategy_endpoint(
    genome_hash: str,
    _user=Depends(require_auth),
) -> dict[str, str]:
    """Promote a validated strategy to live trading."""
    conn = _open_db()
    try:
        # Verify it exists first
        rows = get_strategy_candidates(conn, limit=1)
        # Check specifically for this genome_hash
        row = conn.execute(
            "SELECT id, status FROM strategy_candidates WHERE genome_hash = ?",
            (genome_hash,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Strategy '{genome_hash}' not found")
        promote_strategy(conn, genome_hash)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    return {"status": "ok", "genome_hash": genome_hash, "new_status": "promoted"}


@router.post("/strategies/{genome_hash}/reject")
async def reject_strategy_endpoint(
    genome_hash: str,
    _user=Depends(require_auth),
) -> dict[str, str]:
    """Reject a strategy candidate."""
    conn = _open_db()
    try:
        row = conn.execute(
            "SELECT id, genome, status, fitness, generation FROM strategy_candidates WHERE genome_hash = ?",
            (genome_hash,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Strategy '{genome_hash}' not found")
        import json as _json
        upsert_strategy_candidate(
            conn,
            genome_hash,
            _json.loads(row["genome"]),
            status="rejected",
            fitness=_json.loads(row["fitness"]),
            generation=row["generation"],
            notes="Rejected via API",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    return {"status": "ok", "genome_hash": genome_hash, "new_status": "rejected"}


# ─────────────────────────────────────────────────────────────────────────────
# Market intelligence endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/intelligence/latest", response_model=MarketIntelResponse)
async def latest_market_intel(_user=Depends(require_auth)):
    """Return the most recent market intelligence snapshot from Agent 2."""
    conn = _open_db()
    try:
        row = get_latest_market_intel(conn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="No market intelligence available yet")

    return MarketIntelResponse(
        timestamp=row["timestamp"],
        regime=row["regime"],
        trend=row["trend"],
        risk_score=row["risk_score"],
        confidence=row["confidence"],
        technical=row["technical"],
        fundamental=row["fundamental"],
        session=row.get("session", ""),
    )


@router.get("/intelligence/history", response_model=list[MarketIntelResponse])
async def market_intel_history(
    limit: int = Query(20, ge=1, le=100),
    _user=Depends(require_auth),
):
    """Return the last N market intelligence snapshots."""
    conn = _open_db()
    try:
        rows = conn.execute(
            "SELECT * FROM market_intel ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    import json as _json
    result = []
    for row in rows:
        d = dict(row)
        result.append(
            MarketIntelResponse(
                timestamp=d["timestamp"],
                regime=d["regime"],
                trend=d["trend"],
                risk_score=d["risk_score"],
                confidence=d["confidence"],
                technical=_json.loads(d["technical"]) if isinstance(d["technical"], str) else d["technical"],
                fundamental=_json.loads(d["fundamental"]) if isinstance(d["fundamental"], str) else d["fundamental"],
                session=d.get("session", ""),
            )
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Trade decision endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/decisions/recent", response_model=list[TradeDecisionResponse])
async def recent_trade_decisions(
    limit: int = Query(20, ge=1, le=100),
    _user=Depends(require_auth),
):
    """Return recent trade decisions made by Agent 3, with full explanations."""
    conn = _open_db()
    try:
        rows = get_recent_trade_decisions(conn, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        conn.close()

    return [
        TradeDecisionResponse(
            id=r["id"],
            timestamp=r["timestamp"],
            decision=r["decision"],
            reason=r["reason"],
            trade_id=r.get("trade_id"),
            explanation=r.get("explanation", {}),
        )
        for r in rows
    ]
