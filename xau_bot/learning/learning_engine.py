"""
learning_engine.py
───────────────────
Central orchestrator for the self-learning subsystem.

Coordinates all learning modules:
  • TradeDatabase     — persistent SQLite storage
  • FeatureExtractor  — converts trade context → FeatureVector
  • PatternAnalyzer   — discovers statistically significant patterns
  • ConfidenceModel   — adaptive per-feature confidence weights (EMA)
  • RegimeDetector    — classifies current market conditions from price
  • ValidationEngine  — prevents overfitting via OOS and walk-forward checks
  • ExplainabilityEngine — human-readable narratives for every decision

Safety guarantees (immutable — cannot be overridden by any learning update):
  ✗  Never disables stop losses
  ✗  Never increases maximum account risk
  ✗  Never ignores drawdown protection
  ✗  Never ignores daily loss limits
  ✗  Never chases losses
  ✗  Never optimises purely for win rate at the expense of expectancy

The learning engine's only authority is to output a learned confidence
score that acts as an *additional* entry filter.  Every protective risk
management rule remains fully operative and independent of this module.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

import pandas as pd

from .trade_database import TradeDatabase
from .feature_extractor import FeatureExtractor, FeatureVector
from .pattern_analyzer import PatternAnalyzer
from .confidence_model import ConfidenceModel, ConfidenceBreakdown
from .regime_detector import RegimeDetector, RegimeSnapshot
from .validation_engine import ValidationEngine
from .explainability_engine import ExplainabilityEngine

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# LearningEngine
# ─────────────────────────────────────────────────────────────────────────────

class LearningEngine:
    """
    Orchestrates all self-learning components.
    Call `initialize()` once at startup to restore persisted state.
    Call `shutdown()` at the end of a run to persist final state.

    Thread-safety: read operations (`get_setup_confidence`, `detect_regime`)
    are safe to call concurrently.  Write operations (`record_trade`,
    `_run_periodic_analysis`, `_save_weights`) must be serialised by the
    caller (the Backtester is single-threaded, so this is automatically
    satisfied in the backtest context).
    """

    def __init__(self, cfg: dict, db_path: str = None) -> None:
        lc = cfg.get("learning", {})

        self._cfg     = cfg
        self._enabled = lc.get("enabled", True)

        # Periodic analysis settings
        self._periodic_every      = lc.get("analysis_every_n_trades", 50)
        self._min_data_for_update = lc.get("min_trades_before_update", 30)

        # Adaptive threshold: apply learned confidence filter only when there
        # is enough data.  Below threshold, all setups are allowed through.
        self._adaptive_threshold_enabled = lc.get("adaptive_threshold", True)
        self._min_confidence_threshold   = lc.get("min_confidence_threshold", 0.45)

        # Sub-systems
        _db_path = db_path or lc.get("db_path", "data/learning.db")
        self._db          = TradeDatabase(_db_path)
        self._feat_ex     = FeatureExtractor(cfg)
        self._patterns    = PatternAnalyzer(
            min_samples    = lc.get("min_pattern_samples", 20),
            decay_halflife = lc.get("decay_halflife", 500),
        )
        self._confidence  = ConfidenceModel()
        self._regime_det  = RegimeDetector(cfg)
        self._validator   = ValidationEngine(cfg)
        self._explainer   = ExplainabilityEngine()

        # Runtime state
        self._trade_count          = 0
        self._last_analysis_count  = 0
        self._pending_weights_save = False
        self._last_outcome: str    = "NONE"

    # ── Startup / Shutdown ────────────────────────────────────────────────────

    def initialize(self) -> None:
        """
        Load persisted confidence weights and trade count from the database.
        Must be called once before `get_setup_confidence()` or `record_trade()`.
        """
        if not self._enabled:
            logger.info("Learning engine disabled in config — skipping init.")
            return

        weights = self._db.get_confidence_weights()
        if weights:
            self._confidence.load_from_db_weights(weights)
            logger.info(
                "Learning engine: loaded %d confidence entries from DB.", len(weights)
            )

        self._trade_count = self._db.count_trades()
        logger.info(
            "Learning engine initialised. %d historical trades in DB.", self._trade_count
        )
        self._db.log_event(
            "STARTUP",
            f"Initialised with {self._trade_count} historical trades, "
            f"{len(weights)} confidence entries.",
        )

    def shutdown(self) -> None:
        """Persist any unsaved model state before process exit."""
        if not self._enabled:
            return
        if self._pending_weights_save:
            self._save_weights()
        self._db.log_event(
            "SHUTDOWN", f"Clean shutdown after {self._trade_count} total trades."
        )
        logger.info("Learning engine shut down — state persisted.")

    # ── Regime detection ──────────────────────────────────────────────────────

    def detect_regime(self, df: pd.DataFrame, bar_index: int) -> RegimeSnapshot:
        """Classify the current market regime from OHLC price action."""
        return self._regime_det.detect(df, bar_index)

    def record_regime(
        self, bar_index: int, ts: str, snapshot: RegimeSnapshot, price: float
    ) -> None:
        """Optionally persist regime snapshots for longitudinal analysis."""
        self._db.insert_regime({
            "ts":               ts,
            "bar_index":        bar_index,
            "regime":           snapshot.regime.value,
            "volatility_regime": snapshot.vol_regime.value,
            "trend_strength":   snapshot.trend_strength,
            "atr_ratio":        snapshot.atr_ratio,
            "price":            price,
        })

    # ── Confidence scoring ────────────────────────────────────────────────────

    def get_setup_confidence(self, features: FeatureVector) -> ConfidenceBreakdown:
        """
        Return learned confidence score for a candidate trade setup.
        The score is in [0.05, 0.95] — never absolute.

        NOTE: This score is advisory.  Risk management parameters (SL, lot
        size, daily limits) are never derived from or modified by this score.
        """
        return self._confidence.score(features)

    def is_confidence_sufficient(self, breakdown: ConfidenceBreakdown) -> bool:
        """
        Return True if the adaptive threshold check passes.

        The filter is only applied when:
          1. The adaptive threshold feature is enabled in config.
          2. Enough trades have been recorded for the model to be reliable.

        Before the minimum data threshold is reached, every setup passes.
        """
        if not self._adaptive_threshold_enabled:
            return True
        if self._trade_count < self._min_data_for_update:
            return True   # not enough data — don't filter yet
        return breakdown.final_score >= self._min_confidence_threshold

    # ── Explanations ─────────────────────────────────────────────────────────

    def explain_entry(
        self,
        features: FeatureVector,
        breakdown: ConfidenceBreakdown,
        similar_stats: Optional[dict] = None,
    ) -> str:
        return self._explainer.explain_entry(features, breakdown, similar_stats)

    def explain_rejection(
        self,
        features: FeatureVector,
        breakdown: ConfidenceBreakdown,
        reason: str,
        similar_stats: Optional[dict] = None,
    ) -> str:
        return self._explainer.explain_rejection(features, breakdown, reason, similar_stats)

    def summarise_confidence(self, breakdown: ConfidenceBreakdown) -> str:
        return self._explainer.summarise_confidence(breakdown)

    # ── Pattern lookup ────────────────────────────────────────────────────────

    def get_similar_pattern_stats(self, features: FeatureVector) -> Optional[dict]:
        """Return aggregated stats for the current setup's pattern fingerprint."""
        return self._db.get_pattern_stats(features.pattern_key)

    # ── Trade lifecycle ───────────────────────────────────────────────────────

    def record_trade(
        self,
        trade_record: dict,
        features: FeatureVector,
    ) -> None:
        """
        Called after a trade closes.  Persists the trade and its features,
        immediately updates the confidence model via EMA, and triggers
        periodic full analysis every N trades.

        Safety: this method NEVER modifies risk parameters.
        """
        if not self._enabled:
            return

        # ── Persist raw trade ─────────────────────────────────────────────────
        self._db.insert_trade(trade_record)
        self._db.insert_features(trade_record.get("trade_id", 0), features.to_dict())

        # ── Immediate EMA update on confidence weights ────────────────────────
        pnl = trade_record.get("pnl", 0.0)
        outcome = "WIN" if pnl > 1e-9 else ("LOSS" if pnl < -1e-9 else "BE")
        pnl_r = trade_record.get("pnl_r", 0.0)

        self._confidence.update(features, outcome, pnl_r)
        self._last_outcome = outcome

        self._trade_count         += 1
        self._pending_weights_save = True

        logger.debug(
            "Learning: trade #%d recorded (%s, %.2fR). Total: %d",
            trade_record.get("trade_id", 0), outcome, pnl_r, self._trade_count,
        )

        # ── Periodic deep analysis ────────────────────────────────────────────
        trades_since_last = self._trade_count - self._last_analysis_count
        if trades_since_last >= self._periodic_every:
            self._run_periodic_analysis()

    def post_trade_review(
        self,
        trade_record: dict,
        features: FeatureVector,
    ) -> tuple[str, list[str]]:
        """
        Generate a human-readable post-trade review with actionable
        recommendations.  Saves the review to the database.

        Returns (narrative: str, recommendations: list[str]).
        """
        review_scores = self._evaluate_trade_quality(trade_record, features)

        narrative, recs = self._explainer.generate_trade_review(
            trade_record, features, review_scores
        )

        review_data = {
            **review_scores,
            "narrative":              narrative,
            "recommendations":        recs,
            "overall_decision_score": _compute_decision_score(review_scores),
            # Map boolean flags to the DB column names
            "entry_timing_score":     0.0 if review_scores.get("premature_entry") else 1.0,
            "confirmation_score":     0.0 if review_scores.get("insufficient_confirmation") else 1.0,
            "sl_quality_score":       0.0 if review_scores.get("sl_too_tight") else 1.0,
            "target_quality_score":   0.0 if review_scores.get("unrealistic_target") else 1.0,
            "condition_score":        0.0 if review_scores.get("poor_conditions") else 1.0,
        }

        try:
            self._db.insert_review(trade_record.get("trade_id", 0), review_data)
        except Exception as exc:
            logger.debug("Review insert skipped: %s", exc)

        return narrative, recs

    # ── Feature extraction helper ─────────────────────────────────────────────

    def extract_features(
        self,
        *,
        setup,                      # TradeSetup from strategy_engine
        state,                      # MarketState from market_structure_engine
        candle,                     # Candle from data_handler
        df: pd.DataFrame,
        bar_index: int,
        regime_snapshot: RegimeSnapshot,
        consecutive_losses: int,
        prev_outcome: str,
        htf_bias: str = "UNKNOWN",
    ) -> Optional[FeatureVector]:
        """
        Build a FeatureVector from a TradeSetup + surrounding market context.
        Returns None on extraction failure (non-fatal — trade proceeds without
        learning filter).
        """
        try:
            atr = float(
                df["atr_proxy"].values[bar_index]
                if "atr_proxy" in df.columns else candle.range_size
            )
            # Baseline ATR (50-bar rolling mean, minimum 5)
            baseline_atr = float(
                df["atr_proxy"].rolling(50, min_periods=5).mean().values[bar_index]
                if "atr_proxy" in df.columns else atr
            )

            zone = setup.nearest_zone
            zone_present    = zone is not None
            zone_quality    = float(zone.quality_score) if zone else 0.5
            zone_test_count = int(zone.test_count)      if zone else 0
            zone_origin_bar = int(zone.origin_index)    if zone else max(0, bar_index - 30)

            last_shift_bar = (
                state.last_structure_shift.bar_index
                if state.last_structure_shift else max(0, bar_index - 10)
            )
            last_sweep_type = (
                state.last_sweep.level_type.value
                if state.last_sweep and hasattr(state.last_sweep, "level_type")
                else "UNKNOWN"
            )

            body_ratio  = float(df["body_ratio"].values[bar_index]) if "body_ratio" in df.columns else 0.5
            upper_wick  = float(df["upper_wick"].values[bar_index]) if "upper_wick" in df.columns else 0.0
            lower_wick  = float(df["lower_wick"].values[bar_index]) if "lower_wick" in df.columns else 0.0
            candle_type = str(df["candle_type"].values[bar_index])  if "candle_type" in df.columns else "neutral"

            return self._feat_ex.extract(
                direction          = setup.direction.value,
                entry_price        = setup.entry_price,
                sl_price           = setup.raw_sl_price,
                tp1_price          = setup.entry_price + abs(setup.entry_price - setup.raw_sl_price) * 1.5,
                session            = setup.session,
                timestamp          = setup.timestamp,
                atr_proxy          = atr,
                baseline_atr       = baseline_atr,
                trigger_event      = setup.trigger_shift_event.value,
                sweep_type         = last_sweep_type,
                htf_bias           = htf_bias,
                trend              = state.trend.value,
                zone_present       = zone_present,
                zone_quality       = zone_quality,
                zone_test_count    = zone_test_count,
                zone_origin_bar    = zone_origin_bar,
                current_bar        = bar_index,
                last_shift_bar     = last_shift_bar,
                body_ratio         = body_ratio,
                upper_wick         = upper_wick,
                lower_wick         = lower_wick,
                candle_type        = candle_type,
                consecutive_losses = consecutive_losses,
                prev_trade_outcome = prev_outcome,
                regime             = regime_snapshot.regime.value,
                volatility_regime  = regime_snapshot.vol_regime.value,
            )
        except Exception as exc:
            logger.debug("extract_features failed: %s", exc)
            return None

    # ── Periodic analysis ─────────────────────────────────────────────────────

    def _run_periodic_analysis(self) -> None:
        """
        Full model update cycle.  Run order:
          1. Load all trades with features from DB
          2. Pattern analysis → update pattern_stats table
          3. Feature importances → update ConfidenceModel importances
          4. Regime multiplier updates
          5. Out-of-sample validation
          6. Persist weights if OOS validation passes
          7. Walk-forward validation (every 5th analysis cycle)
        """
        logger.info(
            "Learning: running periodic analysis at trade #%d…", self._trade_count
        )
        try:
            records = self._db.get_all_trades_with_features()
            if len(records) < self._min_data_for_update:
                logger.debug(
                    "Learning: only %d records — skipping analysis (need %d).",
                    len(records), self._min_data_for_update,
                )
                return

            # ── 1. Pattern analysis ───────────────────────────────────────────
            pattern_stats = self._patterns.analyze(records)
            for ps in pattern_stats:
                self._db.upsert_pattern_stats(ps)
            logger.debug("Learning: %d pattern stats upserted.", len(pattern_stats))

            # ── 2. Feature importances ────────────────────────────────────────
            importances = self._patterns.compute_feature_importances(records)
            if importances:
                self._confidence.update_importances(importances)

            # ── 3. Regime multipliers ─────────────────────────────────────────
            self._update_regime_multipliers(records)

            # ── 4. OOS validation ─────────────────────────────────────────────
            is_metrics = {
                "expectancy_r": (
                    sum(r.get("pnl_r", 0.0) for r in records) / len(records)
                )
            }
            val_result = self._validator.validate_oos(records, is_metrics)
            self._db.insert_validation_result(val_result.to_dict())

            if val_result.passed:
                self._save_weights()
                self._pending_weights_save = False
                logger.info("Learning: OOS validation PASS — weights persisted. %s", val_result.notes)
            else:
                logger.warning(
                    "Learning: OOS validation FAIL — weights NOT persisted. %s",
                    val_result.notes,
                )

            # ── 5. Walk-forward (every 5th periodic cycle) ───────────────────
            cycle = self._trade_count // self._periodic_every
            if cycle % 5 == 0:
                wf_results = self._validator.walk_forward(records)
                for wf in wf_results:
                    self._db.insert_validation_result(wf.to_dict())
                if wf_results:
                    pass_pct = sum(1 for r in wf_results if r.passed) / len(wf_results) * 100
                    logger.info(
                        "Learning: walk-forward %d windows, %.0f%% passed.",
                        len(wf_results), pass_pct,
                    )

            self._last_analysis_count = self._trade_count

            self._db.log_event(
                "PERIODIC_ANALYSIS",
                (
                    f"trade#{self._trade_count}: {len(pattern_stats)} patterns analysed, "
                    f"OOS={'PASS' if val_result.passed else 'FAIL'} "
                    f"(IS={val_result.is_expectancy:+.3f}R, OOS={val_result.oos_expectancy:+.3f}R)"
                ),
                {
                    "trade_count":        self._trade_count,
                    "patterns_found":     len(pattern_stats),
                    "oos_passed":         val_result.passed,
                    "is_expectancy":      val_result.is_expectancy,
                    "oos_expectancy":     val_result.oos_expectancy,
                    "overfit_score":      val_result.overfit_score,
                },
            )

        except Exception as exc:
            logger.exception("Periodic analysis error (non-fatal): %s", exc)

    def _update_regime_multipliers(self, records: list[dict]) -> None:
        """Recompute per-regime win rate and profit factor; update ConfidenceModel."""
        regime_groups: dict[str, list] = defaultdict(list)
        for r in records:
            reg = r.get("regime") or "UNKNOWN"
            regime_groups[reg].append(r)

        for regime, trades in regime_groups.items():
            if len(trades) < 20:
                continue
            wins    = sum(1 for t in trades if t.get("pnl", 0) > 1e-9)
            wr      = wins / len(trades)
            pnls    = [t.get("pnl", 0.0) for t in trades]
            gross_w = sum(p for p in pnls if p > 0) or 0.0
            gross_l = abs(sum(p for p in pnls if p < 0)) or 1e-10
            pf      = gross_w / gross_l
            self._confidence.update_regime_from_stats(regime, wr, pf, len(trades))

    def _save_weights(self) -> None:
        """Flush ConfidenceModel state to the database."""
        rows = self._confidence.to_db_rows()
        for feat_name, feat_val, regime, weight, count in rows:
            self._db.upsert_confidence_weight(feat_name, feat_val, regime, weight, count)
        logger.debug("Learning: %d confidence weights saved to DB.", len(rows))

    # ── Trade quality assessment ──────────────────────────────────────────────

    @staticmethod
    def _evaluate_trade_quality(trade: dict, features: FeatureVector) -> dict:
        """
        Score execution quality for the ExplainabilityEngine.
        Returns a dict of boolean flags — True = issue detected.
        """
        return {
            "premature_entry":           features.structure_freshness == "AGED",
            "insufficient_confirmation": features.body_ratio_bucket == "LOW",
            "sl_too_tight":              features.sl_atr_bucket == "TIGHT",
            "unrealistic_target":        features.rr_bucket == "MINIMUM",
            "poor_conditions":           False,  # Reserved for future checks
            "regime_misalignment":       features.regime in ("CHOPPY", "HIGH_VOLATILITY"),
        }

    # ── Utility ───────────────────────────────────────────────────────────────

    @property
    def feature_extractor(self) -> FeatureExtractor:
        return self._feat_ex

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def trade_count(self) -> int:
        return self._trade_count

    def summary(self) -> dict:
        return {
            "enabled":               self._enabled,
            "trade_count":           self._trade_count,
            "last_analysis_at":      self._last_analysis_count,
            "pending_save":          self._pending_weights_save,
            "min_confidence_gate":   self._min_confidence_threshold,
            "confidence_model":      self._confidence.summary(),
            "significant_patterns":  len(self._db.get_significant_patterns()),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helper
# ─────────────────────────────────────────────────────────────────────────────

def _compute_decision_score(review_scores: dict) -> float:
    """0–1: fraction of quality criteria met (1 = all criteria met)."""
    n = len(review_scores)
    if n == 0:
        return 1.0
    issues = sum(1 for v in review_scores.values() if v)
    return round(max(0.0, 1.0 - issues / n), 3)
