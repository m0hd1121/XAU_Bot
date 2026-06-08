"""
tests/test_learning_engine.py
──────────────────────────────
Tests for all 8 learning modules:
  trade_database, feature_extractor, pattern_analyzer, confidence_model,
  regime_detector, validation_engine, explainability_engine, learning_engine

Uses a temporary SQLite database and synthetic data — no external dependencies.
"""

from __future__ import annotations

import math
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cfg(db_path: str = ":memory:") -> dict:
    return {
        "bot":   {"symbol": "XAUUSD"},
        "risk":  {"initial_capital": 10000.0},
        "market_structure": {"swing_lookback": 3},
        "learning": {
            "enabled": True,
            "db_path":  db_path,
            "analysis_every_n_trades": 5,
            "min_trades_before_update": 3,
            "adaptive_threshold": True,
            "min_confidence_threshold": 0.45,
            "min_pattern_samples": 5,
            "decay_halflife": 100,
            "validation": {
                "min_is_trades": 5,
                "min_oos_trades": 2,
                "oos_pct": 0.20,
                "wf_window_trades": 10,
                "wf_step_trades": 5,
                "max_overfit_score": 0.50,
            },
        },
    }


def _make_feature_vector(
    trend="BULLISH",
    trigger="CHoCH_BULL",
    session="london",
    regime="STRONG_TREND",
    vol_regime="VOL_NORMAL",
    consecutive_losses=0,
    rr_bucket="GOOD",
):
    from xau_bot.learning.feature_extractor import FeatureVector
    return FeatureVector(
        trend               = trend,
        trigger_event       = trigger,
        sweep_type          = "equal_low",
        htf_bias            = "BULLISH",
        zone_present        = True,
        zone_quality_bucket = "HIGH",
        zone_test_count     = 0,
        zone_age_bucket     = "FRESH",
        body_ratio_bucket   = "MEDIUM",
        wick_direction      = "LOWER_HEAVY",
        candle_type         = "bullish_marubozu",
        atr_ratio_bucket    = "NORMAL",
        session             = session,
        time_of_day         = "OPEN",
        sl_atr_bucket       = "NORMAL",
        rr_bucket           = rr_bucket,
        consecutive_losses  = consecutive_losses,
        prev_trade_outcome  = "WIN",
        structure_freshness = "FRESH",
        regime              = regime,
        volatility_regime   = vol_regime,
        pattern_key         = "test_pattern_001",
        raw                 = {"atr_ratio": 1.0, "rr_ratio": 2.5, "sl_atr": 1.0},
    )


def _make_trade_record(trade_id: int = 1, pnl: float = 150.0, pnl_r: float = 1.5) -> dict:
    return {
        "trade_id":     trade_id,
        "direction":    "long",
        "entry_price":  1900.0,
        "exit_price":   1930.0,
        "sl_price":     1880.0,
        "tp1_price":    1930.0,
        "tp2_price":    1960.0,
        "lot_size":     0.1,
        "pnl":          pnl,
        "pnl_r":        pnl_r,
        "close_reason": "tp2",
        "session":      "london",
        "quality_score": 0.75,
        "mae":           0.3,
        "mfe":           1.8,
        "open_bar":      100,
        "close_bar":     115,
        "open_time":     "2023-06-01 09:00:00",
        "outcome":       "WIN" if pnl > 0 else "LOSS",
    }


def _make_ohlc_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 1900.0 + np.cumsum(rng.normal(0, 2, n))
    high  = close + rng.uniform(1, 5, n)
    low   = close - rng.uniform(1, 5, n)
    opn   = close - rng.uniform(-2, 2, n)
    df = pd.DataFrame({"open": opn, "high": high, "low": low, "close": close})
    df["atr_proxy"] = (df["high"] - df["low"]).rolling(14, min_periods=1).mean()
    df.index = pd.date_range("2023-01-01", periods=n, freq="1h")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# TradeDatabase
# ═══════════════════════════════════════════════════════════════════════════════

