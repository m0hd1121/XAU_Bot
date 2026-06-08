"""Tests for PerformanceAnalyzer — metrics accuracy."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import math
from xau_bot.performance_analyzer import PerformanceAnalyzer


CFG = {
    "backtest": {"log_trades": False, "save_equity_curve": False, "output_dir": "/tmp"},
    "risk": {"initial_capital": 10000.0},
}


def make_trades(pnls, direction="long", session="london"):
    return [
        {
            "trade_id": i,
            "pnl": pnl,
            "pnl_r": pnl / 100,
            "direction": direction,
            "session": session,
            "open_time": f"2023-01-{i+2:02d} 10:00:00",
            "close_reason": "tp2" if pnl > 0 else "stop_loss",
        }
        for i, pnl in enumerate(pnls)
    ]


@pytest.fixture
def analyzer():
    return PerformanceAnalyzer(CFG)


class TestBasicMetrics:

    def test_total_trades(self, analyzer):
        trades = make_trades([100, -50, 200, -75, 150])
        metrics = analyzer.compute(trades, [10000, 10100, 10050, 10250, 10175, 10325], 10325, 10000)
        assert metrics["total_trades"] == 5

    def test_win_rate(self, analyzer):
        trades = make_trades([100, 100, -50, -50, 100])
        metrics = analyzer.compute(trades, [10000] * 6, 10200, 10000)
        assert metrics["win_rate_pct"] == 60.0

    def test_profit_factor(self, analyzer):
        trades = make_trades([200, 200, -100, -100])
        metrics = analyzer.compute(trades, [10000] * 5, 10200, 10000)
        assert abs(metrics["profit_factor"] - 2.0) < 0.01

    def test_all_losses(self, analyzer):
        trades = make_trades([-100, -200, -150])
        metrics = analyzer.compute(trades, [10000, 9900, 9700, 9550], 9550, 10000)
        assert metrics["win_rate_pct"] == 0.0
        assert metrics["profit_factor"] == 0.0

    def test_all_wins(self, analyzer):
        trades = make_trades([100, 200, 150])
        metrics = analyzer.compute(trades, [10000, 10100, 10300, 10450], 10450, 10000)
        assert metrics["win_rate_pct"] == 100.0
        assert metrics["losers"] == 0


class TestDrawdown:

    def test_max_drawdown_calculation(self, analyzer):
        equity = [10000, 10500, 10200, 9800, 10100]
        trades = make_trades([500, -300, -400, 300])
        metrics = analyzer.compute(trades, equity, 10100, 10000)
        # Peak is 10500, lowest is 9800 → DD = 700/10500 = 6.67%
        assert abs(metrics["max_drawdown_pct"] - 6.67) < 0.5

    def test_zero_drawdown_all_profits(self, analyzer):
        equity = [10000, 10100, 10200, 10300]
        trades = make_trades([100, 100, 100])
        metrics = analyzer.compute(trades, equity, 10300, 10000)
        assert metrics["max_drawdown_pct"] == 0.0


class TestStreaks:

    def test_consecutive_wins(self, analyzer):
        trades = make_trades([100, 100, 100, -50, 100])
        metrics = analyzer.compute(trades, [10000] * 6, 10350, 10000)
        assert metrics["max_consec_wins"] == 3

    def test_consecutive_losses(self, analyzer):
        trades = make_trades([100, -50, -50, -50, 100])
        metrics = analyzer.compute(trades, [10000] * 6, 9950, 10000)
        assert metrics["max_consec_losses"] == 3


class TestBreakdown:

    def test_session_breakdown(self, analyzer):
        trades = (make_trades([100, -50], session="london") +
                  make_trades([200, 150], session="new_york"))
        metrics = analyzer.compute(trades, [10000] * 5, 10400, 10000)
        assert "london" in metrics["by_session"]
        assert "new_york" in metrics["by_session"]

    def test_direction_breakdown(self, analyzer):
        trades = (make_trades([100, 200], direction="long") +
                  make_trades([-50, -100], direction="short"))
        metrics = analyzer.compute(trades, [10000] * 5, 10150, 10000)
        assert "long" in metrics["by_direction"]
        assert "short" in metrics["by_direction"]
        assert metrics["by_direction"]["long"]["win_rate"] == 100.0
        assert metrics["by_direction"]["short"]["win_rate"] == 0.0


class TestNoTrades:

    def test_empty_trade_list(self, analyzer):
        metrics = analyzer.compute([], [10000], 10000, 10000)
        assert metrics.get("total_trades", 0) == 0


class TestReturnMetrics:

    def test_total_return_positive(self, analyzer):
        trades = make_trades([500, 300, 200])
        metrics = analyzer.compute(trades, [10000, 10500, 10800, 11000], 11000, 10000)
        assert metrics["total_return_pct"] == 10.0

    def test_total_return_negative(self, analyzer):
        trades = make_trades([-300, -200, -100])
        metrics = analyzer.compute(trades, [10000, 9700, 9500, 9400], 9400, 10000)
        assert metrics["total_return_pct"] == pytest.approx(-6.0, abs=0.1)
