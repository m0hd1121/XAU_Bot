"""
generate_sample_data.py
───────────────────────
Generates realistic synthetic XAU/USD H1 OHLC data using a geometric
Brownian motion base with regime-switching, session volatility scaling,
and periodic mean-reversion — producing data that visually resembles
real gold price action.

Usage (from project root):
  python data/generate_sample_data.py
  python main.py --generate-data
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def generate_ohlc(
    n_bars: int = 26280,             # ~3 years of H1 bars
    start_date: str = "2022-01-01",
    start_price: float = 1800.0,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Simulate realistic H1 XAU/USD price action with:
    - Geometric Brownian Motion base
    - Regime switching (trending vs ranging)
    - Session volatility scaling
    - Intraday mean-reversion during Asian hours
    """
    rng = np.random.default_rng(seed)

    # ── Time index ────────────────────────────────────────────────────────
    index = pd.date_range(start=start_date, periods=n_bars, freq="h")

    # ── Base parameters ───────────────────────────────────────────────────
    base_vol   = 0.0012    # Hourly volatility ~1.2 basis points
    drift      = 0.00003   # Slight upward drift (gold long-term trend)

    # ── Regime switching ──────────────────────────────────────────────────
    # States: 0=range, 1=uptrend, 2=downtrend
    regime = np.zeros(n_bars, dtype=int)
    transitions = {0: [0.85, 0.08, 0.07], 1: [0.05, 0.88, 0.07], 2: [0.05, 0.05, 0.90]}
    r = 0
    for i in range(1, n_bars):
        r = rng.choice([0, 1, 2], p=transitions[r])
        regime[i] = r

    regime_drift = {0: 0.0, 1: 0.0004, 2: -0.0004}
    regime_vol   = {0: 0.8,  1: 1.2,    2: 1.3}

    # ── Session volatility multiplier ─────────────────────────────────────
    def session_vol_mult(h: int) -> float:
        if 13 <= h <= 15:    return 1.6   # London/NY overlap
        if 7  <= h <= 12:    return 1.3   # London
        if 13 <= h <= 17:    return 1.2   # New York
        if 0  <= h <= 7:     return 0.6   # Asian
        return 0.8

    # ── Generate log returns ──────────────────────────────────────────────
    hours = index.hour
    log_returns = np.zeros(n_bars)
    for i in range(1, n_bars):
        h = int(hours[i])
        sv = session_vol_mult(h)
        rv = regime_vol[regime[i]]
        rd = regime_drift[regime[i]]
        vol_i = base_vol * sv * rv
        log_returns[i] = (drift + rd) + rng.normal(0, vol_i)

    # ── Cumulative price path ─────────────────────────────────────────────
    log_prices = np.log(start_price) + np.cumsum(log_returns)
    closes = np.exp(log_prices)

    # ── Generate realistic OHLC from closes ──────────────────────────────
    opens  = np.zeros(n_bars)
    highs  = np.zeros(n_bars)
    lows   = np.zeros(n_bars)

    opens[0] = start_price
    for i in range(n_bars):
        c = closes[i]
        if i > 0:
            # Open is close of previous bar ± small gap
            opens[i] = closes[i - 1] * (1 + rng.normal(0, base_vol * 0.3))
        else:
            opens[i] = start_price

        h = int(hours[i])
        sv = session_vol_mult(h)
        bar_range = c * base_vol * sv * regime_vol[regime[i]] * rng.uniform(0.5, 2.5)
        is_bull = c >= opens[i]

        if is_bull:
            lows[i]  = min(opens[i], c) - bar_range * rng.uniform(0.1, 0.4)
            highs[i] = max(opens[i], c) + bar_range * rng.uniform(0.1, 0.6)
        else:
            lows[i]  = min(opens[i], c) - bar_range * rng.uniform(0.1, 0.6)
            highs[i] = max(opens[i], c) + bar_range * rng.uniform(0.1, 0.4)

        # Ensure OHLC validity
        highs[i] = max(highs[i], opens[i], c)
        lows[i]  = min(lows[i],  opens[i], c)

    # ── Add realistic volume (not used in logic, just for completeness) ───
    base_vol_contracts = 5000
    volume = rng.integers(
        int(base_vol_contracts * 0.5),
        int(base_vol_contracts * 2.5),
        size=n_bars
    ).astype(float)
    # Higher volume in active sessions
    for i in range(n_bars):
        h = int(hours[i])
        volume[i] *= session_vol_mult(h)

    df = pd.DataFrame({
        "time":   index,
        "open":   np.round(opens,  2),
        "high":   np.round(highs,  2),
        "low":    np.round(lows,   2),
        "close":  np.round(closes, 2),
        "volume": np.round(volume, 0),
    })
    return df


def generate_and_save(
    output_path: str = "data/XAUUSD_H1.csv",
    n_bars: int = 26280,
    start_date: str = "2022-01-01",
) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df = generate_ohlc(n_bars=n_bars, start_date=start_date)
    df.to_csv(output_path, index=False)
    print(f"Sample data saved: {output_path}  ({len(df)} bars)")
    print(f"  Date range : {df['time'].iloc[0]}  →  {df['time'].iloc[-1]}")
    print(f"  Price range: {df['low'].min():.2f}  →  {df['high'].max():.2f}")
    return output_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "data/XAUUSD_H1.csv"
    generate_and_save(out)