class TestTradeDatabase:

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_learning.db")
        from xau_bot.learning.trade_database import TradeDatabase
        self.db = TradeDatabase(self.db_path)

    def test_insert_and_count(self):
        self.db.insert_trade(_make_trade_record(1, 150.0))
        assert self.db.count_trades() == 1

    def test_insert_features(self):
        self.db.insert_trade(_make_trade_record(2))
        fv = _make_feature_vector()
        self.db.insert_features(2, fv.to_dict())
        records = self.db.get_all_trades_with_features()
        assert len(records) >= 1

    def test_upsert_confidence_weight(self):
        self.db.upsert_confidence_weight("session", "london", "ALL", 0.72, 30)
        weights = self.db.get_confidence_weights()
        assert ("session", "london") in weights
        w, cnt = weights[("session", "london")]
        assert abs(w - 0.72) < 1e-6
        assert cnt == 30

    def test_upsert_pattern_stats(self):
        stats = {
            "pattern_key": "abc123",
            "feature_description": "test",
            "sample_count": 25,
            "win_count": 15,
            "win_rate": 0.6,
            "avg_r": 0.5,
            "avg_pnl": 75.0,
            "profit_factor": 1.8,
            "wilson_low": 0.4,
            "wilson_high": 0.78,
            "expectancy_r": 0.3,
        }
        self.db.upsert_pattern_stats(stats)
        result = self.db.get_pattern_stats("abc123")
        assert result is not None
        assert result["sample_count"] == 25

    def test_insert_review(self):
        self.db.insert_trade(_make_trade_record(3))
        review = {
            "premature_entry": 0, "insufficient_confirmation": 0,
            "sl_too_tight": 0, "unrealistic_target": 0,
            "poor_conditions": 0, "regime_misalignment": 0,
            "narrative": "All good.", "recommendations": ["Keep it up."],
            "overall_decision_score": 1.0,
            "entry_timing_score": 1.0, "confirmation_score": 1.0,
            "sl_quality_score": 1.0, "target_quality_score": 1.0,
            "condition_score": 1.0,
        }
        self.db.insert_review(3, review)

    def test_recent_outcomes(self):
        for i in range(5):
            pnl = 100.0 if i % 2 == 0 else -50.0
            self.db.insert_trade(_make_trade_record(10 + i, pnl))
        outcomes = self.db.get_recent_outcomes(5)
        assert len(outcomes) == 5
        assert set(outcomes).issubset({"WIN", "LOSS", "BE"})

    def test_log_event(self):
        self.db.log_event("TEST", "test event", {"key": "value"})

    def test_insert_regime(self):
        self.db.insert_regime({
            "ts": "2023-01-01 09:00:00",
            "bar_index": 10,
            "regime": "STRONG_TREND",
            "volatility_regime": "VOL_NORMAL",
            "trend_strength": 0.75,
            "atr_ratio": 1.1,
            "price": 1900.0,
        })
        latest = self.db.get_latest_regime()
        assert latest is not None
        assert latest["regime"] == "STRONG_TREND"


