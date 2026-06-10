"""
message_bus.py — SQLite-backed pub/sub event bus for inter-agent communication.

Design:
  • Agents publish events by inserting rows into the `events` table.
  • Agents poll for new events using the last-seen timestamp (no cursor table
    needed — each agent tracks its own high-water mark in memory).
  • TTL-based expiry keeps the table from growing unbounded.
  • Thread-safe: each call opens its own short-lived connection in WAL mode.

Channel conventions:
  agent1.*    — Strategy Research Agent output
  agent2.*    — Market Intelligence Agent output
  agent3.*    — Live Trader Agent output
  system.*    — Control plane (start/stop/pause)

Event types by channel:
  agent1.strategy  → STRATEGY_CANDIDATE | STRATEGY_PROMOTED | CONFIDENCE_UPDATE
  agent1.research  → BACKTEST_COMPLETE | WALKFORWARD_RESULT | POPULATION_UPDATE
  agent2.market    → REGIME_UPDATE | TECHNICAL_ANALYSIS | FUNDAMENTAL_ALERT | RISK_ALERT
  agent3.trades    → TRADE_EXECUTED | TRADE_CLOSED | TRADE_REJECTED | TRADE_MANAGED
  system.control   → AGENT_PAUSE | AGENT_RESUME | AGENT_STOP | AGENT_RESTART
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .shared_db import connect, get_db_path

# ── Channel / event type constants ────────────────────────────────────────────

# Agent 1 → Agent 3
CH_STRATEGY      = "agent1.strategy"
CH_RESEARCH      = "agent1.research"

# Agent 2 → Agent 3
CH_MARKET        = "agent2.market"

# Agent 3 → Agent 1 (feedback loop)
CH_TRADES        = "agent3.trades"

# Control plane
CH_SYSTEM        = "system.control"

# Event types
EV_STRATEGY_CANDIDATE   = "STRATEGY_CANDIDATE"
EV_STRATEGY_PROMOTED    = "STRATEGY_PROMOTED"
EV_CONFIDENCE_UPDATE    = "CONFIDENCE_UPDATE"
EV_BACKTEST_COMPLETE    = "BACKTEST_COMPLETE"
EV_WALKFORWARD_RESULT   = "WALKFORWARD_RESULT"
EV_POPULATION_UPDATE    = "POPULATION_UPDATE"
EV_REGIME_UPDATE        = "REGIME_UPDATE"
EV_TECHNICAL_ANALYSIS   = "TECHNICAL_ANALYSIS"
EV_FUNDAMENTAL_ALERT    = "FUNDAMENTAL_ALERT"
EV_RISK_ALERT           = "RISK_ALERT"
EV_TRADE_EXECUTED       = "TRADE_EXECUTED"
EV_TRADE_CLOSED         = "TRADE_CLOSED"
EV_TRADE_REJECTED       = "TRADE_REJECTED"
EV_TRADE_MANAGED        = "TRADE_MANAGED"
EV_AGENT_PAUSE          = "AGENT_PAUSE"
EV_AGENT_RESUME         = "AGENT_RESUME"
EV_AGENT_STOP           = "AGENT_STOP"
EV_AGENT_RESTART        = "AGENT_RESTART"


# ─────────────────────────────────────────────────────────────────────────────
# Core API
# ─────────────────────────────────────────────────────────────────────────────

def publish(
    channel: str,
    event_type: str,
    payload: dict[str, Any],
    published_by: str,
    *,
    db_path: Path | str | None = None,
    ttl_seconds: int = 3600,
) -> str:
    """Insert an event into the bus. Returns the new event ID."""
    event_id = str(uuid.uuid4())
    now = time.time()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO events (id, channel, event_type, payload, published_by,
                                published_at, ttl_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, channel, event_type, json.dumps(payload),
             published_by, now, ttl_seconds),
        )
        conn.commit()
    return event_id


def poll(
    channels: list[str],
    since_timestamp: float,
    *,
    db_path: Path | str | None = None,
    limit: int = 100,
    event_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Return events newer than `since_timestamp` on any of the given channels.
    Caller should store the `published_at` of the last returned event as the
    new high-water mark for the next poll.
    """
    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in channels)
        base_sql = (
            f"SELECT * FROM events WHERE channel IN ({placeholders})"
            f" AND published_at > ?"
        )
        params: list[Any] = list(channels) + [since_timestamp]

        if event_types:
            et_ph = ",".join("?" for _ in event_types)
            base_sql += f" AND event_type IN ({et_ph})"
            params.extend(event_types)

        base_sql += " ORDER BY published_at ASC LIMIT ?"
        params.append(limit)

        rows = conn.execute(base_sql, params).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        result.append(d)
    return result


