"""
strategy_genome.py
──────────────────
StrategyGenome dataclass — encodes every tunable parameter in config.yaml
into a typed, bounded representation suitable for genetic evolution.

Sections covered:
  market_structure: swing_lookback, bos_confirmation_candles,
                    choch_require_sweep, min_zone_impulse_ratio,
                    zone_max_age_candles, liquidity_equal_threshold
  strategy:         require_htf_bias, require_session_window,
                    sl_buffer_pips, tp1_rr, tp2_rr, use_break_even,
                    trail_after_be, partial_tp_pct, limit_entry_buffer_pct
  risk:             risk_per_trade, max_open_trades, min_reward_to_risk,
                    volatility_scale_factor
  psychology:       max_consecutive_losses, cooldown_candles_after_loss,
                    max_trades_per_session
"""

from __future__ import annotations

import copy
import hashlib
import json
import random as _random
from dataclasses import dataclass, field, asdict
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Parameter bound definitions (min, max)
# ─────────────────────────────────────────────────────────────────────────────

_BOUNDS: dict[str, tuple[Any, Any]] = {
    # market_structure
    "swing_lookback":              (2,      8),
    "bos_confirmation_candles":    (1,      4),
    "min_zone_impulse_ratio":      (1.0,    3.0),
    "zone_max_age_candles":        (100,    1000),
    "liquidity_equal_threshold":   (0.0005, 0.005),
    # strategy
    "sl_buffer_pips":              (0.5,    5.0),
    "tp1_rr":                      (1.0,    3.0),
    "tp2_rr":                      (2.0,    6.0),
    "partial_tp_pct":              (0.3,    0.7),
    "limit_entry_buffer_pct":      (0.0001, 0.001),
    # risk
    "risk_per_trade":              (0.005,  0.02),
    "max_open_trades":             (1,      4),
    "min_reward_to_risk":          (1.5,    3.5),
    "volatility_scale_factor":     (1.0,    3.0),
    # psychology
    "max_consecutive_losses":      (2,      6),
    "cooldown_candles_after_loss": (0,      12),
    "max_trades_per_session":      (1,      5),
}

# Fields that are strictly integers
_INT_FIELDS = {
    "swing_lookback",
    "bos_confirmation_candles",
    "zone_max_age_candles",
    "max_open_trades",
    "max_consecutive_losses",
    "cooldown_candles_after_loss",
    "max_trades_per_session",
}

# Fields that are booleans (not range-bounded)
_BOOL_FIELDS = {
    "choch_require_sweep",
    "require_htf_bias",
    "require_session_window",
    "use_break_even",
    "trail_after_be",
}