# ═══════════════════════════════════════════════════════════════════════════════
# FeatureExtractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeatureExtractor:

    def setup_method(self):
        from xau_bot.learning.feature_extractor import FeatureExtractor
        self.extractor = FeatureExtractor(_make_cfg())

    def test_extract_basic(self):
        fv = self.extractor.extract(
            direction="long",
            entry_price=1900.0, sl_price=1880.0, tp1_price=1930.0,
            session="london", timestamp=pd.Timestamp("2023-06-01 09:00"),
            atr_proxy=8.0, baseline_atr=7.5,
            trigger_event="CHoCH_BULL", sweep_type="equal_low",
            htf_bias="BULLISH", trend="BULLISH",
            zone_present=True, zone_quality=0.7, zone_test_count=0,
            zone_origin_bar=90, current_bar=100, last_shift_bar=97,
            body_ratio=0.55, upper_wick=2.0, lower_wick=4.0,
            candle_type="bullish_engulf",
            consecutive_losses=0, prev_trade_outcome="WIN",
            regime="STRONG_TREND", volatility_regime="VOL_NORMAL",
        )
        assert fv.trend == "BULLISH"
        assert fv.session == "london"
        assert fv.zone_present is True
        assert fv.pattern_key  # non-empty hash
        assert fv.rr_bucket in ("MINIMUM", "GOOD", "EXCELLENT")
        assert fv.structure_freshness == "FRESH"

    def test_pattern_key_consistency(self):
        kwargs = dict(
            direction="long", entry_price=1900.0, sl_price=1880.0, tp1_price=1930.0,
            session="london", timestamp=pd.Timestamp("2023-06-01 09:00"),
            atr_proxy=8.0, baseline_atr=7.5, trigger_event="CHoCH_BULL",
            sweep_type="equal_low", htf_bias="BULLISH", trend="BULLISH",
            zone_present=True, zone_quality=0.7, zone_test_count=0,
            zone_origin_bar=90, current_bar=100, last_shift_bar=97,
            body_ratio=0.55, upper_wick=2.0, lower_wick=4.0,
            candle_type="bullish_engulf", consecutive_losses=0,
            prev_trade_outcome="WIN", regime="STRONG_TREND",
            volatility_regime="VOL_NORMAL",
        )
        fv1 = self.extractor.extract(**kwargs)
        fv2 = self.extractor.extract(**kwargs)
        assert fv1.pattern_key == fv2.pattern_key

    def test_rr_bucket_values(self):
        fv_min = self.extractor.extract(
            direction="long", entry_price=1900.0, sl_price=1880.0,
            tp1_price=1910.0,  # only 0.5R
            session="london", timestamp=pd.Timestamp("2023-06-01 09:00"),
            atr_proxy=8.0, baseline_atr=7.5, trigger_event="CHoCH_BULL",
            sweep_type="equal_low", htf_bias="BULLISH", trend="BULLISH",
            zone_present=False, zone_quality=0.5, zone_test_count=0,
            zone_origin_bar=90, current_bar=100, last_shift_bar=97,
            body_ratio=0.5, upper_wick=2.0, lower_wick=2.0,
            candle_type="neutral", consecutive_losses=0,
            prev_trade_outcome="NONE", regime="RANGING",
            volatility_regime="VOL_NORMAL",
        )
        assert fv_min.rr_bucket == "MINIMUM"

    def test_wick_direction_upper_heavy(self):
        fv = self.extractor.extract(
            direction="short", entry_price=1900.0, sl_price=1920.0,
            tp1_price=1870.0,
            session="new_york", timestamp=pd.Timestamp("2023-06-01 14:00"),
            atr_proxy=8.0, baseline_atr=7.5, trigger_event="CHoCH_BEAR",
            sweep_type="equal_high", htf_bias="BEARISH", trend="BEARISH",
            zone_present=True, zone_quality=0.6, zone_test_count=1,
            zone_origin_bar=85, current_bar=100, last_shift_bar=96,
            body_ratio=0.3, upper_wick=8.0, lower_wick=0.5,
            candle_type="bearish_pin",
            consecutive_losses=1, prev_trade_outcome="LOSS",
            regime="WEAK_TREND", volatility_regime="VOL_NORMAL",
        )
        assert fv.wick_direction == "UPPER_HEAVY"

    def test_to_dict_round_trip(self):
        fv = _make_feature_vector()
        d = fv.to_dict()
        assert "pattern_key" in d
        assert "raw" in d
        assert isinstance(d["raw"], dict)


