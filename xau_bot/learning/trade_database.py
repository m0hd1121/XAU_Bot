"""
trade_database.py
─────────────────
Persistent SQLite store for all trade records, extracted features,
discovered patterns, confidence weights, regime history, and
validation results that power the self-learning engine.

Design principles:
  • WAL mode for concurrent read/write without locking the process
  • All heavy queries use indexed columns
  • JSON blobs used only for unstructured extras (raw_features, recommendations)
  • Schema versioned; migrations applied automatically
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_VERSION = 1

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ── Completed trades ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id         INTEGER UNIQUE,
    recorded_at      TEXT    DEFAULT (datetime('now')),
    direction        TEXT,
    entry_price      REAL,
    exit_price       REAL,
    sl_price         REAL,
    tp1_price        REAL,
    tp2_price        REAL,
    lot_size         REAL,
    pnl              REAL,
    pnl_r            REAL,
    close_reason     TEXT,
    session          TEXT,
    quality_score    REAL,
    initial_confidence REAL  DEFAULT NULL,
    mae              REAL,
    mfe              REAL,
    open_bar         INTEGER,
    close_bar        INTEGER,
    duration_bars    INTEGER,
    open_time        TEXT,
    outcome          TEXT     -- WIN / LOSS / BE (break-even)
);

-- ── Rich feature snapshot per trade ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trade_features (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id                   INTEGER REFERENCES trades(trade_id) ON DELETE CASCADE,
    -- Market structure
    trend                      TEXT,
    trigger_event              TEXT,
    sweep_type                 TEXT,
    htf_bias                   TEXT,
    -- Zone
    zone_present               INTEGER,
    zone_quality_bucket        TEXT,   -- LOW / MEDIUM / HIGH
    zone_test_count            INTEGER,
    zone_age_bucket            TEXT,   -- FRESH / AGED
    -- Candle / price action
    body_ratio_bucket          TEXT,   -- LOW / MEDIUM / HIGH
    wick_direction             TEXT,   -- UPPER_HEAVY / LOWER_HEAVY / BALANCED
    candle_type                TEXT,
    -- Volatility / timing
    atr_ratio_bucket           TEXT,   -- LOW / NORMAL / HIGH
    session                    TEXT,
    time_of_day                TEXT,   -- OPEN / MID / CLOSE within session
    -- Risk metrics (bucketed)
    sl_atr_bucket              TEXT,   -- TIGHT / NORMAL / WIDE
    rr_bucket                  TEXT,   -- MINIMUM / GOOD / EXCELLENT
    -- Context
    consecutive_losses         INTEGER,
    prev_trade_outcome         TEXT,   -- WIN / LOSS / NONE
    structure_freshness        TEXT,   -- FRESH / AGED
    -- Regime
    regime                     TEXT,
    volatility_regime          TEXT,
    -- Composite fingerprint (for fast group-by)
    pattern_key                TEXT,
    -- Raw numeric values for numeric analysis
    raw_features               TEXT    -- JSON
);

CREATE INDEX IF NOT EXISTS idx_tf_trade     ON trade_features(trade_id);
CREATE INDEX IF NOT EXISTS idx_tf_pattern   ON trade_features(pattern_key);
CREATE INDEX IF NOT EXISTS idx_tf_session   ON trade_features(session);
CREATE INDEX IF NOT EXISTS idx_tf_regime    ON trade_features(regime);
CREATE INDEX IF NOT EXISTS idx_tf_trigger   ON trade_features(trigger_event);

-- ── Aggregated pattern statistics ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pattern_stats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_key         TEXT    UNIQUE,
    feature_description TEXT,
    sample_count        INTEGER DEFAULT 0,
    win_count           INTEGER DEFAULT 0,
    win_rate            REAL    DEFAULT 0.5,
    avg_r               REAL    DEFAULT 0.0,
    avg_pnl             REAL    DEFAULT 0.0,
    profit_factor       REAL    DEFAULT 1.0,
    wilson_low          REAL    DEFAULT 0.2,
    wilson_high         REAL    DEFAULT 0.8,
    expectancy_r        REAL    DEFAULT 0.0,
    is_significant      INTEGER DEFAULT 0,   -- 1 when sample_count >= MIN_SAMPLES
    last_updated        TEXT
);

CREATE INDEX IF NOT EXISTS idx_ps_key ON pattern_stats(pattern_key);

-- ── Per-feature confidence weights ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS confidence_weights (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_name  TEXT,
    feature_value TEXT,
    regime        TEXT    DEFAULT 'ALL',
    weight        REAL    DEFAULT 0.5,
    sample_count  INTEGER DEFAULT 0,
    last_updated  TEXT,
    UNIQUE(feature_name, feature_value, regime)
);

CREATE INDEX IF NOT EXISTS idx_cw_feature ON confidence_weights(feature_name, feature_value);

-- ── Market regime time-series ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS regime_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT,
    bar_index        INTEGER,
    regime           TEXT,
    volatility_regime TEXT,
    trend_strength   REAL,
    atr_ratio        REAL,
    price            REAL
);

CREATE INDEX IF NOT EXISTS idx_rh_bar ON regime_history(bar_index);

-- ── Post-trade reviews ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS post_trade_reviews (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id                    INTEGER REFERENCES trades(trade_id) ON DELETE CASCADE,
    reviewed_at                 TEXT    DEFAULT (datetime('now')),
    entry_timing_score          REAL,
    confirmation_score          REAL,
    sl_quality_score            REAL,
    target_quality_score        REAL,
    condition_score             REAL,
    overall_decision_score      REAL,
    premature_entry             INTEGER DEFAULT 0,
    insufficient_confirmation   INTEGER DEFAULT 0,
    sl_too_tight                INTEGER DEFAULT 0,
    unrealistic_target          INTEGER DEFAULT 0,
    poor_conditions             INTEGER DEFAULT 0,
    regime_misalignment         INTEGER DEFAULT 0,
    narrative                   TEXT,
    recommendations             TEXT    -- JSON list
);

-- ── Walk-forward / out-of-sample validation results ──────────────────────────
CREATE TABLE IF NOT EXISTS validation_results (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT    DEFAULT (datetime('now')),
    validation_type  TEXT,
    window_start     TEXT,
    window_end       TEXT,
    is_trades        INTEGER,
    oos_trades       INTEGER,
    is_expectancy    REAL,
    oos_expectancy   REAL,
    is_sharpe        REAL,
    oos_sharpe       REAL,
    is_pf            REAL,
    oos_pf           REAL,
    overfit_score    REAL,   -- 0=none, 1=severe
    passed           INTEGER,
    notes            TEXT
);

-- ── Structured learning event log ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    DEFAULT (datetime('now')),
    event_type  TEXT,
    summary     TEXT,
    details     TEXT    -- JSON
);

CREATE INDEX IF NOT EXISTS idx_le_type ON learning_events(event_type);
"""

