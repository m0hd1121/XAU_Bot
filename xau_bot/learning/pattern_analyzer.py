"""
pattern_analyzer.py
────────────────────
Discovers statistically significant patterns from the trade database.

Approach:
  1. Group all historical trades by feature values
  2. Compute win rate, expectancy, profit factor per group
  3. Apply Wilson confidence intervals (handles small samples robustly)
  4. Rank features by information gain (mutual information proxy)
  5. Identify composite patterns that explain performance differentials

Statistical principles:
  • Minimum 20 samples before treating a pattern as significant
  • Wilson CI provides uncertainty range — model must respect this
  • Information gain ensures we focus on discriminative features
  • Exponential decay weights recent trades more than old ones
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Statistical helpers
# ─────────────────────────────────────────────────────────────────────────────

_Z95 = 1.96   # 95% confidence interval z-score


def wilson_ci(wins: int, n: int, z: float = _Z95) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion."""
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half   = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def profit_factor(pnls: list[float]) -> float:
    gross_w = sum(p for p in pnls if p > 0) or 0.0
    gross_l = abs(sum(p for p in pnls if p < 0)) or 1e-10
    return gross_w / gross_l


def expectancy_r(r_values: list[float]) -> float:
    return float(np.mean(r_values)) if r_values else 0.0


def mutual_information(feature_values: list, outcomes: list[int],
                       n_bins: int = 5) -> float:
    """
    Estimate mutual information between a feature and binary outcome.
    Works for both categorical (passed as strings) and numeric values.
    """
    if len(feature_values) != len(outcomes) or len(outcomes) < 4:
        return 0.0

    # Bin numeric features; use as-is for categorical
    if isinstance(feature_values[0], (int, float)):
        bins = np.percentile(feature_values, np.linspace(0, 100, n_bins + 1))
        bins = np.unique(bins)
        feat_cats = pd.cut(feature_values, bins=bins, labels=False, include_lowest=True)
        feat_cats = [str(x) for x in feat_cats]
    else:
        feat_cats = [str(x) for x in feature_values]

    # Contingency table
    from collections import Counter
    joint = Counter(zip(feat_cats, [str(o) for o in outcomes]))
    feat_counts = Counter(feat_cats)
    out_counts  = Counter([str(o) for o in outcomes])
    n = len(outcomes)

    mi = 0.0
    for (f, o), count in joint.items():
        p_fo = count / n
        p_f  = feat_counts[f] / n
        p_o  = out_counts[o]  / n
        if p_fo > 0 and p_f > 0 and p_o > 0:
            mi += p_fo * math.log2(p_fo / (p_f * p_o))
    return max(0.0, mi)


# ─────────────────────────────────────────────────────────────────────────────
# PatternAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORICAL_FEATURES = [
    "trend", "trigger_event", "sweep_type", "session",
    "atr_ratio_bucket", "zone_quality_bucket", "regime",
    "volatility_regime", "body_ratio_bucket", "wick_direction",
    "sl_atr_bucket", "rr_bucket", "structure_freshness", "time_of_day",
    "prev_trade_outcome",
]

_NUMERIC_FEATURES = [
    "atr_ratio", "sl_atr", "rr_ratio", "body_ratio",
    "zone_quality", "zone_age_bars", "struct_age",
]

_MIN_SAMPLES = 20