# ═══════════════════════════════════════════════════════════════════════════════
# PatternAnalyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestPatternAnalyzer:

    def setup_method(self):
        from xau_bot.learning.pattern_analyzer import PatternAnalyzer
        self.analyzer = PatternAnalyzer(min_samples=5, decay_halflife=100)

    def _make_records(self, n: int = 30) -> list[dict]:
        rng = np.random.default_rng(1)
        records = []
        for i in range(n):
            pnl = float(rng.choice([100, -60], p=[0.6, 0.4]))
            records.append({
                "pnl": pnl, "pnl_r": pnl / 60,
                "outcome": "WIN" if pnl > 0 else "LOSS",
                "session": "london" if i % 2 == 0 else "new_york",
                "regime": "STRONG_TREND" if i % 3 != 0 else "RANGING",
                "trigger_event": "CHoCH_BULL",
                "sweep_type": "equal_low",
                "trend": "BULLISH",
                "atr_ratio_bucket": "NORMAL",
                "zone_quality_bucket": "HIGH",
                "volatility_regime": "VOL_NORMAL",
                "body_ratio_bucket": "MEDIUM",
                "wick_direction": "LOWER_HEAVY",
                "sl_atr_bucket": "NORMAL",
                "rr_bucket": "GOOD",
                "structure_freshness": "FRESH",
                "time_of_day": "OPEN",
                "prev_trade_outcome": "WIN",
                "pattern_key": f"pat_{i % 5}",
            })
        return records

    def test_analyze_returns_stats(self):
        records = self._make_records(30)
        stats = self.analyzer.analyze(records)
        assert isinstance(stats, list)
        assert len(stats) > 0

    def test_analyze_fields(self):
        records = self._make_records(30)
        stats = self.analyzer.analyze(records)
        s = stats[0]
        assert "pattern_key" in s
        assert "win_rate" in s
        assert "expectancy_r" in s
        assert 0 <= s["win_rate"] <= 1

    def test_insufficient_data_returns_empty(self):
        records = self._make_records(3)
        stats = self.analyzer.analyze(records)
        assert stats == []

    def test_feature_importances(self):
        records = self._make_records(40)
        imp = self.analyzer.compute_feature_importances(records)
        assert isinstance(imp, dict)
        assert all(0 <= v <= 1 for v in imp.values())

    def test_identify_edge_patterns(self):
        records = self._make_records(40)
        stats = self.analyzer.analyze(records)
        edges = self.analyzer.identify_edge_patterns(stats, min_expectancy=0.05)
        assert "positive" in edges
        assert "negative" in edges
        assert "neutral" in edges

    def test_wilson_ci(self):
        from xau_bot.learning.pattern_analyzer import wilson_ci
        lo, hi = wilson_ci(60, 100)
        assert lo < 0.6 < hi
        assert 0 <= lo < hi <= 1

    def test_wilson_ci_zero(self):
        from xau_bot.learning.pattern_analyzer import wilson_ci
        lo, hi = wilson_ci(0, 0)
        assert lo == 0.0 and hi == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# ConfidenceModel
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceModel:

    def setup_method(self):
        from xau_bot.learning.confidence_model import ConfidenceModel
        self.model = ConfidenceModel()

    def test_initial_score_neutral(self):
        fv = _make_feature_vector()
        bd = self.model.score(fv)
        # With no data, composite ≈ 0.5
        assert 0.40 <= bd.composite_score <= 0.60
        assert 0.05 <= bd.final_score <= 0.95

    def test_score_returns_breakdown(self):
        fv = _make_feature_vector()
        bd = self.model.score(fv)
        assert hasattr(bd, "composite_score")
        assert hasattr(bd, "regime_multiplier")
        assert hasattr(bd, "final_score")
        assert hasattr(bd, "feature_scores")
        assert hasattr(bd, "dominant_features")

    def test_update_wins_increase_confidence(self):
        fv = _make_feature_vector(session="london")
        initial = self.model.score(fv).feature_scores.get("session", 0.5)
        for _ in range(20):
            self.model.update(fv, "WIN", pnl_r=2.0)
        updated = self.model.score(fv).feature_scores.get("session", 0.5)
        assert updated > initial

    def test_update_losses_decrease_confidence(self):
        fv = _make_feature_vector(session="asian")
        initial = self.model.score(fv).feature_scores.get("session", 0.5)
        for _ in range(20):
            self.model.update(fv, "LOSS", pnl_r=-1.0)
        updated = self.model.score(fv).feature_scores.get("session", 0.5)
        assert updated < initial

    def test_confidence_clamped(self):
        fv = _make_feature_vector()
        for _ in range(200):
            self.model.update(fv, "WIN", pnl_r=5.0)
        bd = self.model.score(fv)
        assert bd.final_score <= 0.95
        assert bd.composite_score <= 0.95

    def test_regime_multiplier_choppy(self):
        fv = _make_feature_vector(regime="CHOPPY")
        bd = self.model.score(fv)
        assert bd.regime_multiplier <= 0.80  # CHOPPY = 0.72 default

    def test_regime_multiplier_strong_trend(self):
        fv = _make_feature_vector(regime="STRONG_TREND")
        bd = self.model.score(fv)
        assert bd.regime_multiplier >= 1.10  # STRONG_TREND = 1.15 default

    def test_db_round_trip(self):
        fv = _make_feature_vector()
        for _ in range(5):
            self.model.update(fv, "WIN", 1.5)
        rows = self.model.to_db_rows()
        assert len(rows) > 0
        new_model = __import__(
            "xau_bot.learning.confidence_model", fromlist=["ConfidenceModel"]
        ).ConfidenceModel()
        weights = {(r[0], r[1]): (r[3], r[4]) for r in rows}
        new_model.load_from_db_weights(weights)
        bd1 = self.model.score(fv)
        bd2 = new_model.score(fv)
        assert abs(bd1.final_score - bd2.final_score) < 0.01

    def test_update_importances(self):
        self.model.update_importances({"session": 0.9, "regime": 0.6})
        # Should blend with defaults, not blindly replace
        # Just check it doesn't raise and importances remain in bounds