def poll_one_channel(
    channel: str,
    since_timestamp: float,
    *,
    db_path: Path | str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return poll([channel], since_timestamp, db_path=db_path, limit=limit)


def get_latest(
    channel: str,
    event_type: str | None = None,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return the most recent event on a channel, optionally filtered by type."""
    with connect(db_path) as conn:
        if event_type:
            row = conn.execute(
                "SELECT * FROM events WHERE channel=? AND event_type=?"
                " ORDER BY published_at DESC LIMIT 1",
                (channel, event_type),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM events WHERE channel=?"
                " ORDER BY published_at DESC LIMIT 1",
                (channel,),
            ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["payload"] = json.loads(d["payload"])
    return d


def cleanup_expired(
    *,
    db_path: Path | str | None = None,
    max_age_seconds: float | None = None,
) -> int:
    """
    Delete expired events. Uses per-row TTL if max_age_seconds is None.
    Returns count deleted.
    """
    now = time.time()
    with connect(db_path) as conn:
        if max_age_seconds is not None:
            cutoff = now - max_age_seconds
            cur = conn.execute(
                "DELETE FROM events WHERE published_at < ?", (cutoff,)
            )
        else:
            cur = conn.execute(
                "DELETE FROM events WHERE (published_at + ttl_seconds) < ?", (now,)
            )
        conn.commit()
        return cur.rowcount


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrappers for common publish patterns
# ─────────────────────────────────────────────────────────────────────────────

def publish_strategy_candidate(
    genome_hash: str,
    genome: dict,
    fitness: dict,
    generation: int,
    *,
    db_path: Path | str | None = None,
) -> str:
    return publish(
        CH_STRATEGY, EV_STRATEGY_CANDIDATE,
        {"genome_hash": genome_hash, "genome": genome,
         "fitness": fitness, "generation": generation},
        "agent1", db_path=db_path, ttl_seconds=86400,
    )


def publish_strategy_promoted(
    genome_hash: str,
    fitness: dict,
    validation_summary: dict,
    *,
    db_path: Path | str | None = None,
) -> str:
    return publish(
        CH_STRATEGY, EV_STRATEGY_PROMOTED,
        {"genome_hash": genome_hash, "fitness": fitness,
         "validation": validation_summary},
        "agent1", db_path=db_path, ttl_seconds=86400 * 7,
    )


def publish_market_regime(
    regime: str,
    trend: str,
    risk_score: float,
    confidence: float,
    technical_summary: dict,
    fundamental_summary: dict,
    *,
    db_path: Path | str | None = None,
) -> str:
    return publish(
        CH_MARKET, EV_REGIME_UPDATE,
        {
            "regime": regime, "trend": trend,
            "risk_score": risk_score, "confidence": confidence,
            "technical": technical_summary,
            "fundamental": fundamental_summary,
            "timestamp": time.time(),
        },
        "agent2", db_path=db_path, ttl_seconds=600,
    )


def publish_risk_alert(
    alert_type: str,
    message: str,
    severity: str,
    *,
    db_path: Path | str | None = None,
) -> str:
    return publish(
        CH_MARKET, EV_RISK_ALERT,
        {"type": alert_type, "message": message, "severity": severity,
         "timestamp": time.time()},
        "agent2", db_path=db_path, ttl_seconds=1800,
    )


def publish_trade_executed(
    trade_id: str,
    direction: str,
    lots: float,
    entry_price: float,
    sl_price: float,
    tp1_price: float,
    tp2_price: float,
    explanation: dict,
    *,
    db_path: Path | str | None = None,
) -> str:
    return publish(
        CH_TRADES, EV_TRADE_EXECUTED,
        {
            "trade_id": trade_id, "direction": direction,
            "lots": lots, "entry_price": entry_price,
            "sl_price": sl_price, "tp1_price": tp1_price,
            "tp2_price": tp2_price, "explanation": explanation,
            "timestamp": time.time(),
        },
        "agent3", db_path=db_path, ttl_seconds=86400,
    )


def publish_trade_closed(
    trade_id: str,
    pnl: float,
    pnl_r: float,
    close_reason: str,
    outcome: str,
    *,
    db_path: Path | str | None = None,
) -> str:
    return publish(
        CH_TRADES, EV_TRADE_CLOSED,
        {
            "trade_id": trade_id, "pnl": pnl, "pnl_r": pnl_r,
            "close_reason": close_reason, "outcome": outcome,
            "timestamp": time.time(),
        },
        "agent3", db_path=db_path, ttl_seconds=86400,
    )
