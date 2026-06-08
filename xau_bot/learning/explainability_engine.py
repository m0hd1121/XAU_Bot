"""
explainability_engine.py
─────────────────────────
Generates human-readable explanations for every trading decision.

Every entry and rejection produces a sentence-level narrative explaining:
  • Why the setup was accepted / rejected
  • Which historical patterns drove the confidence score
  • What the similar trades looked like
  • Post-trade: what the model learned and what could have been better

Design principles:
  • Template-based NL generation (no LLM required — deterministic & fast)
  • Confidence breakdown shown per feature
  • Historical similar-trade summary included when data exists
  • Post-trade reviews actionable and jargon-free
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .confidence_model import ConfidenceBreakdown
from .feature_extractor import FeatureVector

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────────────

_REGIME_DESCRIPTIONS = {
    "STRONG_TREND":    "a clearly trending market",
    "WEAK_TREND":      "a weakly trending market",
    "RANGING":         "a ranging / sideways market",
    "HIGH_VOLATILITY": "an elevated-volatility environment",
    "LOW_VOLATILITY":  "a compressed low-volatility environment",
    "CHOPPY":          "a choppy, difficult-to-trade market",
    "UNKNOWN":         "an uncertain market environment",
}

_TRIGGER_DESCRIPTIONS = {
    "CHoCH_BULL":  "a bullish Change of Character",
    "CHoCH_BEAR":  "a bearish Change of Character",
    "BOS_BULL":    "a bullish Break of Structure",
    "BOS_BEAR":    "a bearish Break of Structure",
    "SWEEP_HIGH":  "a liquidity sweep above a high",
    "SWEEP_LOW":   "a liquidity sweep below a low",
    "UNKNOWN":     "an unclassified structure event",
}

_SWEEP_DESCRIPTIONS = {
    "equal_high": "equal highs (clustered buy stops)",
    "equal_low":  "equal lows (clustered sell stops)",
    "prev_high":  "the previous session high (stop cluster)",
    "prev_low":   "the previous session low (stop cluster)",
    "UNKNOWN":    "an unknown liquidity level",
}

_CONFIDENCE_ADJECTIVES = {
    (0.80, 1.01): "very high",
    (0.65, 0.80): "high",
    (0.50, 0.65): "moderate",
    (0.35, 0.50): "below average",
    (0.00, 0.35): "low",
}

_SESSION_DESCRIPTIONS = {
    "london":   "the London session",
    "new_york": "the New York session",
    "overlap":  "the London/New York overlap",
    "asian":    "the Asian session",
}


def _conf_adj(score: float) -> str:
    for (lo, hi), label in _CONFIDENCE_ADJECTIVES.items():
        if lo <= score < hi:
            return label
    return "unknown"


def _pct(val: float) -> str:
    return f"{val * 100:.0f}%"


# ─────────────────────────────────────────────────────────────────────────────
# ExplainabilityEngine
# ─────────────────────────────────────────────────────────────────────────────

class ExplainabilityEngine:

    # ── Trade decision explanation ───────────────────────────────────────────

    def explain_entry(
        self,
        features: FeatureVector,
        breakdown: ConfidenceBreakdown,
        similar_stats: Optional[dict] = None,
    ) -> str:
        """
        Generate explanation for a ACCEPTED trade entry.

        Example output:
        "Trade accepted (confidence 82%) during the London/NY overlap in a
         strongly trending market. A bullish Change of Character confirmed
         direction after a liquidity sweep below equal lows. The CHoCH trigger
         historically achieves 71% win rate over 45 similar trades (2.1R
         expectancy). Demand zone quality is HIGH with 0 prior tests. ATR
         volatility is NORMAL for current conditions."
        """
        conf   = breakdown.final_score
        regime = _REGIME_DESCRIPTIONS.get(features.regime, features.regime)
        sess   = _SESSION_DESCRIPTIONS.get(features.session, features.session)
        trig   = _TRIGGER_DESCRIPTIONS.get(features.trigger_event, features.trigger_event)
        sweep  = _SWEEP_DESCRIPTIONS.get(features.sweep_type, features.sweep_type)

        lines = [
            f"Trade ACCEPTED (confidence {_conf_adj(conf)}, {_pct(conf)}) during "
            f"{sess} in {regime}."
        ]

        lines.append(
            f"Entry triggered by {trig} following a sweep of {sweep}."
        )

        if features.zone_present:
            zone_q = features.zone_quality_bucket.lower()
            tests  = features.zone_test_count
            test_str = "untested" if tests == 0 else f"tested {tests}× before"
            lines.append(
                f"Price is at a {zone_q}-quality supply/demand zone ({test_str}, "
                f"{features.zone_age_bucket.lower()} formation)."
            )

        if features.structure_freshness == "FRESH":
            lines.append("Structure shift is recent (≤5 bars) — entry timing is favorable.")

        if breakdown.regime_multiplier < 0.90:
            lines.append(
                f"Regime multiplier is {breakdown.regime_multiplier:.2f}× "
                f"(reduced confidence in {features.regime.lower().replace('_',' ')} conditions)."
            )
        elif breakdown.regime_multiplier > 1.10:
            lines.append(
                f"Regime multiplier is {breakdown.regime_multiplier:.2f}× "
                f"(elevated confidence — favorable market conditions)."
            )

        if similar_stats and similar_stats.get("sample_count", 0) >= 10:
            n   = similar_stats["sample_count"]
            wr  = similar_stats["win_rate"] * 100
            exp = similar_stats.get("expectancy_r", 0)
            lines.append(
                f"Historically: {n} similar setups — {wr:.0f}% win rate, "
                f"{exp:+.2f}R expectancy."
            )

        if breakdown.dominant_features:
            lines.append(
                f"Primary confidence drivers: {', '.join(breakdown.dominant_features)}."
            )

        return " ".join(lines)

    def explain_rejection(
        self,
        features: FeatureVector,
        breakdown: ConfidenceBreakdown,
        rejection_reason: str,
        similar_stats: Optional[dict] = None,
    ) -> str:
        """Generate explanation for a REJECTED setup."""
        conf   = breakdown.final_score
        regime = _REGIME_DESCRIPTIONS.get(features.regime, features.regime)
        sess   = _SESSION_DESCRIPTIONS.get(features.session, features.session)

        lines = [
            f"Trade REJECTED (learned confidence {_conf_adj(conf)}, {_pct(conf)}) "
            f"during {sess} in {regime}."
        ]

        # Primary rejection reason
        reason_map = {
            "quality_too_low":          "Setup quality score is below the minimum threshold.",
            "cooldown_active":          "Psychology cooldown is active after a recent loss.",
            "daily_loss_limit_breached": "Daily loss limit has been reached — no further entries today.",
            "max_drawdown_kill_switch":  "Drawdown kill-switch is active — all trading halted.",
            "session_limit":            "Maximum trades for this session have been reached.",
            "rr_too_low":               "Risk:Reward ratio does not meet the minimum requirement.",
            "regime_misalignment":      f"Market regime ({features.regime}) historically underperforms for this setup type.",
            "insufficient_confidence":  "Learned confidence is below the adaptive threshold.",
        }
        lines.append(reason_map.get(rejection_reason, f"Reason: {rejection_reason}."))

        if breakdown.weak_features:
            lines.append(
                f"Low-confidence features: {', '.join(breakdown.weak_features)} "
                f"are signaling caution."
            )

        if breakdown.regime_multiplier < 0.85:
            lines.append(
                f"Regime multiplier {breakdown.regime_multiplier:.2f}× is dragging "
                f"composite confidence below threshold."
            )

        if similar_stats and similar_stats.get("sample_count", 0) >= 10:
            wr  = similar_stats["win_rate"] * 100
            exp = similar_stats.get("expectancy_r", 0)
            lines.append(
                f"Historical base rate for this setup: {wr:.0f}% win rate, "
                f"{exp:+.2f}R expectancy across {similar_stats['sample_count']} trades."
            )

        return " ".join(lines)

    # ── Post-trade review narrative ──────────────────────────────────────────

    def generate_trade_review(
        self,
        trade: dict,
        features: FeatureVector,
        review_scores: dict,
    ) -> str:
        """
        Produce a post-trade narrative and actionable recommendations.
        Returns (narrative_string, list_of_recommendations).
        """
        direction = trade.get("direction", "unknown")
        outcome   = trade.get("outcome", "UNKNOWN")
        pnl       = trade.get("pnl", 0.0)
        pnl_r     = trade.get("pnl_r", 0.0)
        reason    = trade.get("close_reason", "unknown")
        mae       = trade.get("mae", 0.0)
        mfe       = trade.get("mfe", 0.0)
        duration  = trade.get("duration_bars", 0)

        outcome_str = {"WIN": "profitable ✓", "LOSS": "unprofitable ✗", "BE": "break-even"}.get(outcome, outcome)
        lines = [
            f"POST-TRADE REVIEW — {direction.upper()} trade was {outcome_str} "
            f"({pnl:+.2f} USD, {pnl_r:+.2f}R) | Closed via {reason} | {duration} bars held."
        ]

        recs = []

        # MAE / MFE analysis
        if mfe > 0 and mae > 0:
            mfe_mae_ratio = mfe / (mae + 1e-10)
            lines.append(f"Price traveled {mfe:.2f} in our favor and {mae:.2f} against us (MFE/MAE ratio: {mfe_mae_ratio:.2f}).")
            if mfe_mae_ratio < 1.5 and outcome == "LOSS":
                recs.append("MFE/MAE ratio was low — price did not show strong conviction in trade direction. Consider waiting for clearer confirmation next time.")
            if mfe > abs(pnl_r) * 2 and outcome == "LOSS":
                recs.append("Trade was initially favorable (high MFE) but reversed. Review whether trailing stop settings need adjustment.")

        # Entry timing
        if review_scores.get("premature_entry"):
            lines.append("Entry was premature — structure shift had not fully confirmed.")
            recs.append("Wait for a full candle close beyond the structure level before entering.")

        if review_scores.get("insufficient_confirmation"):
            lines.append("Confirmation quality was below ideal.")
            recs.append("Require at least one rejection candle at the zone before entry.")

        # SL quality
        if review_scores.get("sl_too_tight") and outcome == "LOSS":
            lines.append("Stop loss was placed too tightly relative to recent volatility.")
            recs.append(f"Consider widening SL to at least 1.0× ATR in {features.volatility_regime.lower().replace('_',' ')} conditions.")

        # Target quality
        if review_scores.get("unrealistic_target") and outcome == "LOSS":
            lines.append("Target was beyond a significant supply/demand zone or prior high/low.")
            recs.append("Set TP1 before the next key liquidity level, not beyond it.")

        # Market conditions
        if review_scores.get("regime_misalignment"):
            regime_desc = _REGIME_DESCRIPTIONS.get(features.regime, features.regime)
            lines.append(f"Market was in {regime_desc}, which historically produces lower-quality results for this setup type.")
            recs.append(f"Reduce position size or skip entries during {features.regime.lower().replace('_',' ')} conditions.")

        # Positive reinforcement for good decisions
        if outcome == "WIN" and not any(review_scores.values()):
            lines.append("All entry criteria were met. This trade followed the process correctly.")
            recs.append("Maintain current setup selection criteria — process was sound.")

        if not recs:
            recs.append("No specific action items identified. Review the trade at next periodic analysis.")

        narrative = " ".join(lines)
        return narrative, recs

    # ── Confidence summary ────────────────────────────────────────────────────

    def summarise_confidence(self, breakdown: ConfidenceBreakdown) -> str:
        """One-line confidence summary for logging."""
        return (
            f"confidence={breakdown.final_score:.2%} "
            f"(composite={breakdown.composite_score:.2%} × regime×{breakdown.regime_multiplier:.2f}) "
            f"top_drivers=[{', '.join(breakdown.dominant_features[:3])}]"
        )
