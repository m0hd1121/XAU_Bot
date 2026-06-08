"""
feature_extractor.py
─────────────────────
Extracts a rich, normalized feature vector from a completed or pending
trade and its surrounding market context.

All features are intentionally bucketed into discrete categories.
This improves statistical robustness and prevents overfitting on
exact numeric values — the learning engine learns from patterns,
not memorized prices.

Features extracted:
  • Market structure  — trend direction, trigger event, sweep type
  • Zone context      — quality, freshness, test history
  • Candle behavior   — body ratio, wick direction, candle type
  • Volatility proxy  — ATR ratio vs baseline
  • Timing            — session, time-of-day within session
  • Risk metrics      — SL width vs ATR, actual R:R ratio
  • Trade context     — consecutive losses, prev outcome, structure age
  • Regime            — trending/ranging/volatile/choppy
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from ..market_structure_engine import Trend, StructureEvent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Bucketing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bucket(value: float, low: float, high: float,
            labels: tuple = ("LOW", "MEDIUM", "HIGH")) -> str:
    if value <= low:
        return labels[0]
    if value >= high:
        return labels[2]
    return labels[1]


def _atr_bucket(atr_ratio: float) -> str:
    return _bucket(atr_ratio, 0.70, 1.40)


def _body_bucket(body_ratio: float) -> str:
    return _bucket(body_ratio, 0.25, 0.60)


def _sl_atr_bucket(sl_atr_ratio: float) -> str:
    return _bucket(sl_atr_ratio, 0.5, 1.5, ("TIGHT", "NORMAL", "WIDE"))


def _rr_bucket(rr: float) -> str:
    if rr < 2.0:
        return "MINIMUM"
    if rr < 3.0:
        return "GOOD"
    return "EXCELLENT"


def _zone_quality_bucket(quality: float) -> str:
    return _bucket(quality, 0.35, 0.65)


def _losses_bucket(n: int) -> int:
    return min(n, 3)   # cap at 3 for statistical grouping


def _time_of_day(dt: datetime, session_start_h: int, session_end_h: int) -> str:
    if not isinstance(dt, datetime):
        return "UNKNOWN"
    h = dt.hour
    span = max(session_end_h - session_start_h, 1)
    pos  = (h - session_start_h) / span
    if pos < 0.33:
        return "OPEN"
    if pos < 0.67:
        return "MID"
    return "CLOSE"


_SESSION_HOURS = {
    "london":   (7, 12),
    "new_york": (13, 17),
    "overlap":  (13, 15),
    "asian":    (0,  7),
}


def _structure_freshness(shift_bar: int, current_bar: int) -> str:
    age = current_bar - shift_bar
    return "FRESH" if age <= 5 else "AGED"


# ─────────────────────────────────────────────────────────────────────────────
# FeatureVector
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FeatureVector:
    """
    Complete feature snapshot for a single trade decision.
    `pattern_key` is a hash of the primary categorical features —
    used for fast group-by in the pattern analyzer.
    """
    # Structure
    trend:               str
    trigger_event:       str
    sweep_type:          str
    htf_bias:            str

    # Zone
    zone_present:        bool
    zone_quality_bucket: str
    zone_test_count:     int
    zone_age_bucket:     str

    # Candle
    body_ratio_bucket:   str
    wick_direction:      str
    candle_type:         str

    # Volatility / timing
    atr_ratio_bucket:    str
    session:             str
    time_of_day:         str

    # Risk
    sl_atr_bucket:       str
    rr_bucket:           str

    # Context
    consecutive_losses:  int
    prev_trade_outcome:  str
    structure_freshness: str

    # Regime
    regime:              str
    volatility_regime:   str

    # Computed
    pattern_key:         str
    raw: dict            = None   # numeric values for regression-style analysis

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "raw"}
        d["raw"] = self.raw or {}
        return d


# ─────────────────────────────────────────────────────────────────────────────
# FeatureExtractor
# ─────────────────────────────────────────────────────────────────────────────

class FeatureExtractor:
    """
    Extracts FeatureVector objects from trade setups and market state.
    Stateless — safe to call from any thread.
    """

    def __init__(self, cfg: dict) -> None:
        self._cfg = cfg

    def extract(
        self,
        *,
        direction: str,
        entry_price: float,
        sl_price: float,
        tp1_price: float,
        session: str,
        timestamp,
        atr_proxy: float,
        baseline_atr: float,
        trigger_event: str,
        sweep_type: str,
        htf_bias: str,
        trend: str,
        zone_present: bool,
        zone_quality: float,
        zone_test_count: int,
        zone_origin_bar: int,
        current_bar: int,
        last_shift_bar: int,
        body_ratio: float,
        upper_wick: float,
        lower_wick: float,
        candle_type: str,
        consecutive_losses: int,
        prev_trade_outcome: str,
        regime: str,
        volatility_regime: str,
    ) -> FeatureVector:

        # ── Derived numerics ──────────────────────────────────────────────────
        atr_ratio = atr_proxy / (baseline_atr + 1e-10)
        sl_dist   = abs(entry_price - sl_price)
        tp_dist   = abs(tp1_price   - entry_price)
        rr_ratio  = tp_dist / (sl_dist + 1e-10)
        sl_atr    = sl_dist / (atr_proxy + 1e-10)

        # ── Wick direction ────────────────────────────────────────────────────
        total_wick = upper_wick + lower_wick + 1e-10
        if upper_wick / total_wick > 0.60:
            wick_dir = "UPPER_HEAVY"
        elif lower_wick / total_wick > 0.60:
            wick_dir = "LOWER_HEAVY"
        else:
            wick_dir = "BALANCED"

        # ── Zone age ─────────────────────────────────────────────────────────
        zone_age = "FRESH" if current_bar - zone_origin_bar < 30 else "AGED"

        # ── Time-of-day bucket ────────────────────────────────────────────────
        sh, eh = _SESSION_HOURS.get(session, (0, 24))
        tod = _time_of_day(
            timestamp if isinstance(timestamp, datetime) else datetime.now(),
            sh, eh
        )

        # ── Primary categorical features → pattern key ────────────────────────
        # Use only the most stable/informative features for fingerprinting
        primary = "|".join([
            trend,
            trigger_event,
            sweep_type,
            session,
            _atr_bucket(atr_ratio),
            _zone_quality_bucket(zone_quality) if zone_present else "NO_ZONE",
            regime,
        ])
        pattern_key = hashlib.sha256(primary.encode()).hexdigest()[:16]

        return FeatureVector(
            trend               = trend,
            trigger_event       = trigger_event,
            sweep_type          = sweep_type,
            htf_bias            = htf_bias,
            zone_present        = zone_present,
            zone_quality_bucket = _zone_quality_bucket(zone_quality) if zone_present else "NONE",
            zone_test_count     = _losses_bucket(zone_test_count),
            zone_age_bucket     = zone_age,
            body_ratio_bucket   = _body_bucket(body_ratio),
            wick_direction      = wick_dir,
            candle_type         = candle_type,
            atr_ratio_bucket    = _atr_bucket(atr_ratio),
            session             = session,
            time_of_day         = tod,
            sl_atr_bucket       = _sl_atr_bucket(sl_atr),
            rr_bucket           = _rr_bucket(rr_ratio),
            consecutive_losses  = _losses_bucket(consecutive_losses),
            prev_trade_outcome  = prev_trade_outcome or "NONE",
            structure_freshness = _structure_freshness(last_shift_bar, current_bar),
            regime              = regime,
            volatility_regime   = volatility_regime,
            pattern_key         = pattern_key,
            raw={
                "atr_ratio":    round(atr_ratio, 3),
                "sl_atr":       round(sl_atr, 3),
                "rr_ratio":     round(rr_ratio, 3),
                "body_ratio":   round(body_ratio, 3),
                "upper_wick":   round(upper_wick, 3),
                "lower_wick":   round(lower_wick, 3),
                "zone_quality": round(zone_quality, 3),
                "zone_age_bars": current_bar - zone_origin_bar,
                "struct_age":   current_bar - last_shift_bar,
                "consec_losses": consecutive_losses,
            }
        )

    def extract_from_trade_record(
        self,
        trade: dict,
        df: pd.DataFrame,
        market_state,
        consecutive_losses: int,
        prev_outcome: str,
        regime: str,
        volatility_regime: str,
    ) -> Optional[FeatureVector]:
        """
        Convenience wrapper: build FeatureVector from a closed ActiveTrade dict
        and the surrounding DataFrame context.
        """
        try:
            i = trade.get("open_bar", 0)
            if i >= len(df):
                return None

            atr   = float(df["atr_proxy"].values[i]) if "atr_proxy" in df.columns else 1.0
            baseline = float(df["atr_proxy"].rolling(50, min_periods=5).mean().values[i])
            setup = trade.get("setup_snapshot", {})   # populated by strategy engine

            return self.extract(
                direction         = trade.get("direction", "long"),
                entry_price       = trade.get("entry_price", 0.0),
                sl_price          = trade.get("sl_price", 0.0),
                tp1_price         = trade.get("tp1_price", 0.0),
                session           = trade.get("session", "unknown"),
                timestamp         = pd.to_datetime(trade.get("open_time")),
                atr_proxy         = atr,
                baseline_atr      = baseline,
                trigger_event     = trade.get("sweep_event", "UNKNOWN"),
                sweep_type        = setup.get("sweep_type", "UNKNOWN"),
                htf_bias          = setup.get("htf_bias", "UNKNOWN"),
                trend             = setup.get("trend", "UNKNOWN"),
                zone_present      = setup.get("zone_present", False),
                zone_quality      = float(setup.get("zone_quality", 0.5)),
                zone_test_count   = int(setup.get("zone_test_count", 0)),
                zone_origin_bar   = int(setup.get("zone_origin_bar", max(0, i - 30))),
                current_bar       = i,
                last_shift_bar    = int(setup.get("last_shift_bar", max(0, i - 3))),
                body_ratio        = float(df.get("body_ratio", pd.Series([0.5])).values[i]
                                         if "body_ratio" in df.columns else 0.5),
                upper_wick        = float(df["upper_wick"].values[i]) if "upper_wick" in df.columns else 0.0,
                lower_wick        = float(df["lower_wick"].values[i]) if "lower_wick" in df.columns else 0.0,
                candle_type       = str(df["candle_type"].values[i]) if "candle_type" in df.columns else "neutral",
                consecutive_losses = consecutive_losses,
                prev_trade_outcome = prev_outcome,
                regime            = regime,
                volatility_regime = volatility_regime,
            )
        except Exception as exc:
            logger.debug("Feature extraction error: %s", exc)
            return None
