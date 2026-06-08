"""
performance_analyzer.py
───────────────────────
Computes and presents comprehensive performance metrics from a completed
backtest. All calculations are pure math — no indicator library dependency.

Metrics tracked:
  • Total return, CAGR
  • Win rate, profit factor
  • Average winner / loser
  • Maximum drawdown (dollar and %)
  • Sharpe ratio (from equity returns)
  • Calmar ratio
  • Expectancy (in R and dollar)
  • Consecutive win/loss streaks
  • Trade-by-trade log (CSV export)
  • Session breakdown
  • Monthly performance table
"""

from __future__ import annotations

import csv
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PerformanceReport:
    """Structured container for all metrics."""
    # Overview
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    total_trades: int
    trading_days: int

    # Win/Loss
    winners: int
    losers: int
    win_rate_pct: float
    avg_winner: float
    avg_loser: float
    largest_winner: float
    largest_loser: float
    best_r: float
    worst_r: float

    # Risk-adjusted
    profit_factor: float
    expectancy_r: float
    expectancy_dollar: float
    sharpe_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_drawdown_dollar: float
    avg_drawdown_pct: float
    recovery_factor: float

    # Streaks
    max_consec_wins: int
    max_consec_losses: int

    # Breakdown
    by_session: dict
    by_direction: dict
    monthly_pnl: dict