class PatternAnalyzer:
    """
    Discovers and ranks trading patterns from historical records.
    Called by the LearningEngine periodically and after significant
    trade volume accumulates.
    """

    def __init__(self, min_samples: int = _MIN_SAMPLES,
                 decay_halflife: int = 500) -> None:
        self._min_samples = min_samples
        self._decay_halflife = decay_halflife   # trades; recent trades weighted higher

    # ── Public API ───────────────────────────────────────────────────────────

    def analyze(self, records: list[dict]) -> list[dict]:
        """
        Run full analysis on a list of trade+feature records.
        Returns list of pattern_stat dicts ready for DB upsert.
        """
        if len(records) < self._min_samples:
            return []

        df = pd.DataFrame(records)
        df = self._clean(df)

        weights = self._compute_decay_weights(len(df))

        pattern_stats = []

        # ── Per-feature-value analysis ────────────────────────────────────────
        for feat in _CATEGORICAL_FEATURES:
            if feat not in df.columns:
                continue
            for val in df[feat].dropna().unique():
                mask = df[feat] == val
                stats = self._compute_stats(df[mask], weights[mask], feat, str(val))
                if stats:
                    pattern_stats.append(stats)

        # ── Composite pattern analysis (pattern_key) ──────────────────────────
        if "pattern_key" in df.columns:
            for key in df["pattern_key"].dropna().unique():
                mask = df["pattern_key"] == key
                subset = df[mask]
                if len(subset) >= self._min_samples // 2:
                    stats = self._compute_stats(
                        subset, weights[mask], "pattern_key", str(key)
                    )
                    if stats:
                        pattern_stats.append(stats)

        return pattern_stats

    def compute_feature_importances(self, records: list[dict]) -> dict[str, float]:
        """
        Return MI-based importance score per feature.
        Used to weight features in the confidence model.
        """
        if len(records) < self._min_samples:
            return {}

        df = pd.DataFrame(records)
        df = self._clean(df)
        outcomes = (df["outcome"] == "WIN").astype(int).tolist()

        importances = {}
        for feat in _CATEGORICAL_FEATURES:
            if feat not in df.columns:
                continue
            vals = df[feat].fillna("UNKNOWN").tolist()
            mi = mutual_information(vals, outcomes)
            importances[feat] = round(mi, 5)

        for feat in _NUMERIC_FEATURES:
            raw_col = f"raw_{feat}"
            if raw_col not in df.columns and "raw_features" in df.columns:
                try:
                    raw_series = df["raw_features"].apply(
                        lambda x: x.get(feat, None) if isinstance(x, dict) else None
                    )
                    df[raw_col] = raw_series
                except Exception:
                    continue
            col = raw_col if raw_col in df.columns else feat
            if col not in df.columns:
                continue
            vals_raw = df[col].dropna().tolist()
            if len(vals_raw) < self._min_samples:
                continue
            mi = mutual_information(vals_raw, [outcomes[i] for i in df[col].dropna().index])
            importances[feat] = round(mi, 5)

        # Normalise to [0, 1]
        if importances:
            max_mi = max(importances.values()) or 1e-10
            importances = {k: v / max_mi for k, v in importances.items()}

        return importances

    def identify_edge_patterns(self, pattern_stats: list[dict],
                                min_expectancy: float = 0.1) -> dict[str, list[dict]]:
        """
        Segregate patterns into positive edge (should prefer) and
        negative edge (should avoid).
        """
        positive, negative, neutral = [], [], []
        for ps in pattern_stats:
            if not ps.get("is_significant"):
                neutral.append(ps)
                continue
            exp = ps.get("expectancy_r", 0)
            if exp > min_expectancy:
                positive.append(ps)
            elif exp < -min_expectancy:
                negative.append(ps)
            else:
                neutral.append(ps)

        positive.sort(key=lambda x: x.get("expectancy_r", 0), reverse=True)
        negative.sort(key=lambda x: x.get("expectancy_r", 0))
        return {"positive": positive, "negative": negative, "neutral": neutral}

    # ── Private ──────────────────────────────────────────────────────────────

    def _compute_stats(self, subset: pd.DataFrame, weights: np.ndarray,
                       feature_name: str, feature_value: str) -> dict | None:
        n = len(subset)
        if n < 2:
            return None

        wins = (subset["outcome"] == "WIN").sum()
        pnls = subset["pnl"].tolist() if "pnl" in subset.columns else [0.0] * n
        r_vals = subset["pnl_r"].tolist() if "pnl_r" in subset.columns else [0.0] * n

        wr = wins / n
        lo, hi = wilson_ci(wins, n)
        pf = profit_factor(pnls)
        exp_r = expectancy_r(r_vals)

        key = f"{feature_name}={feature_value}"
        desc = f"Trades where {feature_name} = {feature_value}"

        return {
            "pattern_key":          key,
            "feature_description":  desc,
            "sample_count":         n,
            "win_count":            wins,
            "win_rate":             round(wr, 4),
            "avg_r":                round(float(np.mean(r_vals)), 4),
            "avg_pnl":              round(float(np.mean(pnls)), 4),
            "profit_factor":        round(pf, 4),
            "wilson_low":           round(lo, 4),
            "wilson_high":          round(hi, 4),
            "expectancy_r":         round(exp_r, 4),
            "is_significant":       1 if n >= self._min_samples else 0,
        }

    def _compute_decay_weights(self, n: int) -> np.ndarray:
        """Exponential decay: most recent trade has weight 1.0."""
        alpha = math.log(2) / self._decay_halflife
        indices = np.arange(n - 1, -1, -1)  # 0 = most recent
        return np.exp(-alpha * indices)

    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "outcome" not in df.columns and "pnl" in df.columns:
            df["outcome"] = df["pnl"].apply(
                lambda x: "WIN" if x > 1e-9 else ("LOSS" if x < -1e-9 else "BE")
            )
        # Flatten raw_features JSON if present
        if "raw_features" in df.columns:
            try:
                raw_df = pd.json_normalize(df["raw_features"].dropna())
                raw_df.columns = ["raw_" + c for c in raw_df.columns]
                df = pd.concat([df.reset_index(drop=True),
                                raw_df.reset_index(drop=True)], axis=1)
            except Exception:
                pass
        return df
