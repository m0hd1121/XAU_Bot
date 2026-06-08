"""
data_handler.py
───────────────
Responsible for loading, validating, and preprocessing OHLC data.
Provides session tagging, volatility proxy, and candle classification —
all derived from raw price, zero indicator dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SessionLabel:
    name: str
    start: time
    end: time
    weight: float


@dataclass
class Candle:
    """Immutable snapshot of a single OHLC bar with derived metadata."""
    index: int
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    session: str
    session_weight: float
    body_size: float
    upper_wick: float
    lower_wick: float
    range_size: float
    is_bullish: bool
    is_bearish: bool
    is_doji: bool
    is_momentum: bool
    is_exhaustion: bool
    candle_type: str


# ─────────────────────────────────────────────────────────────────────────────
# DataHandler
# ─────────────────────────────────────────────────────────────────────────────

class DataHandler:
    """
    Loads and enriches OHLC data from CSV, ensuring it is clean and ready
    for market structure analysis. All derivations are pure price computation.
    """

    REQUIRED_COLUMNS = {"open", "high", "low", "close"}

    def __init__(self, cfg: dict) -> None:
        self._data_cfg = cfg.get("data", {})
        self._session_cfg = cfg.get("sessions", {})
        self._struct_cfg = cfg.get("market_structure", {})
        self._volatility_lookback: int = cfg.get("risk", {}).get("volatility_lookback", 14)
        self._sessions = self._build_sessions()
        self._df: Optional[pd.DataFrame] = None

    # ── Public API ──────────────────────────────────────────────────────────

    def load(self) -> pd.DataFrame:
        """Load raw OHLC data from configured source and return enriched DataFrame."""
        source = self._data_cfg.get("source", "csv")
        if source == "csv":
            df = self._load_csv()
        else:
            raise NotImplementedError(f"Data source '{source}' not yet implemented. Use 'csv'.")

        df = self._validate(df)
        df = self._enrich(df)
        self._df = df
        logger.info("Loaded %d bars (%s → %s)", len(df), df.index[0], df.index[-1])
        return df

    def get_candle(self, df: pd.DataFrame, i: int) -> Candle:
        """Return a typed Candle object for row index i."""
        row = df.iloc[i]
        return Candle(
            index=i,
            timestamp=df.index[i],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
            session=str(row["session"]),
            session_weight=float(row["session_weight"]),
            body_size=float(row["body_size"]),
            upper_wick=float(row["upper_wick"]),
            lower_wick=float(row["lower_wick"]),
            range_size=float(row["range_size"]),
            is_bullish=bool(row["is_bullish"]),
            is_bearish=bool(row["is_bearish"]),
            is_doji=bool(row["is_doji"]),
            is_momentum=bool(row["is_momentum"]),
            is_exhaustion=bool(row["is_exhaustion"]),
            candle_type=str(row["candle_type"]),
        )

    def slice(self, df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        """Return a date-filtered slice."""
        return df.loc[start:end]

    # ── Private: Loading ────────────────────────────────────────────────────

    def _load_csv(self) -> pd.DataFrame:
        path = Path(self._data_cfg.get("csv_path", "data/XAUUSD_H1.csv"))
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")

        date_col = self._data_cfg.get("date_column", "time")
        date_fmt = self._data_cfg.get("date_format", None)
        df = pd.read_csv(path, parse_dates=[date_col])
        df[date_col] = pd.to_datetime(df[date_col], format=date_fmt)
        df.set_index(date_col, inplace=True)
        df.sort_index(inplace=True)

        # Normalise column names to lowercase
        df.columns = [c.lower().strip() for c in df.columns]
        return df

    # ── Private: Validation ─────────────────────────────────────────────────

    def _validate(self, df: pd.DataFrame) -> pd.DataFrame:
        missing = self.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        before = len(df)
        # Remove rows with NaN OHLC
        df = df.dropna(subset=list(self.REQUIRED_COLUMNS))
        # OHLC sanity: high >= max(open,close) and low <= min(open,close)
        bad = (df["high"] < df[["open", "close"]].max(axis=1)) | \
              (df["low"]  > df[["open", "close"]].min(axis=1))
        if bad.any():
            logger.warning("Dropping %d rows with malformed OHLC", bad.sum())
            df = df[~bad]

        after = len(df)
        if before != after:
            logger.info("Validation removed %d rows", before - after)
        return df

    # ── Private: Enrichment ─────────────────────────────────────────────────

    def _enrich(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        o, h, l, c = df["open"], df["high"], df["low"], df["close"]

        # ── Candle geometry ─────────────────────────────────────────────────
        df["range_size"]  = h - l
        df["body_size"]   = (c - o).abs()
        df["upper_wick"]  = h - df[["open", "close"]].max(axis=1)
        df["lower_wick"]  = df[["open", "close"]].min(axis=1) - l
        df["body_ratio"]  = df["body_size"] / df["range_size"].replace(0, np.nan)

        # ── Candle direction ─────────────────────────────────────────────────
        df["is_bullish"] = c > o
        df["is_bearish"] = c < o

        # ── Doji: body <= 10% of range ───────────────────────────────────────
        df["is_doji"] = df["body_ratio"].fillna(0) < 0.10

        # ── Volatility proxy (rolling average true range — pure price math) ──
        prev_close = c.shift(1)
        true_range = pd.concat([
            h - l,
            (h - prev_close).abs(),
            (l - prev_close).abs(),
        ], axis=1).max(axis=1)
        df["atr_proxy"] = true_range.rolling(self._volatility_lookback, min_periods=1).mean()

        # ── Momentum vs Exhaustion candle classification ─────────────────────
        # Momentum: large body (>60% of range), low wick on direction side
        # Exhaustion: large wick (>40% of range) on direction side, small body
        body_ratio = df["body_ratio"].fillna(0)
        upper_ratio = df["upper_wick"] / df["range_size"].replace(0, np.nan)
        lower_ratio = df["lower_wick"] / df["range_size"].replace(0, np.nan)

        momentum_bull  = df["is_bullish"] & (body_ratio > 0.60) & (lower_ratio.fillna(1) < 0.20)
        momentum_bear  = df["is_bearish"] & (body_ratio > 0.60) & (upper_ratio.fillna(1) < 0.20)
        exhaust_bull   = df["is_bullish"] & (upper_ratio.fillna(0) > 0.40) & (body_ratio < 0.35)
        exhaust_bear   = df["is_bearish"] & (lower_ratio.fillna(0) > 0.40) & (body_ratio < 0.35)

        df["is_momentum"]   = momentum_bull | momentum_bear
        df["is_exhaustion"] = exhaust_bull  | exhaust_bear

        # ── Candle type label ────────────────────────────────────────────────
        conditions = [
            df["is_doji"],
            df["is_momentum"] & df["is_bullish"],
            df["is_momentum"] & df["is_bearish"],
            df["is_exhaustion"] & df["is_bullish"],
            df["is_exhaustion"] & df["is_bearish"],
        ]
        labels = ["doji", "momentum_bull", "momentum_bear", "exhaustion_bull", "exhaustion_bear"]
        df["candle_type"] = np.select(conditions, labels, default="neutral")

        # ── Session tagging ──────────────────────────────────────────────────
        df["session"], df["session_weight"] = zip(
            *df.index.map(self._tag_session)
        )

        return df

    # ── Private: Sessions ───────────────────────────────────────────────────

    def _build_sessions(self) -> list[SessionLabel]:
        sessions = []
        ordered = ["overlap", "london", "new_york", "asian"]
        for name in ordered:
            scfg = self._session_cfg.get(name, {})
            if not scfg:
                continue
            start_h, start_m = map(int, scfg["start"].split(":"))
            end_h,   end_m   = map(int, scfg["end"].split(":"))
            sessions.append(SessionLabel(
                name=name,
                start=time(start_h, start_m),
                end=time(end_h, end_m),
                weight=scfg.get("weight", 1.0),
            ))
        return sessions

    def _tag_session(self, ts: datetime) -> tuple[str, float]:
        t = ts.time()
        for sess in self._sessions:
            if sess.start <= t < sess.end:
                return sess.name, sess.weight
        return "off_hours", 0.2

    # ── Utility ─────────────────────────────────────────────────────────────

    @staticmethod
    def compute_volatility_proxy(df: pd.DataFrame, lookback: int = 14) -> pd.Series:
        """Standalone ATR-proxy computation on any OHLC DataFrame."""
        prev_c = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_c).abs(),
            (df["low"]  - prev_c).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(lookback, min_periods=1).mean()

    @staticmethod
    def detect_equal_levels(series: pd.Series, threshold_pct: float = 0.0015) -> pd.Series:
        """
        Returns boolean mask where each value is within threshold_pct of its
        neighbours — identifies 'equal' highs/lows for liquidity mapping.
        """
        mask = pd.Series(False, index=series.index)
        vals = series.values
        for i in range(1, len(vals) - 1):
            ratio_prev = abs(vals[i] - vals[i - 1]) / (vals[i - 1] + 1e-10)
            ratio_next = abs(vals[i] - vals[i + 1]) / (vals[i + 1] + 1e-10)
            if ratio_prev < threshold_pct or ratio_next < threshold_pct:
                mask.iloc[i] = True
        return mask