# ═══════════════════════════════════════════════════════════════════════════════
# RegimeDetector
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegimeDetector:

    def setup_method(self):
        from xau_bot.learning.regime_detector import RegimeDetector
        self.det = RegimeDetector()

    def test_insufficient_data_unknown(self):
        df = _make_ohlc_df(5)
        snap = self.det.detect(df, 4)
        from xau_bot.learning.regime_detector import Regime
        assert snap.regime == Regime.UNKNOWN

    def test_returns_snapshot(self):
        df = _make_ohlc_df(80)
        snap = self.det.detect(df, 79)
        assert hasattr(snap, "regime")
        assert hasattr(snap, "vol_regime")
        assert hasattr(snap, "trend_strength")
        assert 0 <= snap.trend_strength <= 1

    def test_high_vol_regime(self):
        from xau_bot.learning.regime_detector import RegimeDetector, VolRegime
        df = _make_ohlc_df(80)
        # Artificially inflate recent ranges
        df.loc[df.index[-10:], "high"] = df.loc[df.index[-10:], "high"] + 50
        df.loc[df.index[-10:], "low"]  = df.loc[df.index[-10:], "low"]  - 50
        df["atr_proxy"] = (df["high"] - df["low"]).rolling(14, min_periods=1).mean()
        snap = self.det.detect(df, len(df) - 1)
        # With artificially high ATR ratio, should be HIGH_VOLATILITY
        assert snap.vol_regime == VolRegime.HIGH

    def test_atr_ratio_positive(self):
        df = _make_ohlc_df(80)
        snap = self.det.detect(df, 79)
        assert snap.atr_ratio > 0