@dataclass
class StrategyGenome:
    """
    Complete encoding of all tunable strategy parameters.

    Numeric fields have [min, max] bounds defined in _BOUNDS.
    Boolean fields are plain True/False.
    """

    # ── market_structure ──────────────────────────────────────────────────────
    swing_lookback:             int   = 3
    bos_confirmation_candles:   int   = 2
    choch_require_sweep:        bool  = True
    min_zone_impulse_ratio:     float = 1.5
    zone_max_age_candles:       int   = 500
    liquidity_equal_threshold:  float = 0.0015

    # ── strategy ──────────────────────────────────────────────────────────────
    require_htf_bias:           bool  = True
    require_session_window:     bool  = True
    sl_buffer_pips:             float = 1.5
    tp1_rr:                     float = 1.5
    tp2_rr:                     float = 3.0
    use_break_even:             bool  = True
    trail_after_be:             bool  = True
    partial_tp_pct:             float = 0.5
    limit_entry_buffer_pct:     float = 0.0003

    # ── risk ──────────────────────────────────────────────────────────────────
    risk_per_trade:             float = 0.01
    max_open_trades:            int   = 2
    min_reward_to_risk:         float = 2.0
    volatility_scale_factor:    float = 1.5

    # ── psychology ────────────────────────────────────────────────────────────
    max_consecutive_losses:     int   = 3
    cooldown_candles_after_loss: int  = 6
    max_trades_per_session:     int   = 3

    # ─────────────────────────────────────────────────────────────────────────
    # Factory helpers
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def random(cls, rng: _random.Random | None = None) -> "StrategyGenome":
        """Return a genome with all numeric params uniformly randomised within bounds."""
        r = rng or _random.Random()
        kwargs: dict[str, Any] = {}

        for fname, (lo, hi) in _BOUNDS.items():
            if fname in _INT_FIELDS:
                kwargs[fname] = r.randint(int(lo), int(hi))
            else:
                kwargs[fname] = r.uniform(float(lo), float(hi))

        for fname in _BOOL_FIELDS:
            kwargs[fname] = r.choice([True, False])

        return cls(**kwargs)

    @classmethod
    def from_cfg(cls, cfg: dict) -> "StrategyGenome":
        """Extract genome values from a full config dict."""
        ms  = cfg.get("market_structure", {})
        st  = cfg.get("strategy", {})
        ri  = cfg.get("risk", {})
        ps  = cfg.get("psychology", {})

        return cls(
            # market_structure
            swing_lookback=int(ms.get("swing_lookback", 3)),
            bos_confirmation_candles=int(ms.get("bos_confirmation_candles", 2)),
            choch_require_sweep=bool(ms.get("choch_require_sweep", True)),
            min_zone_impulse_ratio=float(ms.get("min_zone_impulse_ratio", 1.5)),
            zone_max_age_candles=int(ms.get("zone_max_age_candles", 500)),
            liquidity_equal_threshold=float(ms.get("liquidity_equal_threshold", 0.0015)),
            # strategy
            require_htf_bias=bool(st.get("require_htf_bias", True)),
            require_session_window=bool(st.get("require_session_window", True)),
            sl_buffer_pips=float(st.get("sl_buffer_pips", 1.5)),
            tp1_rr=float(st.get("tp1_rr", 1.5)),
            tp2_rr=float(st.get("tp2_rr", 3.0)),
            use_break_even=bool(st.get("use_break_even", True)),
            trail_after_be=bool(st.get("trail_after_be", True)),
            partial_tp_pct=float(st.get("partial_tp_pct", 0.5)),
            limit_entry_buffer_pct=float(st.get("limit_entry_buffer_pct", 0.0003)),
            # risk
            risk_per_trade=float(ri.get("risk_per_trade", 0.01)),
            max_open_trades=int(ri.get("max_open_trades", 2)),
            min_reward_to_risk=float(ri.get("min_reward_to_risk", 2.0)),
            volatility_scale_factor=float(ri.get("volatility_scale_factor", 1.5)),
            # psychology
            max_consecutive_losses=int(ps.get("max_consecutive_losses", 3)),
            cooldown_candles_after_loss=int(ps.get("cooldown_candles_after_loss", 6)),
            max_trades_per_session=int(ps.get("max_trades_per_session", 3)),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyGenome":
        """Reconstruct a genome from a plain dict (e.g., stored in agents.db)."""
        coerced: dict[str, Any] = {}
        for fname, value in d.items():
            if fname in _INT_FIELDS:
                coerced[fname] = int(value)
            elif fname in _BOOL_FIELDS:
                coerced[fname] = bool(value)
            else:
                coerced[fname] = float(value)
        return cls(**coerced)

    # ─────────────────────────────────────────────────────────────────────────
    # Serialisation
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a plain dict of all genome parameters."""
        return asdict(self)

    def genome_hash(self) -> str:
        """
        Deterministic SHA-256 of the genome's parameters.
        Keys are sorted alphabetically before hashing. Returns first 16 hex chars.
        """
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ─────────────────────────────────────────────────────────────────────────
    # Config overlay
    # ─────────────────────────────────────────────────────────────────────────

    def to_cfg_overlay(self, base_cfg: dict) -> dict:
        """
        Deep-merge the genome's values into a copy of base_cfg and return the
        complete merged config dict, ready to pass to Backtester(cfg).
        """
        cfg = copy.deepcopy(base_cfg)

        # Ensure all sections exist
        for section in ("market_structure", "strategy", "risk", "psychology"):
            cfg.setdefault(section, {})

        ms = cfg["market_structure"]
        st = cfg["strategy"]
        ri = cfg["risk"]
        ps = cfg["psychology"]

        # ── market_structure ──────────────────────────────────────────────────
        ms["swing_lookback"]            = self.swing_lookback
        ms["bos_confirmation_candles"]  = self.bos_confirmation_candles
        ms["choch_require_sweep"]       = self.choch_require_sweep
        ms["min_zone_impulse_ratio"]    = self.min_zone_impulse_ratio
        ms["zone_max_age_candles"]      = self.zone_max_age_candles
        ms["liquidity_equal_threshold"] = self.liquidity_equal_threshold

        # ── strategy ──────────────────────────────────────────────────────────
        st["require_htf_bias"]          = self.require_htf_bias
        st["require_session_window"]    = self.require_session_window
        st["sl_buffer_pips"]            = self.sl_buffer_pips
        st["tp1_rr"]                    = self.tp1_rr
        st["tp2_rr"]                    = self.tp2_rr
        st["use_break_even"]            = self.use_break_even
        st["trail_after_be"]            = self.trail_after_be
        st["partial_tp_pct"]            = self.partial_tp_pct
        st["limit_entry_buffer_pct"]    = self.limit_entry_buffer_pct

        # ── risk ──────────────────────────────────────────────────────────────
        ri["risk_per_trade"]            = self.risk_per_trade
        ri["max_open_trades"]           = self.max_open_trades
        ri["min_reward_to_risk"]        = self.min_reward_to_risk
        ri["volatility_scale_factor"]   = self.volatility_scale_factor

        # ── psychology ────────────────────────────────────────────────────────
        ps["max_consecutive_losses"]      = self.max_consecutive_losses
        ps["cooldown_candles_after_loss"] = self.cooldown_candles_after_loss
        ps["max_trades_per_session"]      = self.max_trades_per_session

        return cfg

    # ─────────────────────────────────────────────────────────────────────────
    # Constraint enforcement
    # ─────────────────────────────────────────────────────────────────────────

    def clamp(self) -> "StrategyGenome":
        """
        Return a new genome with all numeric values clamped to their valid
        bounds. Boolean fields are left untouched.
        """
        d = self.to_dict()
        for fname, (lo, hi) in _BOUNDS.items():
            if fname in _INT_FIELDS:
                d[fname] = int(max(int(lo), min(int(hi), int(d[fname]))))
            else:
                d[fname] = float(max(float(lo), min(float(hi), float(d[fname]))))
        return StrategyGenome.from_dict(d)

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience
    # ─────────────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"StrategyGenome(hash={self.genome_hash()}, "
            f"swing={self.swing_lookback}, tp1={self.tp1_rr:.2f}R, "
            f"tp2={self.tp2_rr:.2f}R, risk={self.risk_per_trade:.3f})"
        )