class PerformanceAnalyzer:

    def __init__(self, cfg: dict) -> None:
        self._cfg = cfg
        self._output_dir = cfg.get("backtest", {}).get("output_dir", "reports")
        self._initial_capital = cfg.get("risk", {}).get("initial_capital", 10000.0)

    # ── Public API ──────────────────────────────────────────────────────────

    def compute(
        self,
        trades: list[dict],
        equity_curve: list[float],
        final_equity: float,
        initial_capital: float,
    ) -> dict:
        """
        Compute full performance metrics. Returns a flat dict (easy to log/export).
        Also saves the trade log CSV.
        """
        if not trades:
            logger.warning("No trades to analyse.")
            return {"total_trades": 0, "message": "no_trades"}

        initial_capital = initial_capital or self._initial_capital
        pnls    = [t["pnl"] for t in trades]
        r_vals  = [t.get("pnl_r", 0.0) for t in trades]
        winners = [p for p in pnls if p > 0]
        losers  = [p for p in pnls if p <= 0]

        # ── Return metrics ───────────────────────────────────────────────────
        total_return = (final_equity - initial_capital) / (initial_capital + 1e-10)

        # CAGR approximation using number of trading days
        if trades:
            try:
                t0 = datetime.fromisoformat(trades[0]["open_time"][:19])
                t1 = datetime.fromisoformat(trades[-1]["open_time"][:19])
                trading_days = max((t1 - t0).days, 1)
                years = trading_days / 365.25
                cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0
            except Exception:
                trading_days = len(set(t["open_time"][:10] for t in trades))
                cagr = 0.0
        else:
            trading_days = 0
            cagr = 0.0

        # ── Win/loss stats ───────────────────────────────────────────────────
        win_rate = len(winners) / len(pnls) * 100 if pnls else 0.0
        avg_w    = np.mean(winners) if winners else 0.0
        avg_l    = np.mean(losers)  if losers  else 0.0
        max_w    = max(winners) if winners else 0.0
        max_l    = min(losers)  if losers  else 0.0
        best_r   = max(r_vals) if r_vals else 0.0
        worst_r  = min(r_vals) if r_vals else 0.0

        # ── Profit factor ────────────────────────────────────────────────────
        gross_profit = sum(winners) if winners else 0.0
        gross_loss   = abs(sum(losers)) if losers else 1e-10
        profit_factor = gross_profit / gross_loss

        # ── Expectancy ───────────────────────────────────────────────────────
        expectancy_r = np.mean(r_vals) if r_vals else 0.0
        expectancy_d = np.mean(pnls)   if pnls   else 0.0

        # ── Drawdown ─────────────────────────────────────────────────────────
        max_dd, max_dd_pct, avg_dd = self._compute_drawdown(equity_curve)

        # ── Sharpe ratio ─────────────────────────────────────────────────────
        # Using trade-level returns (each trade = one period)
        sharpe = self._compute_sharpe(pnls, initial_capital)

        # ── Calmar ratio ─────────────────────────────────────────────────────
        calmar = (cagr * 100) / (max_dd_pct + 1e-10) if max_dd_pct > 0 else 0.0

        # ── Recovery factor ──────────────────────────────────────────────────
        recovery = (final_equity - initial_capital) / (max_dd + 1e-10) if max_dd > 0 else 0.0

        # ── Consecutive streaks ──────────────────────────────────────────────
        max_cw, max_cl = self._compute_streaks(pnls)

        # ── Breakdowns ───────────────────────────────────────────────────────
        by_session   = self._breakdown_by(trades, "session")
        by_direction = self._breakdown_by(trades, "direction")
        monthly_pnl  = self._monthly_breakdown(trades)

        metrics = {
            "initial_capital":    initial_capital,
            "final_equity":       round(final_equity, 2),
            "total_return_pct":   round(total_return * 100, 2),
            "cagr_pct":           round(cagr * 100, 2),
            "total_trades":       len(trades),
            "trading_days":       trading_days,
            "winners":            len(winners),
            "losers":             len(losers),
            "win_rate_pct":       round(win_rate, 1),
            "avg_winner":         round(avg_w, 2),
            "avg_loser":          round(avg_l, 2),
            "largest_winner":     round(max_w, 2),
            "largest_loser":      round(max_l, 2),
            "best_r":             round(best_r, 2),
            "worst_r":            round(worst_r, 2),
            "profit_factor":      round(profit_factor, 3),
            "expectancy_r":       round(expectancy_r, 3),
            "expectancy_dollar":  round(expectancy_d, 2),
            "sharpe_ratio":       round(sharpe, 3),
            "calmar_ratio":       round(calmar, 3),
            "max_drawdown_pct":   round(max_dd_pct, 2),
            "max_drawdown_dollar": round(max_dd, 2),
            "avg_drawdown_pct":   round(avg_dd, 2),
            "recovery_factor":    round(recovery, 3),
            "max_consec_wins":    max_cw,
            "max_consec_losses":  max_cl,
            "by_session":         by_session,
            "by_direction":       by_direction,
            "monthly_pnl":        monthly_pnl,
        }

        # ── Save trade log ───────────────────────────────────────────────────
        if self._cfg.get("backtest", {}).get("log_trades", True):
            self._save_trade_log(trades)

        if self._cfg.get("backtest", {}).get("save_equity_curve", True):
            self._save_equity_curve(equity_curve)

        return metrics

    def print_report(self, metrics: dict) -> None:
        """Pretty-print performance report to stdout."""
        sep = "─" * 60
        print(f"\n{sep}")
        print(f"  XAU/USD Price Action Bot — Backtest Performance Report")
        print(sep)

        def row(label, value):
            print(f"  {label:<35} {value}")

        print("\n  [Overview]")
        row("Initial Capital",        f"${metrics.get('initial_capital', 0):,.2f}")
        row("Final Equity",           f"${metrics.get('final_equity', 0):,.2f}")
        row("Total Return",           f"{metrics.get('total_return_pct', 0):+.2f}%")
        row("CAGR",                   f"{metrics.get('cagr_pct', 0):+.2f}%")
        row("Trading Days",           metrics.get("trading_days", 0))

        print("\n  [Trade Statistics]")
        row("Total Trades",           metrics.get("total_trades", 0))
        row("Winners / Losers",       f"{metrics.get('winners', 0)} / {metrics.get('losers', 0)}")
        row("Win Rate",               f"{metrics.get('win_rate_pct', 0):.1f}%")
        row("Avg Winner",             f"${metrics.get('avg_winner', 0):,.2f}")
        row("Avg Loser",              f"${metrics.get('avg_loser', 0):,.2f}")
        row("Largest Winner",         f"${metrics.get('largest_winner', 0):,.2f}")
        row("Largest Loser",          f"${metrics.get('largest_loser', 0):,.2f}")
        row("Best R",                 f"{metrics.get('best_r', 0):.2f}R")
        row("Worst R",                f"{metrics.get('worst_r', 0):.2f}R")

        print("\n  [Risk-Adjusted Performance]")
        row("Profit Factor",          f"{metrics.get('profit_factor', 0):.3f}")
        row("Expectancy (R)",         f"{metrics.get('expectancy_r', 0):.3f}R")
        row("Expectancy (USD)",       f"${metrics.get('expectancy_dollar', 0):,.2f}")
        row("Sharpe Ratio",           f"{metrics.get('sharpe_ratio', 0):.3f}")
        row("Calmar Ratio",           f"{metrics.get('calmar_ratio', 0):.3f}")
        row("Max Drawdown",           f"{metrics.get('max_drawdown_pct', 0):.2f}%  "
                                       f"(${metrics.get('max_drawdown_dollar', 0):,.2f})")
        row("Recovery Factor",        f"{metrics.get('recovery_factor', 0):.3f}")

        print("\n  [Streaks]")
        row("Max Consecutive Wins",   metrics.get("max_consec_wins", 0))
        row("Max Consecutive Losses", metrics.get("max_consec_losses", 0))

        print("\n  [Session Breakdown]")
        for sess, stats in metrics.get("by_session", {}).items():
            row(f"  {sess}", f"trades={stats['trades']}  wr={stats['win_rate']:.0f}%  "
                             f"pnl=${stats['total_pnl']:,.2f}")

        print("\n  [Direction Breakdown]")
        for d, stats in metrics.get("by_direction", {}).items():
            row(f"  {d}", f"trades={stats['trades']}  wr={stats['win_rate']:.0f}%  "
                          f"pnl=${stats['total_pnl']:,.2f}")

        print(f"\n{sep}\n")

    # ── Calculations ────────────────────────────────────────────────────────

    @staticmethod
    def _compute_drawdown(equity: list[float]) -> tuple[float, float, float]:
        if not equity:
            return 0.0, 0.0, 0.0
        eq = np.array(equity)
        peak = np.maximum.accumulate(eq)
        dd   = peak - eq
        dd_pct = dd / (peak + 1e-10) * 100
        max_dd      = float(dd.max())
        max_dd_pct  = float(dd_pct.max())
        avg_dd_pct  = float(dd_pct[dd_pct > 0].mean()) if (dd_pct > 0).any() else 0.0
        return max_dd, max_dd_pct, avg_dd_pct

    @staticmethod
    def _compute_sharpe(pnls: list[float], initial_capital: float,
                        risk_free_rate: float = 0.04) -> float:
        """
        Trade-level Sharpe: mean return per trade / std of returns.
        Using percentage returns to normalise for position sizing changes.
        """
        if len(pnls) < 2:
            return 0.0
        returns = np.array(pnls) / initial_capital
        mean_r  = returns.mean()
        std_r   = returns.std(ddof=1)
        if std_r < 1e-10:
            return 0.0
        # Annualise assuming ~252 trades/year (approximate)
        sharpe = (mean_r - risk_free_rate / 252) / std_r * np.sqrt(252)
        return float(sharpe)

    @staticmethod
    def _compute_streaks(pnls: list[float]) -> tuple[int, int]:
        max_w = max_l = cur_w = cur_l = 0
        for p in pnls:
            if p > 0:
                cur_w += 1; cur_l = 0
                max_w = max(max_w, cur_w)
            else:
                cur_l += 1; cur_w = 0
                max_l = max(max_l, cur_l)
        return max_w, max_l

    @staticmethod
    def _breakdown_by(trades: list[dict], key: str) -> dict:
        groups: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            groups[str(t.get(key, "unknown"))].append(t["pnl"])
        result = {}
        for k, pnls in groups.items():
            wins = [p for p in pnls if p > 0]
            result[k] = {
                "trades":    len(pnls),
                "win_rate":  len(wins) / len(pnls) * 100 if pnls else 0.0,
                "total_pnl": round(sum(pnls), 2),
                "avg_pnl":   round(np.mean(pnls), 2) if pnls else 0.0,
            }
        return result

    @staticmethod
    def _monthly_breakdown(trades: list[dict]) -> dict:
        monthly: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            month = t.get("open_time", "")[:7]   # "YYYY-MM"
            monthly[month].append(t["pnl"])
        return {
            m: round(sum(pnls), 2)
            for m, pnls in sorted(monthly.items())
        }

    # ── File I/O ─────────────────────────────────────────────────────────────

    def _save_trade_log(self, trades: list[dict]) -> None:
        if not trades:
            return
        out_dir = Path(self._output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "trade_log.csv"
        keys = list(trades[0].keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(trades)
        logger.info("Trade log saved: %s", path)

    def _save_equity_curve(self, equity: list[float]) -> None:
        if not equity:
            return
        out_dir = Path(self._output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "equity_curve.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["bar", "equity"])
            writer.writerows(enumerate(equity))
        logger.info("Equity curve saved: %s", path)