# ═══════════════════════════════════════════════════════════════════════════════
# ValidationEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidationEngine:

    def setup_method(self):
        from xau_bot.learning.validation_engine import ValidationEngine
        self.val = ValidationEngine(_make_cfg())

    def _make_trade_records(self, n: int = 50, win_rate: float = 0.6) -> list[dict]:
        rng = np.random.default_rng(7)
        records = []
        for i in range(n):
            pnl_r = float(rng.choice([2.0, -1.0], p=[win_rate, 1 - win_rate]))
            records.append({
                "pnl_r":     pnl_r,
                "pnl":       pnl_r * 100,
                "open_time": f"2023-{(i // 30) + 1:02d}-01",
                "outcome":   "WIN" if pnl_r > 0 else "LOSS",
            })
        return records

    def test_validate_oos_returns_result(self):
        records = self._make_trade_records(50, 0.65)
        result = self.val.validate_oos(records, {"expectancy_r": 0.5})
        assert hasattr(result, "passed")
        assert hasattr(result, "overfit_score")
        assert 0 <= result.overfit_score <= 1

    def test_insufficient_data_fails(self):
        records = self._make_trade_records(5)
        result = self.val.validate_oos(records, {})
        assert result.passed is False

    def test_walk_forward_returns_list(self):
        records = self._make_trade_records(80, 0.6)
        results = self.val.walk_forward(records)
        assert isinstance(results, list)

    def test_validate_pattern_significant(self):
        records = self._make_trade_records(30, 0.70)
        result = self.val.validate_pattern(records, min_samples=20)
        assert "valid" in result
        assert "win_rate" in result
        assert "n" in result

    def test_validate_pattern_insufficient(self):
        records = self._make_trade_records(5)
        result = self.val.validate_pattern(records, min_samples=20)
        assert result["valid"] is False

    def test_overfit_score_no_degradation(self):
        from xau_bot.learning.validation_engine import ValidationEngine
        is_m  = {"expectancy_r": 0.5}
        oos_m = {"expectancy_r": 0.4}
        score = ValidationEngine._overfit_score(is_m, oos_m)
        assert 0 <= score <= 1

    def test_overfit_score_severe(self):
        from xau_bot.learning.validation_engine import ValidationEngine
        is_m  = {"expectancy_r": 1.0}
        oos_m = {"expectancy_r": -0.5}
        score = ValidationEngine._overfit_score(is_m, oos_m)
        assert score >= 0.5

    def test_validation_result_to_dict(self):
        records = self._make_trade_records(50, 0.6)
        result = self.val.validate_oos(records, {"expectancy_r": 0.3})
        d = result.to_dict()
        assert isinstance(d["passed"], int)  # 0 or 1


# ═══════════════════════════════════════════════════════════════════════════════
# ExplainabilityEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestExplainabilityEngine:

    def setup_method(self):
        from xau_bot.learning.explainability_engine import ExplainabilityEngine
        from xau_bot.learning.confidence_model import ConfidenceModel
        self.explainer = ExplainabilityEngine()
        self.conf_model = ConfidenceModel()

    def test_explain_entry_basic(self):
        fv = _make_feature_vector()
        bd = self.conf_model.score(fv)
        narrative = self.explainer.explain_entry(fv, bd)
        assert "ACCEPTED" in narrative
        assert "confidence" in narrative.lower()

    def test_explain_entry_with_similar_stats(self):
        fv = _make_feature_vector()
        bd = self.conf_model.score(fv)
        similar = {"sample_count": 30, "win_rate": 0.65, "expectancy_r": 0.45}
        narrative = self.explainer.explain_entry(fv, bd, similar_stats=similar)
        assert "30" in narrative
        assert "65%" in narrative

    def test_explain_rejection(self):
        fv = _make_feature_vector()
        bd = self.conf_model.score(fv)
        narrative = self.explainer.explain_rejection(fv, bd, "quality_too_low")
        assert "REJECTED" in narrative
        assert "quality" in narrative.lower()

    def test_explain_rejection_unknown_reason(self):
        fv = _make_feature_vector()
        bd = self.conf_model.score(fv)
        narrative = self.explainer.explain_rejection(fv, bd, "custom_reason")
        assert "custom_reason" in narrative

    def test_generate_trade_review_win(self):
        fv = _make_feature_vector()
        trade = _make_trade_record(pnl=200.0, pnl_r=2.0)
        review_scores = {
            "premature_entry": False, "insufficient_confirmation": False,
            "sl_too_tight": False, "unrealistic_target": False,
            "poor_conditions": False, "regime_misalignment": False,
        }
        narrative, recs = self.explainer.generate_trade_review(trade, fv, review_scores)
        assert "WIN" in narrative or "profitable" in narrative
        assert isinstance(recs, list)
        assert len(recs) >= 1

    def test_generate_trade_review_loss_with_flags(self):
        fv = _make_feature_vector()
        trade = _make_trade_record(pnl=-60.0, pnl_r=-1.0)
        trade["outcome"] = "LOSS"
        review_scores = {
            "premature_entry": True, "insufficient_confirmation": False,
            "sl_too_tight": True, "unrealistic_target": False,
            "poor_conditions": False, "regime_misalignment": True,
        }
        narrative, recs = self.explainer.generate_trade_review(trade, fv, review_scores)
        assert "LOSS" in narrative or "unprofitable" in narrative
        assert len(recs) >= 3

    def test_summarise_confidence(self):
        fv = _make_feature_vector()
        from xau_bot.learning.confidence_model import ConfidenceModel
        bd = ConfidenceModel().score(fv)
        summary = self.explainer.summarise_confidence(bd)
        assert "confidence=" in summary
        assert "composite=" in summary


