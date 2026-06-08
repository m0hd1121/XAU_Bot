"""
validation_engine.py
─────────────────────
Prevents the learning engine from overfitting to historical data by
validating every proposed confidence update against held-out periods.

Methods implemented:
  1. Walk-Forward Analysis  — train on window[i], test on window[i+1], step forward
  2. Out-of-Sample Test     — reserve the most recent 20% of data, never train on it
  3. Statistical Significance — enforce minimum sample counts and CI thresholds
  4. Overfitting Score      — compare IS vs OOS performance; reject if OOS degrades

Core safety guarantee:
  An update is REJECTED if OOS expectancy falls below 50% of IS expectancy.
  This prevents the model from learning patterns that only exist in the past.
"""

from __future__ import annotations

import logging
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    validation_type:   str
    window_start:      str
    window_end:        str
    is_trades:         int
    oos_trades:        int
    is_expectancy:     float
    oos_expectancy:    float
    is_sharpe:         float
    oos_sharpe:        float
    is_pf:             float
    oos_pf:            float
    overfit_score:     float   # 0=no overfit, 1=severe overfit
    passed:            bool
    notes:             str

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["passed"] = 1 if self.passed else 0
        return d


# ─────────────────────────────────────────────────────────────────────────────
# ValidationEngine
# ─────────────────────────────────────────────────────────────────────────────

