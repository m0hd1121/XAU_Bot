"""
confidence_model.py
────────────────────
Adaptive confidence scoring for trade setups.

Mechanism:
  1. Each feature-value pair has a confidence weight in [0, 1],
     initialised to 0.5 (neutral) and updated via EMA as trades resolve.
  2. Feature importances (mutual information scores) determine how much
     each feature contributes to the composite score.
  3. Regime multipliers allow the model to express that some setups
     work better in certain market conditions.
  4. A Bayesian prior prevents single-sample overconfidence.
  5. Composite score = weighted average of per-feature confidences,
     adjusted by regime multiplier.

Safety constraints hard-coded into this module:
  • Confidence never adjusts risk parameters
  • Maximum confidence clamp: 0.95 (never 100% certain)
  • Minimum confidence: 0.05 (never absolute rejection based on history)
  • Regime multiplier range: [0.70, 1.30]
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .feature_extractor import FeatureVector

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_EMA_ALPHA      = 0.08    # learning rate for confidence updates
_PRIOR_STRENGTH = 10      # equivalent sample count of the 0.5 prior
_MIN_CONFIDENCE = 0.05
_MAX_CONFIDENCE = 0.95
_MIN_REGIME_MULT = 0.70
_MAX_REGIME_MULT = 1.30

# Default feature importances (overridden by PatternAnalyzer)
_DEFAULT_IMPORTANCES = {
    "trigger_event":    0.90,
    "sweep_type":       0.85,
    "trend":            0.80,
    "session":          0.75,
    "regime":           0.70,
    "zone_quality_bucket": 0.65,
    "atr_ratio_bucket": 0.55,
    "structure_freshness": 0.50,
    "rr_bucket":        0.50,
    "wick_direction":   0.45,
    "body_ratio_bucket": 0.40,
    "sl_atr_bucket":    0.40,
    "volatility_regime": 0.35,
    "prev_trade_outcome": 0.30,
    "consecutive_losses": 0.25,
    "time_of_day":      0.20,
}

# Regime multipliers (prior knowledge; updated by validation)
_REGIME_MULTIPLIERS = {
    "STRONG_TREND":    1.15,
    "WEAK_TREND":      1.00,
    "RANGING":         0.85,
    "HIGH_VOLATILITY": 0.80,
    "LOW_VOLATILITY":  0.90,
    "CHOPPY":          0.72,
    "UNKNOWN":         1.00,
}


# ─────────────────────────────────────────────────────────────────────────────
# ConfidenceBreakdown
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConfidenceBreakdown:
    """Detailed decomposition of a confidence score for explainability."""
    composite_score:    float
    regime_multiplier:  float
    final_score:        float
    feature_scores: dict[str, float] = field(default_factory=dict)
    feature_weights: dict[str, float] = field(default_factory=dict)
    sample_counts: dict[str, int] = field(default_factory=dict)
    dominant_features: list[str] = field(default_factory=list)
    weak_features:     list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# ConfidenceModel
# ─────────────────────────────────────────────────────────────────────────────

class ConfidenceModel:
    """
    Adaptive confidence model that learns from trade outcomes.
    Thread-safe for reads; write operations should be serialised by
    the LearningEngine.
    """

    def __init__(self) -> None:
        # confidence_store: {(feature_name, feature_value): (confidence, sample_count)}
        self._store: dict[tuple[str, str], tuple[float, int]] = {}
        self._importances: dict[str, float] = dict(_DEFAULT_IMPORTANCES)
        self._regime_mults: dict[str, float] = dict(_REGIME_MULTIPLIERS)

    # ── Serialisation (for DB persistence) ───────────────────────────────────

    def load_from_db_weights(self, weights: dict) -> None:
        """Populate from DB rows: {(feature, value): (weight, count)}."""
        for (feat, val), (w, cnt) in weights.items():
            self._store[(feat, val)] = (float(w), int(cnt))
        logger.info("Confidence model loaded: %d entries", len(self._store))

    def to_db_rows(self) -> list[tuple]:
        """Yield (feature_name, feature_value, regime, weight, sample_count) tuples."""
        return [
            (f, v, "ALL", w, cnt)
            for (f, v), (w, cnt) in self._store.items()
        ]

    def update_importances(self, importances: dict[str, float]) -> None:
        """Replace feature importances after PatternAnalyzer update."""
        for k, v in importances.items():
            # Blend with defaults to prevent extreme jumps
            default = _DEFAULT_IMPORTANCES.get(k, 0.5)
            self._importances[k] = 0.7 * v + 0.3 * default
        logger.debug("Feature importances updated: %s", self._importances)

    def update_regime_multiplier(self, regime: str, new_mult: float) -> None:
        clamped = max(_MIN_REGIME_MULT, min(_MAX_REGIME_MULT, new_mult))
        self._regime_mults[regime] = 0.8 * self._regime_mults.get(regime, 1.0) + 0.2 * clamped

    # ── Core scoring ──────────────────────────────────────────────────────────

    def score(self, features: FeatureVector) -> ConfidenceBreakdown:
        """
        Compute composite confidence for a given feature vector.
        Returns a ConfidenceBreakdown with the final score and all
        per-feature contributions for explainability.
        """
        feat_dict = {
            "trend":               features.trend,
            "trigger_event":       features.trigger_event,
            "sweep_type":          features.sweep_type,
            "session":             features.session,
            "atr_ratio_bucket":    features.atr_ratio_bucket,
            "zone_quality_bucket": features.zone_quality_bucket,
            "body_ratio_bucket":   features.body_ratio_bucket,
            "wick_direction":      features.wick_direction,
            "sl_atr_bucket":       features.sl_atr_bucket,
            "rr_bucket":           features.rr_bucket,
            "structure_freshness": features.structure_freshness,
            "prev_trade_outcome":  features.prev_trade_outcome,
            "consecutive_losses":  str(features.consecutive_losses),
            "regime":              features.regime,
            "volatility_regime":   features.volatility_regime,
            "time_of_day":         features.time_of_day,
        }

        scores, weights, counts = {}, {}, {}
        for fname, fval in feat_dict.items():
            key  = (fname, str(fval))
            conf, cnt = self._store.get(key, (0.5, 0))
            imp  = self._importances.get(fname, 0.5)
            scores[fname] = conf
            weights[fname] = imp
            counts[fname]  = cnt

        # Weighted average
        total_w = sum(weights.values()) or 1e-10
        composite = sum(scores[f] * weights[f] for f in scores) / total_w
        composite  = max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, composite))

        regime_mult = self._regime_mults.get(features.regime, 1.0)
        final = max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, composite * regime_mult))

        # Top / bottom features
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        dominant = [f for f, s in ranked[:3] if s > 0.60]
        weak     = [f for f, s in ranked if s < 0.40][:3]

        return ConfidenceBreakdown(
            composite_score   = round(composite, 4),
            regime_multiplier = round(regime_mult, 3),
            final_score       = round(final, 4),
            feature_scores    = {f: round(s, 4) for f, s in scores.items()},
            feature_weights   = {f: round(w, 4) for f, w in weights.items()},
            sample_counts     = counts,
            dominant_features = dominant,
            weak_features     = weak,
        )

    # ── Learning update ───────────────────────────────────────────────────────

    def update(self, features: FeatureVector, outcome: str,
               pnl_r: float = 0.0) -> None:
        """
        Update confidence for each feature given a trade outcome.
        Uses EMA with Bayesian smoothing so early samples don't dominate.

        outcome: "WIN" / "LOSS" / "BE"
        pnl_r:   R-multiple (used to weight wins proportionally)
        """
        win = 1.0 if outcome == "WIN" else 0.0
        # Scale the win signal: bigger R = stronger positive signal
        if outcome == "WIN":
            signal = min(1.0, 0.5 + pnl_r * 0.1)
        elif outcome == "LOSS":
            signal = max(0.0, 0.5 + pnl_r * 0.1)   # pnl_r is negative for losses
        else:
            signal = 0.5

        feat_dict = {
            "trend":               features.trend,
            "trigger_event":       features.trigger_event,
            "sweep_type":          features.sweep_type,
            "session":             features.session,
            "atr_ratio_bucket":    features.atr_ratio_bucket,
            "zone_quality_bucket": features.zone_quality_bucket,
            "body_ratio_bucket":   features.body_ratio_bucket,
            "wick_direction":      features.wick_direction,
            "sl_atr_bucket":       features.sl_atr_bucket,
            "rr_bucket":           features.rr_bucket,
            "structure_freshness": features.structure_freshness,
            "regime":              features.regime,
            "volatility_regime":   features.volatility_regime,
        }

        for fname, fval in feat_dict.items():
            key = (fname, str(fval))
            cur_conf, cnt = self._store.get(key, (0.5, 0))

            # Bayesian EMA: weight prior more heavily when samples are few
            effective_alpha = _EMA_ALPHA * (cnt / (cnt + _PRIOR_STRENGTH))
            effective_alpha = max(0.005, min(0.15, effective_alpha))

            new_conf = (1 - effective_alpha) * cur_conf + effective_alpha * signal
            new_conf = max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, new_conf))
            self._store[key] = (new_conf, cnt + 1)

    # ── Regime learning ───────────────────────────────────────────────────────

    def update_regime_from_stats(self, regime: str, win_rate: float,
                                  profit_factor: float, n_samples: int) -> None:
        """
        Adjust regime multiplier based on observed statistics in that regime.
        Only updates when sufficient samples exist.
        """
        if n_samples < 20:
            return
        # Target multiplier: scale around 1.0 based on PF
        target = 1.0 + (profit_factor - 1.0) * 0.2
        target = max(_MIN_REGIME_MULT, min(_MAX_REGIME_MULT, target))
        current = self._regime_mults.get(regime, 1.0)
        self._regime_mults[regime] = 0.9 * current + 0.1 * target
        logger.debug("Regime mult updated: %s → %.3f", regime, self._regime_mults[regime])

    # ── Utility ───────────────────────────────────────────────────────────────

    def get_regime_multiplier(self, regime: str) -> float:
        return self._regime_mults.get(regime, 1.0)

    def get_feature_confidence(self, feature_name: str, feature_value: str) -> float:
        return self._store.get((feature_name, str(feature_value)), (0.5, 0))[0]

    def get_sample_count(self, feature_name: str, feature_value: str) -> int:
        return self._store.get((feature_name, str(feature_value)), (0.5, 0))[1]

    @property
    def total_samples(self) -> int:
        return max((v[1] for v in self._store.values()), default=0)

    def summary(self) -> dict:
        return {
            "stored_entries":   len(self._store),
            "max_sample_count": self.total_samples,
            "top_features":     sorted(
                self._importances.items(), key=lambda x: x[1], reverse=True
            )[:5],
            "regime_multipliers": dict(self._regime_mults),
        }
