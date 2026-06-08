"""
regime_detector.py
──────────────────
Detects the current market regime from raw OHLC price action.
No indicators — all derived from price structure and range analysis.

Regimes:
  STRONG_TREND   — clear HH/HL or LH/LL sequence, consistent direction
  WEAK_TREND     — mild directional bias, inconsistent structure
  RANGING        — price compressing within a horizontal band
  HIGH_VOLATILITY — ATR significantly above baseline
  LOW_VOLATILITY  — ATR significantly below baseline
  CHOPPY          — frequent structure violations, no follow-through

Volatility sub-label (independent of trend label):
  VOL_HIGH / VOL_NORMAL / VOL_LOW

The detector is stateless per call — safe for concurrent use.
It maintains a history internally only for rolling statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Regime(Enum):
    STRONG_TREND    = "STRONG_TREND"
    WEAK_TREND      = "WEAK_TREND"
    RANGING         = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY  = "LOW_VOLATILITY"
    CHOPPY          = "CHOPPY"
    UNKNOWN         = "UNKNOWN"


class VolRegime(Enum):
    HIGH   = "VOL_HIGH"
    NORMAL = "VOL_NORMAL"
    LOW    = "VOL_LOW"


@dataclass
class RegimeSnapshot:
    regime:            Regime
    vol_regime:        VolRegime
    trend_strength:    float    # 0–1; 0 = no trend, 1 = strong trend
    atr_ratio:         float    # current ATR / baseline ATR
    hh_hl_score:       float    # fraction of recent swings forming HH/HL
    lh_ll_score:       float    # fraction of recent swings forming LH/LL
    range_compression: float    # recent range / baseline range
    description:       str      # human-readable one-liner


class RegimeDetector:
    """
    Analyzes a window of OHLC bars to classify market regime.
    """

    def __init__(self, cfg: dict = None) -> None:
        mc = (cfg or {}).get("market_structure", {})
        self._swing_lookback    = mc.get("swing_lookback", 5)
        self._vol_lookback      = 14
        self._vol_baseline      = 50
        self._regime_window     = 40      # bars for regime analysis
        self._choppiness_window = 20      # bars for choppiness scoring

    # ── Public API ───────────────────────────────────────────────────────────

    def detect(self, df: pd.DataFrame, current_bar: int) -> RegimeSnapshot:
        """
        Classify regime using price data up to (and including) current_bar.
        Returns a RegimeSnapshot immediately usable by the learning engine.
        """
        n = min(current_bar + 1, len(df))
        if n < self._swing_lookback * 3:
            return RegimeSnapshot(Regime.UNKNOWN, VolRegime.NORMAL, 0.0, 1.0, 0.5, 0.5, 1.0,
                                  "Insufficient data")

        window = df.iloc[max(0, n - self._regime_window): n]

        atr_ratio, vol_regime = self._vol_regime(df, current_bar)
        hh_hl, lh_ll          = self._structure_scores(window)
        compression           = self._range_compression(df, current_bar)
        choppiness            = self._choppiness_score(window)

        # ── Classification ────────────────────────────────────────────────────
        trend_strength = max(hh_hl, lh_ll)

        if vol_regime == VolRegime.HIGH and atr_ratio > 1.8:
            regime = Regime.HIGH_VOLATILITY
        elif vol_regime == VolRegime.LOW and compression < 0.5:
            regime = Regime.LOW_VOLATILITY
        elif choppiness > 0.60:
            regime = Regime.CHOPPY
        elif compression < 0.55 and trend_strength < 0.55:
            regime = Regime.RANGING
        elif trend_strength >= 0.70:
            regime = Regime.STRONG_TREND
        elif trend_strength >= 0.50:
            regime = Regime.WEAK_TREND
        else:
            regime = Regime.RANGING

        desc = self._describe(regime, vol_regime, trend_strength, atr_ratio, hh_hl, lh_ll)

        return RegimeSnapshot(
            regime=regime,
            vol_regime=vol_regime,
            trend_strength=trend_strength,
            atr_ratio=atr_ratio,
            hh_hl_score=hh_hl,
            lh_ll_score=lh_ll,
            range_compression=compression,
            description=desc,
        )

    # ── Private: Volatility ──────────────────────────────────────────────────

    def _vol_regime(self, df: pd.DataFrame, i: int) -> tuple[float, VolRegime]:
        """ATR ratio = recent ATR / long-term ATR baseline."""
        if i < self._vol_lookback:
            return 1.0, VolRegime.NORMAL
        atr_series = df["atr_proxy"] if "atr_proxy" in df.columns else (df["high"] - df["low"])
        recent_atr   = float(atr_series.iloc[max(0, i - self._vol_lookback + 1): i + 1].mean())
        baseline_atr = float(atr_series.iloc[max(0, i - self._vol_baseline + 1): i + 1].mean())
        ratio = recent_atr / (baseline_atr + 1e-10)

        if ratio > 1.5:
            return ratio, VolRegime.HIGH
        if ratio < 0.6:
            return ratio, VolRegime.LOW
        return ratio, VolRegime.NORMAL

    # ── Private: Structure scores ─────────────────────────────────────────────

    def _structure_scores(self, window: pd.DataFrame) -> tuple[float, float]:
        """
        Score HH/HL and LH/LL tendencies from recent swing pairs.
        Returns (bullish_score, bearish_score) each in [0, 1].
        """
        highs  = window["high"].values
        lows   = window["low"].values
        closes = window["close"].values
        n = len(highs)

        if n < 6:
            return 0.5, 0.5

        lb = min(self._swing_lookback, 2)
        swing_h_prices = []
        swing_l_prices = []

        for i in range(lb, n - lb):
            if highs[i] == highs[i - lb:i + lb + 1].max():
                swing_h_prices.append(highs[i])
            if lows[i] == lows[i - lb:i + lb + 1].min():
                swing_l_prices.append(lows[i])

        def _trend_score(prices: list[float]) -> tuple[float, float]:
            if len(prices) < 2:
                return 0.5, 0.5
            up = sum(1 for a, b in zip(prices, prices[1:]) if b > a)
            dn = sum(1 for a, b in zip(prices, prices[1:]) if b < a)
            total = len(prices) - 1
            return up / total, dn / total

        hh_score, _ = _trend_score(swing_h_prices)
        hl_score, _ = _trend_score(swing_l_prices)
        lh_score = 1 - hh_score
        ll_score = 1 - hl_score

        bullish = (hh_score + hl_score) / 2
        bearish = (lh_score + ll_score) / 2
        return round(bullish, 3), round(bearish, 3)

    # ── Private: Range compression ────────────────────────────────────────────

    def _range_compression(self, df: pd.DataFrame, i: int) -> float:
        """
        Ratio: recent range / baseline range.
        < 0.5 = compressed (ranging). > 1.5 = expanding (trending/volatile).
        """
        if i < self._vol_baseline:
            return 1.0
        recent_range   = float(df["high"].iloc[max(0, i - 20): i + 1].max()
                               - df["low"].iloc[max(0, i - 20): i + 1].min())
        baseline_range = float(df["high"].iloc[max(0, i - self._vol_baseline): i + 1].max()
                               - df["low"].iloc[max(0, i - self._vol_baseline): i + 1].min())
        return recent_range / (baseline_range + 1e-10)

    # ── Private: Choppiness score ─────────────────────────────────────────────

    def _choppiness_score(self, window: pd.DataFrame) -> float:
        """
        Choppiness index (pure price): ratio of summed candle ranges to
        the overall high-low range. Values near 1 = choppy; near 0 = trending.
        """
        n = len(window)
        if n < 4:
            return 0.5
        tr_sum = (window["high"] - window["low"]).sum()
        total  = window["high"].max() - window["low"].min()
        if total < 1e-10:
            return 1.0
        ratio = tr_sum / total / n
        # Normalize: pure trending ≈ 1.0, choppy ≈ 2.0+ → map to [0,1]
        return min(1.0, max(0.0, (ratio - 1.0)))

    # ── Human-readable description ────────────────────────────────────────────

    @staticmethod
    def _describe(regime: Regime, vol: VolRegime, ts: float,
                  atr_r: float, hh: float, lh: float) -> str:
        vol_str = {"VOL_HIGH": "elevated", "VOL_NORMAL": "normal", "VOL_LOW": "compressed"}[vol.value]
        dirn = "bullish" if hh >= lh else "bearish"
        return (f"{regime.value} | {vol_str} volatility (ATR×{atr_r:.2f}) | "
                f"{dirn} bias (strength {ts:.0%})")
