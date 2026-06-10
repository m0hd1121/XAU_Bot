"""
shared_db.py — Shared SQLite database schema and access helpers for the
multi-agent trading system.

All three agents and the backend read/write this database.
Each write is a short, targeted transaction to minimise WAL contention.

Database location: resolved from AGENTS_DB_PATH env var or config.yaml,
defaulting to data/agents.db relative to repo root.

Schema:
  events              — append-only message bus (pub/sub via polling)
  agent_state         — per-agent heartbeat and metrics (upserted)
  strategy_candidates — Agent 1 output: validated strategy genomes
  market_intel        — Agent 2 output: regime + technical + fundamental
  trade_decisions     — Agent 3 decisions with full explainability
  strategy_memory     — Persistent institutional knowledge base
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# DB location helpers
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_DB = Path(__file__).parent.parent / "data" / "agents.db"


def get_db_path(cfg: dict | None = None) -> Path:
    env = os.environ.get("AGENTS_DB_PATH")
    if env:
        return Path(env)
    if cfg:
        p = cfg.get("agents", {}).get("db_path")
        if p:
            return Path(p)
    return _DEFAULT_DB


def connect(db_path: Path | str | None = None, *, timeout: float = 10.0) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
-- Message bus: append-only, polled by agents
CREATE TABLE IF NOT EXISTS events (
    id          TEXT    PRIMARY KEY,
    channel     TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,           -- JSON blob
    published_by TEXT   NOT NULL,
    published_at REAL   NOT NULL,           -- Unix timestamp (time.time())
    ttl_seconds INTEGER NOT NULL DEFAULT 3600
);
CREATE INDEX IF NOT EXISTS idx_events_channel_ts  ON events(channel, published_at);
CREATE INDEX IF NOT EXISTS idx_events_ts           ON events(published_at);

-- Per-agent heartbeat / live status (upserted by each agent)
CREATE TABLE IF NOT EXISTS agent_state (
    agent_id        TEXT    PRIMARY KEY,
    status          TEXT    NOT NULL DEFAULT 'stopped',  -- running|stopped|paused|error
    current_task    TEXT    NOT NULL DEFAULT '',
    last_heartbeat  REAL    NOT NULL DEFAULT 0,
    uptime_start    REAL    NOT NULL DEFAULT 0,
    metrics         TEXT    NOT NULL DEFAULT '{}',       -- JSON: cpu, mem, counts
    updated_at      REAL    NOT NULL DEFAULT 0
);

-- Agent 1 output: strategy genome candidates
CREATE TABLE IF NOT EXISTS strategy_candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    genome_hash     TEXT    UNIQUE NOT NULL,
    genome          TEXT    NOT NULL,                    -- JSON params
    status          TEXT    NOT NULL DEFAULT 'pending',  -- pending|validating|validated|rejected|shadow|promoted
    fitness         TEXT    NOT NULL DEFAULT '{}',       -- JSON: expectancy, pf, sharpe, …
    validation      TEXT    NOT NULL DEFAULT '{}',       -- JSON: per-stage results
    generation      INTEGER NOT NULL DEFAULT 0,
    parent_hashes   TEXT    NOT NULL DEFAULT '[]',       -- JSON array
    created_at      REAL    NOT NULL,
    updated_at      REAL    NOT NULL,
    promoted_at     REAL    DEFAULT NULL,
    notes           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sc_status ON strategy_candidates(status, created_at);

-- Agent 2 output: market intelligence snapshots
CREATE TABLE IF NOT EXISTS market_intel (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       REAL    NOT NULL,
    timeframe       TEXT    NOT NULL DEFAULT '5M',
    regime          TEXT    NOT NULL DEFAULT 'UNKNOWN',
    trend           TEXT    NOT NULL DEFAULT 'UNKNOWN',
    technical       TEXT    NOT NULL DEFAULT '{}',       -- zones, BOS, CHoCH, volatility
    fundamental     TEXT    NOT NULL DEFAULT '{}',       -- upcoming events, impact scores
    risk_score      REAL    NOT NULL DEFAULT 0.5,        -- 0=safe, 1=avoid trading
    confidence      REAL    NOT NULL DEFAULT 0.5,
    session         TEXT    NOT NULL DEFAULT '',
    created_at      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mi_ts ON market_intel(timestamp DESC);

-- Agent 3 output: every trade decision with full explainability
CREATE TABLE IF NOT EXISTS trade_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       REAL    NOT NULL,
    decision        TEXT    NOT NULL,   -- EXECUTE|REJECT|DEFER
    reason          TEXT    NOT NULL,
    trade_id        TEXT    DEFAULT NULL,
    strategy_id     TEXT    DEFAULT NULL,
    intel_id        INTEGER DEFAULT NULL REFERENCES market_intel(id),
    explanation     TEXT    NOT NULL DEFAULT '{}',  -- full narrative JSON
    created_at      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_td_ts ON trade_decisions(timestamp DESC);

-- Persistent institutional knowledge: every test result ever run
CREATE TABLE IF NOT EXISTS strategy_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    genome_hash TEXT    NOT NULL,
    record_type TEXT    NOT NULL,   -- BACKTEST|WALKFORWARD|MONTE_CARLO|OOS|SHADOW|LIVE
    metrics     TEXT    NOT NULL DEFAULT '{}',
    passed      INTEGER NOT NULL DEFAULT 0,   -- 1=pass, 0=fail
    created_at  REAL    NOT NULL,
    notes       TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sm_hash ON strategy_memory(genome_hash, record_type);
"""


def init_schema(db_path: Path | str | None = None) -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Agent state helpers
# ─────────────────────────────────────────────────────────────────────────────

