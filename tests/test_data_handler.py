"""Tests for DataHandler — OHLC loading and enrichment."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from io import StringIO
from unittest.mock import patch, MagicMock
from pathlib import Path

from xau_bot.data_handler import DataHandler


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_CSV = """time,open,high,low,close,volume
2023-01-02 08:00:00,1820.0,1825.0,1815.0,1822.0,5000
2023-01-02 09:00:00,1822.0,1830.0,1818.0,1828.0,4800
2023-01-02 10:00:00,1828.0,1828.5,1810.0,1812.0,6200
2023-01-02 11:00:00,1812.0,1815.0,1808.0,1814.0,3900
2023-01-02 12:00:00,1814.0,1820.0,1813.0,1819.0,4200
2023-01-02 13:00:00,1819.0,1835.0,1817.0,1832.0,7100
2023-01-02 14:00:00,1832.0,1845.0,1829.0,1841.0,8200
2023-01-02 15:00:00,1841.0,1842.0,1820.0,1821.0,5500
"""

CFG = {
    "data": {
        "source": "csv",
        "csv_path": "/tmp/test_xau.csv",
        "date_column": "time",
        "date_format": None,
    },
    "sessions": {
        "london":   {"start": "07:00", "end": "12:00", "weight": 1.0},
        "new_york": {"start": "13:00", "end": "17:00", "weight": 1.0},
        "overlap":  {"start": "13:00", "end": "15:00", "weight": 1.2},
        "asian":    {"start": "00:00", "end": "07:00", "weight": 0.3},
    },
    "market_structure": {},
    "risk": {"volatility_lookback": 3},
}


@pytest.fixture
def sample_csv(tmp_path):
    p = tmp_path / "test_xau.csv"
    p.write_text(SAMPLE_CSV)
    return str(p)


@pytest.fixture
def handler(sample_csv):
    cfg = dict(CFG)
    cfg["data"] = dict(CFG["data"])
    cfg["data"]["csv_path"] = sample_csv
    return DataHandler(cfg)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDataHandler:

    def test_load_returns_dataframe(self, handler):
        df = handler.load()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 8

    def test_required_columns_present(self, handler):
        df = handler.load()
        for col in ("open", "high", "low", "close"):
            assert col in df.columns

    def test_enriched_columns_present(self, handler):
        df = handler.load()
        expected = ["body_size", "range_size", "upper_wick", "lower_wick",
                    "is_bullish", "is_bearish", "is_doji", "candle_type",
                    "session", "session_weight", "atr_proxy"]
        for col in expected:
            assert col in df.columns, f"Missing column: {col}"

    def test_ohlc_sanity(self, handler):
        df = handler.load()
        assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
        assert (df["low"]  <= df[["open", "close"]].min(axis=1)).all()

    def test_range_size_correct(self, handler):
        df = handler.load()
        expected = df["high"] - df["low"]
        pd.testing.assert_series_equal(df["range_size"], expected, check_names=False)

    def test_body_size_non_negative(self, handler):
        df = handler.load()
        assert (df["body_size"] >= 0).all()

    def test_session_tagging(self, handler):
        df = handler.load()
        # 08:00 UTC → London session
        assert df.iloc[0]["session"] == "london"
        # 13:00 UTC → overlap
        assert df.iloc[5]["session"] == "overlap"

    def test_candle_direction(self, handler):
        df = handler.load()
        bullish_mask = df["close"] > df["open"]
        assert (df.loc[bullish_mask, "is_bullish"] == True).all()
        bearish_mask = df["close"] < df["open"]
        assert (df.loc[bearish_mask, "is_bearish"] == True).all()

    def test_atr_proxy_positive(self, handler):
        df = handler.load()
        assert (df["atr_proxy"] > 0).all()

    def test_candle_type_labels(self, handler):
        df = handler.load()
        valid = {"doji", "momentum_bull", "momentum_bear",
                 "exhaustion_bull", "exhaustion_bear", "neutral"}
        assert set(df["candle_type"].unique()).issubset(valid)

    def test_get_candle(self, handler):
        df = handler.load()
        candle = handler.get_candle(df, 0)
        assert candle.open  == df.iloc[0]["open"]
        assert candle.high  == df.iloc[0]["high"]
        assert candle.low   == df.iloc[0]["low"]
        assert candle.close == df.iloc[0]["close"]

    def test_missing_file_raises(self, tmp_path):
        cfg = dict(CFG)
        cfg["data"] = {"source": "csv", "csv_path": str(tmp_path / "nonexistent.csv")}
        handler = DataHandler(cfg)
        with pytest.raises(FileNotFoundError):
            handler.load()

    def test_volatility_proxy_static(self):
        df = pd.DataFrame({
            "open":  [100, 102, 101],
            "high":  [105, 107, 104],
            "low":   [98,  100,  99],
            "close": [103, 105, 102],
        })
        result = DataHandler.compute_volatility_proxy(df, lookback=2)
        assert len(result) == 3
        assert (result > 0).all()


class TestEqualLevelDetection:

    def test_detects_equal_highs(self):
        prices = pd.Series([1800, 1820, 1820.5, 1821, 1800])
        mask = DataHandler.detect_equal_levels(prices, threshold_pct=0.001)
        # Middle values that are close to each other should be flagged
        assert mask.iloc[1] or mask.iloc[2] or mask.iloc[3]

    def test_no_false_positives_on_large_swings(self):
        prices = pd.Series([1800, 1850, 1750, 1900, 1700])
        mask = DataHandler.detect_equal_levels(prices, threshold_pct=0.001)
        assert not mask.any()
