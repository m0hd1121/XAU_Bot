"""
risk_manager.py
───────────────
Handles all capital protection logic:

  • Dynamic position sizing (structure-based SL + volatility scaling)
  • Daily loss limit enforcement
  • Maximum drawdown kill-switch
  • Per-trade risk budgeting
  • Drawdown tracking

No indicators used — volatility is estimated from raw price range (ATR-proxy).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskReport:
    """Outcome of a position-size calculation."""
    allowed: bool
    reason: str
    lot_size: float = 0.0
    risk_amount: float = 0.0
    sl_price: float = 0.0
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    sl_pips: float = 0.0
    risk_pct: float = 0.0


@dataclass
class DrawdownState:
    peak_equity: float
    current_equity: float
    daily_start_equity: float
    daily_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    kill_switch_active: bool = False
    trading_halted: bool = False
    halt_reason: str = ""


class RiskManager:
    """
    Central risk arbiter. Every potential trade must pass through
    `evaluate_trade()` before execution is permitted.
    """

    def __init__(self, cfg: dict) -> None:
        rc = cfg.get("risk", {})
        ec = cfg.get("execution", {})

        self._initial_capital: float  = rc.get("initial_capital", 10000.0)
        self._risk_per_trade: float   = rc.get("risk_per_trade", 0.01)
        self._max_risk: float         = rc.get("max_risk_per_trade", 0.02)
        self._daily_limit: float      = rc.get("daily_loss_limit", 0.03)
        self._kill_drawdown: float    = rc.get("max_drawdown_kill", 0.10)
        self._min_rr: float           = rc.get("min_reward_to_risk", 2.0)
        self._max_open: int           = rc.get("max_open_trades", 2)
        self._vol_lookback: int       = rc.get("volatility_lookback", 14)
        self._vol_scale: float        = rc.get("volatility_scale_factor", 1.5)

        self._sl_buffer: float        = cfg.get("strategy", {}).get("sl_buffer_pips", 3.0)
        self._lot_size: float         = ec.get("lot_size", 100)
        self._min_lot: float          = ec.get("min_lot", 0.01)
        self._max_lot: float          = ec.get("max_lot", 10.0)
        self._lot_step: float         = ec.get("lot_step", 0.01)
        self._commission: float       = ec.get("commission_per_lot", 7.0)

        # Mutable state
        self._equity: float = self._initial_capital
        self._peak: float   = self._initial_capital
        self._daily_start: float = self._initial_capital
        self._current_day: Optional[date] = None
        self._open_trades: int = 0
        self._kill_active: bool = False
        self._trading_halted: bool = False
        self._halt_reason: str = ""
        self._trade_history: list[dict] = []

    # ── Public API ──────────────────────────────────────────────────────────

    def evaluate_trade(
        self,
        entry_price: float,
        sl_price: float,
        direction: str,    # "long" | "short"
        atr_proxy: float,
        current_time: Optional[datetime] = None,
        open_trades: int = 0,
        psychology_modifier: float = 1.0,
    ) -> RiskReport:
        """
        Determine whether a trade is permissible and compute its parameters.

        Returns a RiskReport with allowed=False and a reason if any limit is hit.
        """
        # ── Hard stops ──────────────────────────────────────────────────────
        if self._kill_active:
            return RiskReport(False, "kill_switch_active")

        if self._trading_halted:
            return RiskReport(False, f"trading_halted: {self._halt_reason}")

        if open_trades >= self._max_open:
            return RiskReport(False, f"max_open_trades ({self._max_open}) reached")

        # ── Daily reset ──────────────────────────────────────────────────────
        if current_time:
            self._maybe_reset_daily(current_time.date())

        # ── Daily loss limit check ───────────────────────────────────────────
        daily_pnl_pct = (self._equity - self._daily_start) / (self._daily_start + 1e-10)
        if daily_pnl_pct <= -self._daily_limit:
            self._halt("daily_loss_limit")
            return RiskReport(False, "daily_loss_limit_breached")

        # ── Drawdown kill-switch ─────────────────────────────────────────────
        dd_pct = (self._peak - self._equity) / (self._peak + 1e-10)
        if dd_pct >= self._kill_drawdown - 1e-9:
            self._activate_kill_switch()
            return RiskReport(False, "max_drawdown_kill_switch")

        # ── SL direction sanity (before buffering) ───────────────────────────
        if direction == "long" and sl_price >= entry_price:
            return RiskReport(False, "sl_wrong_side_for_long")
        if direction == "short" and sl_price <= entry_price:
            return RiskReport(False, "sl_wrong_side_for_short")

        # ── SL distance validation ───────────────────────────────────────────
        sl_distance = abs(entry_price - sl_price)
        if sl_distance < 1e-6:
            return RiskReport(False, "sl_distance_zero")

        # Add structural buffer to SL
        buffered_sl = self._apply_sl_buffer(sl_price, direction)
        buffered_sl_distance = abs(entry_price - buffered_sl)

        # ── TP levels (minimum R:R gate) ─────────────────────────────────────
        tp1_rr = cfg_get_nested_value(2.0, "strategy", "tp1_rr")
        tp2_rr = cfg_get_nested_value(3.0, "strategy", "tp2_rr")
        tp1_price, tp2_price = self._compute_tp(entry_price, buffered_sl_distance,
                                                 direction, tp1_rr, tp2_rr)

        actual_rr = (abs(tp1_price - entry_price) / (buffered_sl_distance + 1e-10))
        if actual_rr < self._min_rr - 1e-9:
            return RiskReport(False, f"rr_too_low ({actual_rr:.2f} < {self._min_rr})")

        # ── Position sizing ──────────────────────────────────────────────────
        effective_risk_pct = self._risk_per_trade * psychology_modifier
        effective_risk_pct = max(0.001, min(effective_risk_pct, self._max_risk))

        risk_amount = self._equity * effective_risk_pct
        # Volatility scaling: widen risk budget slightly when volatility is high
        vol_ratio = buffered_sl_distance / (atr_proxy + 1e-10)
        if vol_ratio > self._vol_scale:
            # SL is wide relative to ATR — reduce size proportionally
            risk_amount *= self._vol_scale / vol_ratio

        lot_size = self._compute_lot_size(risk_amount, buffered_sl_distance)

        if lot_size < self._min_lot:
            return RiskReport(False, f"lot_size_too_small ({lot_size:.3f})")

        return RiskReport(
            allowed=True,
            reason="ok",
            lot_size=lot_size,
            risk_amount=risk_amount,
            sl_price=buffered_sl,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            sl_pips=buffered_sl_distance,
            risk_pct=effective_risk_pct,
        )

    def register_trade_open(self, lot_size: float) -> None:
        self._open_trades += 1

    def register_trade_close(self, pnl: float) -> None:
        self._open_trades = max(0, self._open_trades - 1)
        self._equity += pnl
        self._peak = max(self._peak, self._equity)
        dd_pct = (self._peak - self._equity) / (self._peak + 1e-10)

        if dd_pct >= self._kill_drawdown - 1e-9:
            self._activate_kill_switch()

        self._trade_history.append({"pnl": pnl, "equity": self._equity})
        logger.debug("Trade closed PnL=%.2f  equity=%.2f  DD=%.2f%%",
                     pnl, self._equity, dd_pct * 100)

    def get_state(self) -> DrawdownState:
        dd_pct = (self._peak - self._equity) / (self._peak + 1e-10)
        daily_pnl = self._equity - self._daily_start
        return DrawdownState(
            peak_equity=self._peak,
            current_equity=self._equity,
            daily_start_equity=self._daily_start,
            daily_pnl=daily_pnl,
            max_drawdown_pct=dd_pct,
            current_drawdown_pct=dd_pct,
            kill_switch_active=self._kill_active,
            trading_halted=self._trading_halted,
            halt_reason=self._halt_reason,
        )

    def reset_kill_switch(self) -> None:
        """Manual reset required after kill switch fires."""
        self._kill_active = False
        self._trading_halted = False
        self._halt_reason = ""
        logger.warning("Kill switch manually reset. Capital: %.2f", self._equity)

    def update_equity(self, equity: float) -> None:
        self._equity = equity
        self._peak = max(self._peak, equity)

    @property
    def equity(self) -> float:
        return self._equity

    @property
    def is_trading_allowed(self) -> bool:
        return not self._trading_halted and not self._kill_active

    # ── Private ─────────────────────────────────────────────────────────────

    def _compute_lot_size(self, risk_amount: float, sl_distance: float) -> float:
        """
        Lot size = risk_amount / (sl_distance_per_unit × lot_value_per_unit)

        For XAUUSD: 1 standard lot = 100 oz. Each $1 move = $100 per lot.
        sl_distance is in price units (e.g., USD for gold).
        """
        value_per_lot_per_unit = self._lot_size  # 100 oz × $1 per oz = $100 per $1 move
        raw_lots = risk_amount / (sl_distance * value_per_lot_per_unit + 1e-10)
        # Round to lot step
        lots = round(raw_lots / self._lot_step) * self._lot_step
        return max(self._min_lot, min(self._max_lot, lots))

    def _apply_sl_buffer(self, sl_price: float, direction: str) -> float:
        """Add a small buffer beyond the structural SL to avoid premature hits."""
        if direction == "long":
            return sl_price - self._sl_buffer
        return sl_price + self._sl_buffer

    def _compute_tp(self, entry: float, sl_dist: float,
                    direction: str, tp1_rr: float, tp2_rr: float) -> tuple[float, float]:
        sign = 1.0 if direction == "long" else -1.0
        tp1 = entry + sign * sl_dist * tp1_rr
        tp2 = entry + sign * sl_dist * tp2_rr
        return tp1, tp2

    def _maybe_reset_daily(self, today: date) -> None:
        if self._current_day == today:
            return
        if self._current_day is not None:
            # Actual day change — snapshot today's starting equity
            self._daily_start = self._equity
            logger.info("New trading day %s — daily equity reset to %.2f", today, self._equity)
        # First call: keep _daily_start at initial_capital (set in __init__)
        self._current_day = today

    def _halt(self, reason: str) -> None:
        if not self._trading_halted:
            self._trading_halted = True
            self._halt_reason = reason
            logger.warning("Trading HALTED: %s  equity=%.2f", reason, self._equity)

    def _activate_kill_switch(self) -> None:
        if not self._kill_active:
            self._kill_active = True
            self._trading_halted = True
            self._halt_reason = "max_drawdown_kill"
            logger.critical(
                "KILL SWITCH ACTIVATED — Max drawdown %.1f%% breached. Equity: %.2f",
                self._kill_drawdown * 100, self._equity
            )


def cfg_get_nested_value(default, *keys):
    """Tiny helper — returns default when cfg isn't threaded through here."""
    return default