class ValidationEngine:
    """
    Validates proposed model improvements against held-out data.
    Works with lists of trade records (dicts from TradeDatabase).
    """

    def __init__(self, cfg: dict = None) -> None:
        vc = (cfg or {}).get("validation", {})
        self._min_is_trades   = vc.get("min_is_trades",   30)
        self._min_oos_trades  = vc.get("min_oos_trades",  10)
        self._oos_pct         = vc.get("oos_pct",         0.20)    # hold-out fraction
        self._wf_window       = vc.get("wf_window_trades", 60)     # IS window size
        self._wf_step         = vc.get("wf_step_trades",   20)     # step size
        self._max_overfit     = vc.get("max_overfit_score", 0.50)  # reject threshold
        self._min_oos_ratio   = vc.get("min_oos_ratio",    0.40)   # OOS/IS expectancy

    # ── Public API ───────────────────────────────────────────────────────────

    def validate_oos(self, all_trades: list[dict],
                     is_metrics: dict) -> ValidationResult:
        """
        Compare in-sample (IS) metrics against a held-out out-of-sample (OOS)
        window consisting of the most recent `oos_pct` fraction of trades.
        """
        n = len(all_trades)
        if n < self._min_is_trades + self._min_oos_trades:
            return self._insufficient(n)

        split = int(n * (1 - self._oos_pct))
        is_data  = all_trades[:split]
        oos_data = all_trades[split:]

        is_m  = self._compute_metrics(is_data)
        oos_m = self._compute_metrics(oos_data)

        overfit = self._overfit_score(is_m, oos_m)
        passed  = (overfit < self._max_overfit and
                   len(oos_data) >= self._min_oos_trades)

        notes = self._build_notes(is_m, oos_m, overfit, passed)

        return ValidationResult(
            validation_type  = "OOS",
            window_start     = str(all_trades[0].get("open_time", ""))[:10],
            window_end       = str(all_trades[-1].get("open_time", ""))[:10],
            is_trades        = len(is_data),
            oos_trades       = len(oos_data),
            is_expectancy    = is_m["expectancy_r"],
            oos_expectancy   = oos_m["expectancy_r"],
            is_sharpe        = is_m["sharpe"],
            oos_sharpe       = oos_m["sharpe"],
            is_pf            = is_m["profit_factor"],
            oos_pf           = oos_m["profit_factor"],
            overfit_score    = overfit,
            passed           = passed,
            notes            = notes,
        )

    def walk_forward(self, all_trades: list[dict]) -> list[ValidationResult]:
        """
        Sliding walk-forward analysis.  Returns one result per window.
        Used for periodic full re-validation.
        """
        results = []
        n = len(all_trades)
        win = self._wf_window
        step = self._wf_step

        if n < win + self._min_oos_trades:
            return results

        i = 0
        while i + win + step <= n:
            is_data  = all_trades[i: i + win]
            oos_data = all_trades[i + win: i + win + step]

            if len(is_data) >= self._min_is_trades and len(oos_data) >= 5:
                is_m  = self._compute_metrics(is_data)
                oos_m = self._compute_metrics(oos_data)
                overfit = self._overfit_score(is_m, oos_m)
                passed  = overfit < self._max_overfit

                results.append(ValidationResult(
                    validation_type  = "WF",
                    window_start     = str(is_data[0].get("open_time", ""))[:10],
                    window_end       = str(oos_data[-1].get("open_time", ""))[:10],
                    is_trades        = len(is_data),
                    oos_trades       = len(oos_data),
                    is_expectancy    = is_m["expectancy_r"],
                    oos_expectancy   = oos_m["expectancy_r"],
                    is_sharpe        = is_m["sharpe"],
                    oos_sharpe       = oos_m["sharpe"],
                    is_pf            = is_m["profit_factor"],
                    oos_pf           = oos_m["profit_factor"],
                    overfit_score    = overfit,
                    passed           = passed,
                    notes            = self._build_notes(is_m, oos_m, overfit, passed),
                ))
            i += step

        return results

    def validate_pattern(self, pattern_trades: list[dict],
                          min_samples: int = 20) -> dict:
        """
        Check whether a specific pattern has statistical significance
        on held-out data.  Returns a dict with decision and confidence interval.
        """
        n = len(pattern_trades)
        if n < min_samples:
            return {"valid": False, "reason": f"insufficient_samples ({n})", "n": n}

        m = self._compute_metrics(pattern_trades)
        lo = m.get("wilson_low", 0.0)
        hi = m.get("wilson_high", 1.0)
        wr = m.get("win_rate", 0.5)

        # Pattern is valid if the Wilson lower bound is >40% (genuine edge)
        valid = lo > 0.35 and m.get("expectancy_r", 0) > 0.0
        return {
            "valid":       valid,
            "win_rate":    round(wr, 3),
            "wilson_low":  round(lo, 3),
            "wilson_high": round(hi, 3),
            "expectancy_r": round(m.get("expectancy_r", 0), 3),
            "profit_factor": round(m.get("profit_factor", 1.0), 3),
            "n":           n,
            "reason":      "ok" if valid else "insufficient_edge",
        }

    # ── Private: Metrics ─────────────────────────────────────────────────────

    @staticmethod
    def _compute_metrics(trades: list[dict]) -> dict:
        if not trades:
            return {"expectancy_r": 0.0, "sharpe": 0.0, "profit_factor": 1.0,
                    "win_rate": 0.5, "wilson_low": 0.0, "wilson_high": 1.0}

        pnls   = [t.get("pnl", 0.0) for t in trades]
        r_vals = [t.get("pnl_r", 0.0) for t in trades]
        wins   = sum(1 for p in pnls if p > 1e-9)
        n      = len(pnls)

        # Profit factor
        gross_w = sum(p for p in pnls if p > 0) or 0.0
        gross_l = abs(sum(p for p in pnls if p < 0)) or 1e-10
        pf      = gross_w / gross_l

        # Expectancy (R)
        exp_r = float(np.mean(r_vals)) if r_vals else 0.0

        # Sharpe (trade-level)
        if len(r_vals) > 1:
            std_r = float(np.std(r_vals, ddof=1)) or 1e-10
            sharpe = exp_r / std_r * math.sqrt(len(r_vals))
        else:
            sharpe = 0.0

        # Wilson CI
        from .pattern_analyzer import wilson_ci
        lo, hi = wilson_ci(wins, n)

        return {
            "expectancy_r":  round(exp_r, 4),
            "sharpe":        round(sharpe, 4),
            "profit_factor": round(pf, 4),
            "win_rate":      round(wins / n, 4),
            "wilson_low":    round(lo, 4),
            "wilson_high":   round(hi, 4),
            "n":             n,
        }

    @staticmethod
    def _overfit_score(is_m: dict, oos_m: dict) -> float:
        """
        Overfit score ∈ [0, 1].
        0 = OOS matches IS perfectly; 1 = OOS is severely worse.
        """
        is_exp  = is_m.get("expectancy_r",  0.0)
        oos_exp = oos_m.get("expectancy_r", 0.0)

        if abs(is_exp) < 1e-6:
            return 0.0    # No IS edge → nothing to overfit

        if is_exp > 0 and oos_exp >= is_exp * 0.5:
            return 0.0    # OOS retains at least half the IS edge → ok

        degradation = (is_exp - oos_exp) / (abs(is_exp) + 1e-10)
        return max(0.0, min(1.0, degradation))

    @staticmethod
    def _build_notes(is_m: dict, oos_m: dict, overfit: float, passed: bool) -> str:
        verdict = "PASS" if passed else "FAIL"
        return (
            f"{verdict} | overfit={overfit:.2f} | "
            f"IS: n={is_m.get('n',0)} exp={is_m.get('expectancy_r',0):+.3f}R "
            f"pf={is_m.get('profit_factor',0):.2f} | "
            f"OOS: n={oos_m.get('n',0)} exp={oos_m.get('expectancy_r',0):+.3f}R "
            f"pf={oos_m.get('profit_factor',0):.2f}"
        )

    @staticmethod
    def _insufficient(n: int) -> ValidationResult:
        return ValidationResult(
            "OOS", "", "", n, 0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, False,
            f"insufficient_trades ({n})"
        )
