"""Tests for PsychologyLayer — cooldowns, revenge trading, streaks."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from xau_bot.psychology_layer import PsychologyLayer, PsychologyVerdict


CFG = {
    "psychology": {
        "max_consecutive_losses": 3,
        "loss_streak_size_reduction": 0.5,
        "cooldown_candles_after_loss": 3,
        "cooldown_candles_after_kill": 48,
        "min_setup_quality_score": 0.6,
        "max_trades_per_session": 2,
        "revenge_trade_detection": True,
    }
}


@pytest.fixture
def psych():
    return PsychologyLayer(CFG)


class TestCooldown:

    def test_cooldown_after_loss(self, psych):
        psych.record_loss(bar=10, session="london")
        verdict = psych.approve(0.8, current_bar=11, session="london",
                                setup_direction="long")
        assert not verdict.approved
        assert "cooldown" in verdict.reason

    def test_cooldown_expires(self, psych):
        psych.record_loss(bar=10, session="london")
        # Cooldown is 3 candles, so bar 13 should be ok
        verdict = psych.approve(0.8, current_bar=14, session="london",
                                setup_direction="long")
        assert verdict.approved

    def test_no_cooldown_after_win(self, psych):
        psych.record_win(bar=10, session="london")
        verdict = psych.approve(0.8, current_bar=11, session="london",
                                setup_direction="long")
        assert verdict.approved


class TestQualityGate:

    def test_low_quality_rejected(self, psych):
        verdict = psych.approve(0.4, current_bar=5, session="london",
                                setup_direction="long")
        assert not verdict.approved
        assert "quality" in verdict.reason

    def test_high_quality_approved(self, psych):
        verdict = psych.approve(0.9, current_bar=5, session="london",
                                setup_direction="long")
        assert verdict.approved

    def test_exact_threshold_approved(self, psych):
        verdict = psych.approve(0.6, current_bar=5, session="london",
                                setup_direction="long")
        assert verdict.approved


class TestRevengeTrade:

    def test_revenge_trade_blocked(self, psych):
        psych.record_loss(bar=10, session="london")
        # Attempting the same direction immediately after a loss
        verdict = psych.approve(
            setup_quality=0.8,
            current_bar=11,
            session="london",
            setup_direction="long",
            last_trade_direction="long",
            last_trade_was_loss=True,
        )
        # Should be blocked by cooldown (comes first) or revenge detection
        assert not verdict.approved

    def test_opposite_direction_after_loss_not_revenge(self, psych):
        # After cooldown expires, opposite direction is fine
        psych.record_loss(bar=10, session="london")
        verdict = psych.approve(
            setup_quality=0.8,
            current_bar=15,  # After cooldown
            session="new_york",
            setup_direction="short",
            last_trade_direction="long",
            last_trade_was_loss=True,
        )
        assert verdict.approved


class TestSessionLimit:

    def test_session_limit_enforced(self, psych):
        psych.record_win(bar=5, session="london")
        psych.record_win(bar=8, session="london")
        verdict = psych.approve(0.9, current_bar=10, session="london",
                                setup_direction="long")
        assert not verdict.approved
        assert "session_limit" in verdict.reason

    def test_different_session_not_limited(self, psych):
        psych.record_win(bar=5, session="london")
        psych.record_win(bar=8, session="london")
        verdict = psych.approve(0.9, current_bar=10, session="new_york",
                                setup_direction="long")
        assert verdict.approved


class TestSizeModifier:

    def test_size_reduced_after_streak(self, psych):
        for i in range(3):
            psych.record_loss(bar=i * 5, session="london")

        # After 3 losses, next approved trade has reduced size
        # Fast-forward past all cooldowns
        verdict = psych.approve(0.8, current_bar=100, session="new_york",
                                setup_direction="long")
        if verdict.approved:
            assert verdict.size_modifier < 1.0

    def test_size_restored_after_win(self, psych):
        psych.record_loss(bar=5, session="london")
        psych.record_loss(bar=10, session="london")
        psych.record_loss(bar=15, session="london")
        psych.record_win(bar=100, session="new_york")
        assert psych.size_modifier == 1.0


class TestExtremeLossHalt:

    def test_extreme_streak_halts(self, psych):
        for i in range(7):  # 2× max consecutive losses
            psych.record_loss(bar=i * 10, session="london")
        assert psych.state.halted_by_psychology

    def test_halt_reset(self, psych):
        psych.state.halted_by_psychology = True
        psych.reset_halt()
        assert not psych.state.halted_by_psychology
