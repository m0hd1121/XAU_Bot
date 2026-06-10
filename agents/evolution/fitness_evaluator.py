"""
fitness_evaluator.py
────────────────────
FitnessEvaluator — runs the Backtester on a StrategyGenome and converts
the raw BacktestResult into a structured, multi-objective FitnessResult.

WalkForwardValidator — splits the CSV date range into n IS/OOS windows,
evaluates each, and returns an aggregated WalkForwardResult to guard
against curve-fitting.

Usage:
    base_cfg = yaml.safe_load(open("config.yaml"))
    evaluator = FitnessEvaluator(base_cfg, "data/XAUUSD_H1.csv")
    result = evaluator.evaluate(genome)
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FitnessResult:
    """
    Multi-objective fitness for one evaluated genome / window.
    composite_score is the primary ranking metric (0–1, higher=better).
    """
    expectancy: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 100.0
    win_rate: float = 0.0
    total_trades: int = 0
    stability_score: float = 0.0       # normalised 0-1, lower stdev = higher score
    recovery_factor: float = 0.0       # total_pnl / max_drawdown_abs
    composite_score: float = 0.0
    passed_minimum: bool = False
    rejection_reason: str = ""
    raw_metrics: dict = field(default_factory=dict)


@dataclass
class WalkForwardResult:
    """Aggregated result of n-split walk-forward validation."""
    is_splits: list[FitnessResult] = field(default_factory=list)
    oos_splits: list[FitnessResult] = field(default_factory=list)
    avg_is_score: float = 0.0
    avg_oos_score: float = 0.0
    oos_degradation: float = 1.0       # 1 - avg_oos/avg_is; lower = better
    passed: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if abs(denominator) < 1e-10:
        return default
    return numerator / denominator


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _compute_sortino(pnls: list[float], initial_capital: float) -> float:
    """Trade-level Sortino ratio using downside deviation."""
    if len(pnls) < 2:
        return 0.0
    returns = [p / max(initial_capital, 1.0) for p in pnls]
    mean_r = sum(returns) / len(returns)
    negative_returns = [r for r in returns if r < 0.0]
    if not negative_returns:
        return 3.0  # No downside — cap at 3.0 as a proxy for excellent
    downside_variance = sum(r ** 2 for r in negative_returns) / len(returns)
    downside_std = math.sqrt(downside_variance)
    if downside_std < 1e-10:
        return 0.0
    # Annualise with sqrt(252) trade-year approximation
    return (mean_r / downside_std) * math.sqrt(252)


def _compute_stability_score(daily_equity: list[dict]) -> float:
    """
    Compute a stability score (0–1) from daily equity snapshots.
    Lower standard deviation of monthly returns → higher score.

    Returns 0.5 (neutral) when insufficient data exists.
    """
    if len(daily_equity) < 10:
        return 0.5

    # Build a {YYYY-MM: final_equity} mapping — keep last entry per month
    monthly_equity: dict[str, float] = {}
    for entry in daily_equity:
        month_key = str(entry.get("date", ""))[:7]
        if month_key:
            monthly_equity[month_key] = float(entry.get("equity", 0.0))

    sorted_months = sorted(monthly_equity.keys())
    if len(sorted_months) < 3:
        return 0.5

    equities = [monthly_equity[m] for m in sorted_months]
    monthly_returns: list[float] = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev > 1e-10:
            monthly_returns.append((equities[i] - prev) / prev)

    if len(monthly_returns) < 2:
        return 0.5

    mean_r = sum(monthly_returns) / len(monthly_returns)
    variance = sum((r - mean_r) ** 2 for r in monthly_returns) / len(monthly_returns)
    std_r = math.sqrt(variance)

    # Soft cap: stdev of 15% monthly returns → score ≈ 0; 0% stdev → score = 1
    # Normalise: score = 1 - min(std / 0.15, 1)
    score = 1.0 - min(std_r / 0.15, 1.0)
    return _clamp01(score)


def _build_composite_score(
    expectancy: float,
    profit_factor: float,
    sharpe_ratio: float,
    max_drawdown_pct: float,
    stability_score: float,
    win_rate_frac: float,       # 0–1, NOT percentage
    recovery_factor: float,
) -> float:
    """
    Weighted multi-objective composite score, all components 0–1.

    Weights:
      expectancy_normalized     0.25
      profit_factor_normalized  0.20
      sharpe_normalized         0.15
      max_drawdown_score        0.15
      stability_score           0.10
      win_rate                  0.10
      recovery_factor_norm      0.05
    """
    # Soft-cap normalisations
    exp_norm   = _clamp01(expectancy / 200.0)                  # cap at $200
    pf_norm    = _clamp01((profit_factor - 1.0) / 4.0)         # PF 1–5 → 0–1
    sh_norm    = _clamp01(sharpe_ratio / 3.0)                  # cap at 3.0
    dd_score   = _clamp01(1.0 - max_drawdown_pct / 30.0)       # 0% dd → 1, 30%+ → 0
    rec_norm   = _clamp01(recovery_factor / 10.0)              # cap at 10x

    composite = (
        exp_norm   * 0.25
        + pf_norm  * 0.20
        + sh_norm  * 0.15
        + dd_score * 0.15
        + _clamp01(stability_score) * 0.10
        + _clamp01(win_rate_frac)   * 0.10
        + rec_norm * 0.05
    )
    return _clamp01(composite)


def _zero_fitness(reason: str) -> FitnessResult:
    return FitnessResult(
        passed_minimum=False,
        rejection_reason=reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# FitnessEvaluator
# ─────────────────────────────────────────────────────────────────────────────

class FitnessEvaluator:
    """
    Evaluates a StrategyGenome by running a full Backtester and converting
    the result into a FitnessResult.

    Parameters
    ----------
    base_cfg : dict
        Full config.yaml dict (used as the template for all evaluations).
    data_csv_path : str
        Absolute path to the OHLC CSV file (used to determine date range for
        walk-forward splitting).
    """

    MIN_TRADES       = 30
    MIN_EXPECTANCY   = 0.0
    MIN_PROFIT_FACTOR = 1.2

    def __init__(self, base_cfg: dict, data_csv_path: str) -> None:
        self._base_cfg = base_cfg
        self._csv_path = str(data_csv_path)

    # ── Public API ──────────────────────────────────────────────────────────

    def evaluate(self, genome: "StrategyGenome") -> FitnessResult:  # type: ignore[name-defined]
        """
        Build the genome config overlay, run Backtester, and return FitnessResult.
        Catches all exceptions and returns a zero FitnessResult on failure.
        """
        from .strategy_genome import StrategyGenome  # local import to avoid circularity
        from xau_bot.backtester import Backtester  # absolute import (sibling package)

        try:
            cfg = genome.to_cfg_overlay(self._base_cfg)
            # Ensure the CSV path points at the evaluator's data file
            cfg.setdefault("data", {})
            cfg["data"]["csv_path"] = self._csv_path
            # Silence per-trade logging during evolution runs
            cfg.setdefault("backtest", {})
            cfg["backtest"]["log_trades"] = False
            cfg["backtest"]["save_equity_curve"] = False

            result = Backtester(cfg).run()
            return self._build_fitness(result, cfg)

        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            logger.debug("Backtester raised exception during evaluation: %s", reason)
            return _zero_fitness(reason)

    # ── Internal ────────────────────────────────────────────────────────────

    def _build_fitness(self, result: "BacktestResult", cfg: dict) -> FitnessResult:  # type: ignore[name-defined]
        """Convert BacktestResult → FitnessResult."""
        m = result.metrics

        if not result.trades or m.get("total_trades", 0) == 0:
            return _zero_fitness("no_trades_generated")

        total_trades    = int(m.get("total_trades", 0))
        profit_factor   = float(m.get("profit_factor", 0.0))
        max_dd_pct      = float(m.get("max_drawdown_pct", 100.0))
        max_dd_dollar   = float(m.get("max_drawdown_dollar", 0.0))
        sharpe          = float(m.get("sharpe_ratio", 0.0))
        win_rate_pct    = float(m.get("win_rate_pct", 0.0))
        total_pnl       = float(m.get("total_pnl", m.get("expectancy_dollar", 0.0) * total_trades))

        # expectancy_dollar is the per-trade average dollar PnL
        expectancy = float(m.get("expectancy_dollar", 0.0))
        if expectancy == 0.0 and result.trades:
            expectancy = sum(t.get("pnl", 0.0) for t in result.trades) / len(result.trades)

        # total_pnl: prefer explicit key, fall back to summing trades
        if total_pnl == 0.0 and result.trades:
            total_pnl = sum(t.get("pnl", 0.0) for t in result.trades)

        # Sortino from raw trade PnLs
        initial_capital = float(cfg.get("risk", {}).get("initial_capital", 10000.0))
        trade_pnls = [t.get("pnl", 0.0) for t in result.trades]
        sortino = _compute_sortino(trade_pnls, initial_capital)

        # Recovery factor
        recovery = _safe_div(total_pnl, max_dd_dollar, default=0.0)

        # Stability from daily equity snapshots
        stability = _compute_stability_score(result.daily_equity)

        win_rate_frac = win_rate_pct / 100.0

        # ── Minimum acceptance checks ──────────────────────────────────────
        rejection_reason = ""
        if total_trades < self.MIN_TRADES:
            rejection_reason = f"insufficient_trades:{total_trades}<{self.MIN_TRADES}"
        elif expectancy <= self.MIN_EXPECTANCY:
            rejection_reason = f"non_positive_expectancy:{expectancy:.2f}"
        elif profit_factor < self.MIN_PROFIT_FACTOR:
            rejection_reason = f"low_profit_factor:{profit_factor:.3f}<{self.MIN_PROFIT_FACTOR}"

        passed = rejection_reason == ""

        composite = _build_composite_score(
            expectancy=expectancy,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd_pct,
            stability_score=stability,
            win_rate_frac=win_rate_frac,
            recovery_factor=max(recovery, 0.0),
        )

        return FitnessResult(
            expectancy=round(expectancy, 4),
            profit_factor=round(profit_factor, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            max_drawdown_pct=round(max_dd_pct, 4),
            win_rate=round(win_rate_frac, 4),
            total_trades=total_trades,
            stability_score=round(stability, 4),
            recovery_factor=round(recovery, 4),
            composite_score=round(composite, 6),
            passed_minimum=passed,
            rejection_reason=rejection_reason,
            raw_metrics=m,
        )


# ─────────────────────────────────────────────────────────────────────────────
# WalkForwardValidator
# ─────────────────────────────────────────────────────────────────────────────

class WalkForwardValidator:
    """
    Splits the OHLC CSV date range into IS/OOS windows and evaluates the
    genome on each window independently.

    Window construction (anchored walk-forward):
      For n_splits windows, the IS period grows with each split while the
      OOS period is a fixed-size forward window immediately following the IS.
      This mimics real deployment: train on the past, test on the near future.

    Parameters
    ----------
    base_cfg : dict
        Full config.yaml template.
    data_csv_path : str
        Path to the OHLC CSV — used to read the full date range.
    is_fraction : float
        Fraction of the total window assigned to in-sample (default 0.80).
    """

    OOS_DEGRADATION_THRESHOLD = 0.50
    MIN_OOS_COMPOSITE         = 0.30

    def __init__(
        self,
        base_cfg: dict,
        data_csv_path: str,
        is_fraction: float = 0.80,
    ) -> None:
        self._base_cfg   = base_cfg
        self._csv_path   = str(data_csv_path)
        self._is_fraction = is_fraction
        self._date_range: Optional[tuple[datetime, datetime]] = None

    # ── Public API ──────────────────────────────────────────────────────────

    def validate(
        self,
        genome: "StrategyGenome",  # type: ignore[name-defined]
        n_splits: int = 5,
    ) -> WalkForwardResult:
        """
        Run walk-forward validation.  Returns a WalkForwardResult with per-split
        IS and OOS FitnessResult objects plus aggregated statistics.
        """
        windows = self._build_windows(n_splits)
        if not windows:
            return WalkForwardResult(
                passed=False,
                oos_degradation=1.0,
            )

        is_results: list[FitnessResult] = []
        oos_results: list[FitnessResult] = []

        for is_start, is_end, oos_start, oos_end in windows:
            is_cfg  = self._cfg_for_window(is_start, is_end)
            oos_cfg = self._cfg_for_window(oos_start, oos_end)

            is_evaluator  = FitnessEvaluator(is_cfg,  self._csv_path)
            oos_evaluator = FitnessEvaluator(oos_cfg, self._csv_path)

            is_fitness  = is_evaluator.evaluate(genome)
            oos_fitness = oos_evaluator.evaluate(genome)

            is_results.append(is_fitness)
            oos_results.append(oos_fitness)

            logger.debug(
                "WF split IS[%s→%s] score=%.3f  OOS[%s→%s] score=%.3f",
                is_start.strftime("%Y-%m-%d"), is_end.strftime("%Y-%m-%d"),
                is_fitness.composite_score,
                oos_start.strftime("%Y-%m-%d"), oos_end.strftime("%Y-%m-%d"),
                oos_fitness.composite_score,
            )

        avg_is  = self._mean([r.composite_score for r in is_results])
        avg_oos = self._mean([r.composite_score for r in oos_results])

        degradation = 1.0 - _safe_div(avg_oos, avg_is, default=1.0)
        degradation = max(0.0, degradation)  # can't be negative in a meaningful way

        passed = (
            degradation < self.OOS_DEGRADATION_THRESHOLD
            and avg_oos >= self.MIN_OOS_COMPOSITE
        )

        return WalkForwardResult(
            is_splits=is_results,
            oos_splits=oos_results,
            avg_is_score=round(avg_is, 6),
            avg_oos_score=round(avg_oos, 6),
            oos_degradation=round(degradation, 6),
            passed=passed,
        )

    # ── Internal ────────────────────────────────────────────────────────────

    def _get_date_range(self) -> tuple[datetime, datetime]:
        """Load the CSV once to determine the full date range."""
        if self._date_range is not None:
            return self._date_range

        try:
            import pandas as pd
            data_cfg = self._base_cfg.get("data", {})
            date_col = data_cfg.get("date_column", "time")
            date_fmt = data_cfg.get("date_format", None)
            df = pd.read_csv(self._csv_path, parse_dates=[date_col])
            df[date_col] = pd.to_datetime(df[date_col], format=date_fmt)
            start = df[date_col].min().to_pydatetime()
            end   = df[date_col].max().to_pydatetime()
            self._date_range = (start, end)
            return start, end
        except Exception as exc:
            raise RuntimeError(
                f"WalkForwardValidator could not determine CSV date range: {exc}"
            ) from exc

    def _build_windows(
        self, n_splits: int
    ) -> list[tuple[datetime, datetime, datetime, datetime]]:
        """
        Build anchored walk-forward windows.

        The total date range is divided so that the OOS window is a fixed
        fraction (1 - is_fraction) of the per-split length, walked forward.

        Returns list of (is_start, is_end, oos_start, oos_end) tuples.
        """
        start, end = self._get_date_range()
        total_days = (end - start).days
        if total_days < 60:
            logger.warning("WalkForward: CSV has fewer than 60 days; skipping.")
            return []

        # Each window covers total_days / n_splits calendar days
        window_days = total_days / n_splits
        oos_days    = int(window_days * (1.0 - self._is_fraction))
        oos_days    = max(oos_days, 14)  # floor at 2 weeks

        windows = []
        for i in range(n_splits):
            # IS period: from data start to the split point
            split_day    = int(window_days * (i + 1) * self._is_fraction)
            is_start     = start
            is_end       = start + timedelta(days=split_day)
            oos_start    = is_end + timedelta(days=1)
            oos_end      = oos_start + timedelta(days=oos_days)

            # Clip OOS end to the actual data end
            if oos_end > end:
                oos_end = end
            # Skip degenerate windows
            if oos_start >= oos_end or is_start >= is_end:
                continue

            windows.append((is_start, is_end, oos_start, oos_end))

        return windows

    def _cfg_for_window(self, start: datetime, end: datetime) -> dict:
        """Return a base_cfg copy with backtest.start_date / end_date overridden."""
        cfg = copy.deepcopy(self._base_cfg)
        cfg.setdefault("backtest", {})
        cfg["backtest"]["start_date"] = start.strftime("%Y-%m-%d")
        cfg["backtest"]["end_date"]   = end.strftime("%Y-%m-%d")
        # Point at our CSV
        cfg.setdefault("data", {})
        cfg["data"]["csv_path"] = self._csv_path
        return cfg

    @staticmethod
    def _mean(values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)