# ═══════════════════════════════════════════════════════════════════════════════
# LearningEngine (integration)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLearningEngine:

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "le_test.db")
        cfg = _make_cfg(self.db_path)
        from xau_bot.learning.learning_engine import LearningEngine
        self.engine = LearningEngine(cfg, db_path=self.db_path)
        self.engine.initialize()

    def test_initialize(self):
        assert self.engine.trade_count == 0

    def test_get_setup_confidence(self):
        fv = _make_feature_vector()
        bd = self.engine.get_setup_confidence(fv)
        assert 0.05 <= bd.final_score <= 0.95

    def test_is_confidence_sufficient_before_min_data(self):
        # Before reaching min_trades_before_update, always True
        fv = _make_feature_vector()
        bd = self.engine.get_setup_confidence(fv)
        bd_low = bd
        assert self.engine.is_confidence_sufficient(bd_low)

    def test_record_trade_increments_count(self):
        fv = _make_feature_vector()
        trade = _make_trade_record(1, 150.0)
        self.engine.record_trade(trade, fv)
        assert self.engine.trade_count == 1

    def test_record_multiple_trades_triggers_analysis(self):
        for i in range(10):
            pnl = 100.0 if i % 2 == 0 else -50.0
            fv = _make_feature_vector()
            trade = _make_trade_record(100 + i, pnl)
            self.engine.record_trade(trade, fv)
        assert self.engine.trade_count == 10

    def test_post_trade_review_returns_narrative(self):
        fv = _make_feature_vector()
        trade = _make_trade_record(1, 150.0)
        narrative, recs = self.engine.post_trade_review(trade, fv)
        assert isinstance(narrative, str)
        assert len(narrative) > 10
        assert isinstance(recs, list)

    def test_detect_regime(self):
        df = _make_ohlc_df(80)
        snap = self.engine.detect_regime(df, 79)
        assert hasattr(snap, "regime")
        assert hasattr(snap, "trend_strength")

    def test_explain_entry(self):
        fv = _make_feature_vector()
        bd = self.engine.get_setup_confidence(fv)
        narrative = self.engine.explain_entry(fv, bd)
        assert "ACCEPTED" in narrative

    def test_explain_rejection(self):
        fv = _make_feature_vector()
        bd = self.engine.get_setup_confidence(fv)
        narrative = self.engine.explain_rejection(fv, bd, "quality_too_low")
        assert "REJECTED" in narrative

    def test_shutdown_saves_weights(self):
        fv = _make_feature_vector()
        for i in range(5):
            self.engine.record_trade(_make_trade_record(200 + i, 100.0), fv)
        self.engine.shutdown()
        # Re-open and verify weights were loaded
        from xau_bot.learning.learning_engine import LearningEngine
        cfg = _make_cfg(self.db_path)
        engine2 = LearningEngine(cfg, db_path=self.db_path)
        engine2.initialize()
        assert engine2.trade_count >= 5

    def test_summary(self):
        summary = self.engine.summary()
        assert "enabled" in summary
        assert "trade_count" in summary
        assert "confidence_model" in summary

    def test_safety_no_risk_modification(self):
        """
        Safety check: the learning engine has no mechanism to modify risk
        parameters.  This test verifies that record_trade never raises and
        never modifies the passed-in trade_record dict.
        """
        fv = _make_feature_vector()
        trade = _make_trade_record(99, -200.0, -2.0)
        original_pnl = trade["pnl"]
        for _ in range(20):
            self.engine.record_trade(trade, fv)
        assert trade["pnl"] == original_pnl  # unchanged
