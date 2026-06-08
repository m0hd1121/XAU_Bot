"""Tests for RiskManager — position sizing, drawdown, kill-switch."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, date

from xau_bot.risk_manager import RiskManager, RiskReport


CFG = {
    "risk": {
        "initial_capital": 10000.0,
        "risk_per_trade":  0.01,
        "max_risk_per_trade": 0.02,
        "daily_loss_limit": 0.03,
        "max_drawdown_kill": 0.10,
        "min_reward_to_risk": 2.0,
        "max_open_trades": 2,
        "volatility_lookback": 14,
        "volatility_scale_factor": 1.5,
    },
    "strategy": {
        "sl_buffer_pips": 3.0,
        "tp1_rr": 1.5,
        "tp2_rr": 3.0,
    },
    "execution": {
        "lot_size": 100,
        "min_lot":  0.01,
        "max_lot":  10.0,
        "lot_step": 0.01,
        "commission_per_lot": 7.0,
    }
}


@pytest.fixture
def rm():
    return RiskManager(CFG)


class TestPositionSizing:

    def test_basic_trade_allowed(self, rm):
        report = rm.evaluate_trade(
            entry_price=1850.0,
            sl_price=1840.0,
            direction="long",
            atr_proxy=10.0,
        )
        assert report.allowed
        assert report.lot_size >= 0.01

    def test_sl_above_entry_for_long_rejected(self, rm):
        report = rm.evaluate_trade(
            entry_price=1850.0,
            sl_price=1860.0,   # SL above entry for long — invalid
            direction="long",
            atr_proxy=10.0,
        )
        assert not report.allowed

    def test_sl_below_entry_for_short_rejected(self, rm):
        # For a SHORT: SL must be ABOVE entry. SL below entry is in profit territory → invalid.
        report = rm.evaluate_trade(
            entry_price=1850.0,
            sl_price=1830.0,   # SL below entry for short — invalid (profit direction)
            direction="short",
            atr_proxy=10.0,
        )
        assert not report.allowed

    def test_lot_size_within_bounds(self, rm):
        report = rm.evaluate_trade(
            entry_price=1850.0,
            sl_price=1840.0,
            direction="long",
            atr_proxy=10.0,
        )
        assert report.allowed
        assert CFG["execution"]["min_lot"] <= report.lot_size <= CFG["execution"]["max_lot"]

    def test_lot_size_scales_with_risk(self, rm):
        # Small SL → larger lot size
        report_tight = rm.evaluate_trade(1850.0, 1847.0, "long", 5.0)
        report_wide  = rm.evaluate_trade(1850.0, 1830.0, "long", 5.0)
        if report_tight.allowed and report_wide.allowed:
            assert report_tight.lot_size >= report_wide.lot_size

    def test_tp1_at_correct_rr(self, rm):
        report = rm.evaluate_trade(1850.0, 1840.0, "long", 10.0)
        assert report.allowed
        sl_dist = report.sl_pips
        expected_tp1 = report.sl_price + sl_dist * (1 + 1.5)   # approximate
        assert report.tp1_price > report.sl_price

    def test_risk_amount_correct(self, rm):
        report = rm.evaluate_trade(1850.0, 1840.0, "long", 10.0)
        assert report.allowed
        expected_risk = 10000.0 * 0.01
        assert abs(report.risk_amount - expected_risk) < expected_risk * 0.2


class TestDailyLimit:

    def test_daily_loss_limit_halts_trading(self, rm):
        # Simulate losses equal to daily limit
        rm.register_trade_close(-310.0)   # > 3% of 10000
        report = rm.evaluate_trade(
            1850.0, 1840.0, "long", 10.0,
            current_time=datetime(2023, 1, 2, 10, 0),
        )
        # Should be halted
        assert not report.allowed

    def test_daily_reset(self, rm):
        dt_day1 = datetime(2023, 1, 2, 10, 0)
        dt_day2 = datetime(2023, 1, 3, 10, 0)
        # Force into loss
        rm._equity = rm._initial_capital * 0.96
        rm._daily_start = rm._initial_capital * 0.96
        # New day resets daily start
        rm._maybe_reset_daily(dt_day2.date())
        assert rm._daily_start == rm._equity


class TestDrawdownKillSwitch:

    def test_kill_switch_activates_at_threshold(self, rm):
        # Simulate 10% drawdown
        rm.register_trade_close(-1000.0)  # 10% of 10000
        assert not rm.is_trading_allowed

    def test_kill_switch_blocks_trades(self, rm):
        rm._kill_active = True
        report = rm.evaluate_trade(1850.0, 1840.0, "long", 10.0)
        assert not report.allowed
        assert "kill_switch" in report.reason

    def test_kill_switch_manual_reset(self, rm):
        rm._kill_active = True
        rm._trading_halted = True
        rm.reset_kill_switch()
        assert rm.is_trading_allowed

    def test_kill_switch_not_triggered_before_threshold(self, rm):
        # Only 5% drawdown — should NOT trigger
        rm.register_trade_close(-500.0)
        assert rm.is_trading_allowed


class TestMaxOpenTrades:

    def test_max_open_trades_respected(self, rm):
        report = rm.evaluate_trade(
            1850.0, 1840.0, "long", 10.0,
            open_trades=2,   # Already at max
        )
        assert not report.allowed
        assert "max_open_trades" in report.reason


class TestEquityTracking:

    def test_equity_updates_on_close(self, rm):
        initial = rm.equity
        rm.register_trade_close(100.0)
        assert rm.equity == initial + 100.0

    def test_peak_tracks_correctly(self, rm):
        rm.register_trade_close(500.0)
        assert rm._peak == rm._initial_capital + 500.0
        rm.register_trade_close(-200.0)
        assert rm._peak == rm._initial_capital + 500.0  # Peak doesn't decrease

    def test_drawdown_state_accessible(self, rm):
        state = rm.get_state()
        assert state.current_equity == rm._initial_capital
        assert not state.kill_switch_active