def upsert_agent_state(
    conn: sqlite3.Connection,
    agent_id: str,
    *,
    status: str | None = None,
    current_task: str | None = None,
    metrics: dict | None = None,
    uptime_start: float | None = None,
) -> None:
    now = time.time()
    conn.execute(
        """
        INSERT INTO agent_state (agent_id, status, current_task, last_heartbeat,
                                  uptime_start, metrics, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(agent_id) DO UPDATE SET
            status        = COALESCE(EXCLUDED.status,       agent_state.status),
            current_task  = COALESCE(EXCLUDED.current_task, agent_state.current_task),
            last_heartbeat = EXCLUDED.last_heartbeat,
            uptime_start  = CASE WHEN EXCLUDED.uptime_start > 0
                                 THEN EXCLUDED.uptime_start
                                 ELSE agent_state.uptime_start END,
            metrics       = COALESCE(EXCLUDED.metrics, agent_state.metrics),
            updated_at    = EXCLUDED.updated_at
        """,
        (
            agent_id,
            status or "running",
            current_task or "",
            now,
            uptime_start or 0,
            json.dumps(metrics or {}),
            now,
        ),
    )
    conn.commit()


def get_agent_state(conn: sqlite3.Connection, agent_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM agent_state WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["metrics"] = json.loads(d["metrics"])
    return d


def get_all_agent_states(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM agent_state ORDER BY agent_id").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["metrics"] = json.loads(d["metrics"])
        result.append(d)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Strategy candidate helpers
# ─────────────────────────────────────────────────────────────────────────────

def upsert_strategy_candidate(
    conn: sqlite3.Connection,
    genome_hash: str,
    genome: dict,
    *,
    status: str = "pending",
    fitness: dict | None = None,
    validation: dict | None = None,
    generation: int = 0,
    parent_hashes: list[str] | None = None,
    notes: str = "",
) -> int:
    now = time.time()
    conn.execute(
        """
        INSERT INTO strategy_candidates
            (genome_hash, genome, status, fitness, validation,
             generation, parent_hashes, created_at, updated_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(genome_hash) DO UPDATE SET
            status       = EXCLUDED.status,
            fitness      = EXCLUDED.fitness,
            validation   = EXCLUDED.validation,
            generation   = EXCLUDED.generation,
            updated_at   = EXCLUDED.updated_at,
            notes        = EXCLUDED.notes
        """,
        (
            genome_hash,
            json.dumps(genome),
            status,
            json.dumps(fitness or {}),
            json.dumps(validation or {}),
            generation,
            json.dumps(parent_hashes or []),
            now,
            now,
            notes,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM strategy_candidates WHERE genome_hash = ?", (genome_hash,)
    ).fetchone()
    return row["id"]


def get_strategy_candidates(
    conn: sqlite3.Connection,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT * FROM strategy_candidates WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy_candidates ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["genome"]       = json.loads(d["genome"])
        d["fitness"]      = json.loads(d["fitness"])
        d["validation"]   = json.loads(d["validation"])
        d["parent_hashes"] = json.loads(d["parent_hashes"])
        result.append(d)
    return result


def promote_strategy(conn: sqlite3.Connection, genome_hash: str) -> None:
    now = time.time()
    conn.execute(
        "UPDATE strategy_candidates SET status='promoted', promoted_at=?, updated_at=? WHERE genome_hash=?",
        (now, now, genome_hash),
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Market intelligence helpers
# ─────────────────────────────────────────────────────────────────────────────

def insert_market_intel(
    conn: sqlite3.Connection,
    *,
    timestamp: float,
    timeframe: str,
    regime: str,
    trend: str,
    technical: dict,
    fundamental: dict,
    risk_score: float,
    confidence: float,
    session: str,
) -> int:
    now = time.time()
    cur = conn.execute(
        """
        INSERT INTO market_intel
            (timestamp, timeframe, regime, trend, technical, fundamental,
             risk_score, confidence, session, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp, timeframe, regime, trend,
            json.dumps(technical), json.dumps(fundamental),
            risk_score, confidence, session, now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_latest_market_intel(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT * FROM market_intel ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["technical"]   = json.loads(d["technical"])
    d["fundamental"] = json.loads(d["fundamental"])
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Trade decision helpers
# ─────────────────────────────────────────────────────────────────────────────

def insert_trade_decision(
    conn: sqlite3.Connection,
    *,
    decision: str,
    reason: str,
    trade_id: str | None = None,
    strategy_id: str | None = None,
    intel_id: int | None = None,
    explanation: dict | None = None,
) -> int:
    now = time.time()
    cur = conn.execute(
        """
        INSERT INTO trade_decisions
            (timestamp, decision, reason, trade_id, strategy_id,
             intel_id, explanation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now, decision, reason, trade_id, strategy_id,
            intel_id, json.dumps(explanation or {}), now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_recent_trade_decisions(
    conn: sqlite3.Connection, limit: int = 20
) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM trade_decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["explanation"] = json.loads(d["explanation"])
        result.append(d)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Strategy memory helpers
# ─────────────────────────────────────────────────────────────────────────────

def insert_strategy_memory(
    conn: sqlite3.Connection,
    genome_hash: str,
    record_type: str,
    metrics: dict,
    *,
    passed: bool = False,
    notes: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO strategy_memory (genome_hash, record_type, metrics, passed, created_at, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (genome_hash, record_type, json.dumps(metrics), int(passed), time.time(), notes),
    )
    conn.commit()


def get_strategy_memory(
    conn: sqlite3.Connection, genome_hash: str
) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM strategy_memory WHERE genome_hash = ? ORDER BY created_at",
        (genome_hash,),
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["metrics"] = json.loads(d["metrics"])
        result.append(d)
    return result