_MIN_SAMPLES_FOR_SIGNIFICANCE = 20


# ─────────────────────────────────────────────────────────────────────────────
# TradeDatabase
# ─────────────────────────────────────────────────────────────────────────────

class TradeDatabase:

    def __init__(self, db_path: str = "data/learning.db") -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info("TradeDatabase ready: %s", self._path)

    # ── Connection context ───────────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_DDL)
            row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_meta VALUES ('version', ?)",
                             (str(SCHEMA_VERSION),))

    # ── Trade CRUD ───────────────────────────────────────────────────────────

    def insert_trade(self, trade_dict: dict) -> None:
        cols = ["trade_id","direction","entry_price","exit_price","sl_price",
                "tp1_price","tp2_price","lot_size","pnl","pnl_r","close_reason",
                "session","quality_score","initial_confidence","mae","mfe",
                "open_bar","close_bar","duration_bars","open_time","outcome"]
        row = {c: trade_dict.get(c) for c in cols}
        # Compute outcome
        pnl = trade_dict.get("pnl", 0)
        row["outcome"] = "WIN" if pnl > 1e-9 else ("LOSS" if pnl < -1e-9 else "BE")
        row["duration_bars"] = (trade_dict.get("close_bar", 0) or 0) - (trade_dict.get("open_bar", 0) or 0)
        placeholders = ", ".join("?" * len(cols))
        sql = f"INSERT OR IGNORE INTO trades ({', '.join(cols)}) VALUES ({placeholders})"
        with self._conn() as conn:
            conn.execute(sql, [row[c] for c in cols])

    def insert_features(self, trade_id: int, features: dict) -> None:
        feat_cols = [
            "trade_id","trend","trigger_event","sweep_type","htf_bias",
            "zone_present","zone_quality_bucket","zone_test_count","zone_age_bucket",
            "body_ratio_bucket","wick_direction","candle_type",
            "atr_ratio_bucket","session","time_of_day",
            "sl_atr_bucket","rr_bucket","consecutive_losses","prev_trade_outcome",
            "structure_freshness","regime","volatility_regime","pattern_key","raw_features",
        ]
        row = {c: features.get(c) for c in feat_cols}
        row["trade_id"] = trade_id
        row["raw_features"] = json.dumps(features.get("raw", {}))
        ph = ", ".join("?" * len(feat_cols))
        sql = f"INSERT INTO trade_features ({', '.join(feat_cols)}) VALUES ({ph})"
        with self._conn() as conn:
            conn.execute(sql, [row[c] for c in feat_cols])

    def insert_review(self, trade_id: int, review: dict) -> None:
        cols = ["trade_id","entry_timing_score","confirmation_score","sl_quality_score",
                "target_quality_score","condition_score","overall_decision_score",
                "premature_entry","insufficient_confirmation","sl_too_tight",
                "unrealistic_target","poor_conditions","regime_misalignment",
                "narrative","recommendations"]
        row = {c: review.get(c) for c in cols}
        row["trade_id"] = trade_id
        row["recommendations"] = json.dumps(review.get("recommendations", []))
        ph = ", ".join("?" * len(cols))
        sql = f"INSERT OR REPLACE INTO post_trade_reviews ({', '.join(cols)}) VALUES ({ph})"
        with self._conn() as conn:
            conn.execute(sql, [row[c] for c in cols])

    def insert_validation_result(self, result: dict) -> None:
        cols = ["validation_type","window_start","window_end","is_trades","oos_trades",
                "is_expectancy","oos_expectancy","is_sharpe","oos_sharpe",
                "is_pf","oos_pf","overfit_score","passed","notes"]
        ph = ", ".join("?" * len(cols))
        sql = f"INSERT INTO validation_results ({', '.join(cols)}) VALUES ({ph})"
        with self._conn() as conn:
            conn.execute(sql, [result.get(c) for c in cols])

    def insert_regime(self, regime: dict) -> None:
        sql = """INSERT INTO regime_history (ts, bar_index, regime, volatility_regime,
                 trend_strength, atr_ratio, price)
                 VALUES (?, ?, ?, ?, ?, ?, ?)"""
        with self._conn() as conn:
            conn.execute(sql, [
                regime.get("ts"), regime.get("bar_index"),
                regime.get("regime"), regime.get("volatility_regime"),
                regime.get("trend_strength"), regime.get("atr_ratio"),
                regime.get("price"),
            ])

    def log_event(self, event_type: str, summary: str, details: dict = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO learning_events (event_type, summary, details) VALUES (?, ?, ?)",
                (event_type, summary, json.dumps(details or {}))
            )

    # ── Confidence weights ────────────────────────────────────────────────────

    def upsert_confidence_weight(self, feature_name: str, feature_value: str,
                                  regime: str, weight: float, sample_count: int) -> None:
        sql = """
        INSERT INTO confidence_weights (feature_name, feature_value, regime, weight, sample_count, last_updated)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(feature_name, feature_value, regime) DO UPDATE SET
            weight       = excluded.weight,
            sample_count = excluded.sample_count,
            last_updated = excluded.last_updated
        """
        with self._conn() as conn:
            conn.execute(sql, (feature_name, feature_value, regime, weight, sample_count))

    def get_confidence_weights(self, regime: str = "ALL") -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT feature_name, feature_value, weight, sample_count "
                "FROM confidence_weights WHERE regime IN (?, 'ALL')",
                (regime,)
            ).fetchall()
        return {(r["feature_name"], r["feature_value"]): (r["weight"], r["sample_count"])
                for r in rows}

    # ── Pattern stats ─────────────────────────────────────────────────────────

    def upsert_pattern_stats(self, stats: dict) -> None:
        sig = 1 if stats.get("sample_count", 0) >= _MIN_SAMPLES_FOR_SIGNIFICANCE else 0
        sql = """
        INSERT INTO pattern_stats
            (pattern_key, feature_description, sample_count, win_count, win_rate,
             avg_r, avg_pnl, profit_factor, wilson_low, wilson_high, expectancy_r,
             is_significant, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(pattern_key) DO UPDATE SET
            feature_description = excluded.feature_description,
            sample_count   = excluded.sample_count,
            win_count      = excluded.win_count,
            win_rate       = excluded.win_rate,
            avg_r          = excluded.avg_r,
            avg_pnl        = excluded.avg_pnl,
            profit_factor  = excluded.profit_factor,
            wilson_low     = excluded.wilson_low,
            wilson_high    = excluded.wilson_high,
            expectancy_r   = excluded.expectancy_r,
            is_significant = excluded.is_significant,
            last_updated   = excluded.last_updated
        """
        with self._conn() as conn:
            conn.execute(sql, [
                stats["pattern_key"], stats.get("feature_description",""),
                stats["sample_count"], stats["win_count"], stats["win_rate"],
                stats["avg_r"], stats["avg_pnl"], stats["profit_factor"],
                stats["wilson_low"], stats["wilson_high"], stats["expectancy_r"], sig,
            ])

    def get_pattern_stats(self, pattern_key: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM pattern_stats WHERE pattern_key = ?", (pattern_key,)
            ).fetchone()
        return dict(row) if row else None

    def get_significant_patterns(self, min_samples: int = _MIN_SAMPLES_FOR_SIGNIFICANCE,
                                  min_abs_r: float = 0.1) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pattern_stats WHERE sample_count >= ? "
                "AND abs(expectancy_r) >= ? ORDER BY abs(expectancy_r) DESC",
                (min_samples, min_abs_r)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Queries for analysis ──────────────────────────────────────────────────

    def get_all_trades_with_features(self, limit: int = 5000) -> list[dict]:
        sql = """
        SELECT t.*, f.trend, f.trigger_event, f.sweep_type, f.zone_present,
               f.zone_quality_bucket, f.zone_test_count, f.session AS feat_session,
               f.atr_ratio_bucket, f.sl_atr_bucket, f.rr_bucket, f.regime,
               f.volatility_regime, f.pattern_key, f.consecutive_losses,
               f.body_ratio_bucket, f.wick_direction, f.structure_freshness,
               f.time_of_day, f.raw_features
        FROM trades t
        LEFT JOIN trade_features f ON t.trade_id = f.trade_id
        ORDER BY t.recorded_at DESC
        LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_trades_by_pattern(self, pattern_key: str) -> list[dict]:
        sql = """
        SELECT t.outcome, t.pnl_r, t.pnl, t.session, t.quality_score
        FROM trades t
        JOIN trade_features f ON t.trade_id = f.trade_id
        WHERE f.pattern_key = ?
        ORDER BY t.recorded_at DESC
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (pattern_key,)).fetchall()
        return [dict(r) for r in rows]

    def count_trades(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    def get_recent_outcomes(self, n: int = 20) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT outcome FROM trades ORDER BY recorded_at DESC LIMIT ?", (n,)
            ).fetchall()
        return [r[0] for r in rows]

    def get_latest_regime(self) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM regime_history ORDER BY bar_index DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def get_last_validation(self) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM validation_results ORDER BY run_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
