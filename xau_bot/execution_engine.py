"""
execution_engine.py
────────────────────
Handles order creation, fill simulation, and trade lifecycle management.

Supports three modes:
  • backtest  — historical replay with spread/slippage simulation
  • paper     — live market data with simulated fills (no real money)
  • live      — API-ready interface (broker integration plugged in here)

Realistic simulation features:
  • Spread modelling (fixed, random, or volatility-scaled)
  • Slippage on market orders
  • Commission deduction
  • Partial fills (TP1 partial close)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Protocol

from .strategy_engine import ActiveTrade, TradeDirection, TradeSetup, TradeState
from .risk_manager import RiskReport

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Interfaces
# ─────────────────────────────────────────────────────────────────────────────

class BrokerAPI(Protocol):
    """Protocol that any live broker adapter must implement."""

    def place_order(self, symbol: str, direction: str, lots: float,
                    sl: float, tp: float) -> str: ...

    def close_order(self, order_id: str, price: float) -> bool: ...

    def get_current_price(self, symbol: str) -> tuple[float, float]: ...  # bid, ask

    def get_account_balance(self) -> float: ...


# ─────────────────────────────────────────────────────────────────────────────
# Fill Models
# ─────────────────────────────────────────────────────────────────────────────

class FillModel(Enum):
    NEXT_OPEN  = "next_open"     # Fill at the open of the next bar
    TOUCH      = "touch"         # Fill when price touches entry level
    CURR_CLOSE = "current_close" # Fill at current bar's close


@dataclass
class OrderFill:
    order_id: int
    filled_price: float
    lot_size: float
    commission: float
    spread_cost: float
    slippage_applied: float
    timestamp: object


# ─────────────────────────────────────────────────────────────────────────────
# ExecutionEngine
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionEngine:
    """
    Manages the full lifecycle of orders from placement to close.
    In backtest/paper mode this is self-contained.
    In live mode it delegates to a BrokerAPI adapter.
    """

    def __init__(self, cfg: dict, broker: Optional[BrokerAPI] = None) -> None:
        ec = cfg.get("execution", {})
        bc = cfg.get("backtest", {})

        self._mode: str             = cfg.get("bot", {}).get("mode", "backtest")
        self._symbol: str           = cfg.get("bot", {}).get("symbol", "XAUUSD")
        self._spread: float         = ec.get("spread_pips", 3.0)
        self._max_slip: float       = ec.get("slippage_pips", 1.5)
        self._slip_model: str       = ec.get("slippage_model", "random")
        self._commission: float     = ec.get("commission_per_lot", 7.0)
        self._lot_size: float       = ec.get("lot_size", 100)
        self._partial_pct: float    = cfg.get("strategy", {}).get("partial_tp_pct", 0.5)

        fill_str = bc.get("fill_model", "next_open")
        self._fill_model = FillModel(fill_str)

        self._broker = broker
        self._pending_orders: dict[int, tuple[TradeSetup, RiskReport]] = {}
        self._next_order_id: int = 1
        self._order_log: list[dict] = []

    # ── Public API ──────────────────────────────────────────────────────────

    def submit_order(
        self,
        setup: TradeSetup,
        risk_report: RiskReport,
        current_bar: int,
        current_bar_data: dict,
    ) -> Optional[ActiveTrade]:
        """
        Attempt to fill an order. Returns an ActiveTrade if filled, else None.
        For limit orders, stores as pending and fills on next price touch.
        """
        if self._mode == "live":
            return self._submit_live(setup, risk_report)

        entry_type = "market"
        fill_price = self._simulate_fill_price(
            setup.entry_price,
            setup.direction,
            current_bar_data,
            entry_type,
        )

        if fill_price is None:
            return None

        commission = self._commission * risk_report.lot_size * 2  # round trip
        spread_cost = self._spread * risk_report.lot_size * self._lot_size

        order_id = self._next_order_id
        self._next_order_id += 1

        fill = OrderFill(
            order_id=order_id,
            filled_price=fill_price,
            lot_size=risk_report.lot_size,
            commission=commission,
            spread_cost=spread_cost,
            slippage_applied=abs(fill_price - setup.entry_price),
            timestamp=setup.timestamp,
        )

        self._log_order("open", setup, fill)

        trade = ActiveTrade(
            trade_id=order_id,
            setup=setup,
            direction=setup.direction,
            entry_price=fill_price,
            lot_size=risk_report.lot_size,
            sl_price=risk_report.sl_price,
            tp1_price=risk_report.tp1_price,
            tp2_price=risk_report.tp2_price,
            state=TradeState.OPEN,
            open_bar=current_bar,
        )

        logger.info(
            "Order FILLED: #%d %s %.2f lots @ %.2f  SL=%.2f  TP1=%.2f  TP2=%.2f",
            order_id, setup.direction.value, risk_report.lot_size,
            fill_price, risk_report.sl_price,
            risk_report.tp1_price, risk_report.tp2_price,
        )
        return trade

    def close_trade(
        self,
        trade: ActiveTrade,
        close_price: float,
        close_bar: int,
        reason: str,
        partial: bool = False,
    ) -> float:
        """
        Close a trade (fully or partially). Returns net PnL in USD.
        """
        fill_price = self._apply_close_slippage(close_price, trade.direction)
        commission = self._commission * trade.lot_size

        direction_sign = 1.0 if trade.direction == TradeDirection.LONG else -1.0
        price_diff = fill_price - trade.entry_price
        lot_value  = trade.lot_size * self._lot_size  # oz

        if partial:
            active_lots = trade.lot_size * self._partial_pct
        else:
            active_lots = trade.lot_size * (1.0 - self._partial_pct if trade.tp1_hit else 1.0)

        gross_pnl = direction_sign * price_diff * active_lots * self._lot_size
        net_pnl   = gross_pnl - commission

        if not partial:
            trade.close_price  = fill_price
            trade.close_bar    = close_bar
            trade.close_reason = reason
            trade.state        = TradeState.CLOSED
            trade.pnl          = net_pnl + trade.partial_close_pnl
            sl_dist = abs(trade.entry_price - trade.sl_price)
            trade.pnl_r = trade.pnl / (sl_dist * trade.lot_size * self._lot_size + 1e-10)

        self._log_order("close", trade.setup, None,
                        extra={"pnl": net_pnl, "reason": reason})
        logger.info(
            "Trade #%d CLOSED [%s] @ %.2f  PnL=%.2f  Reason=%s",
            trade.trade_id, trade.direction.value, fill_price, net_pnl, reason
        )
        return net_pnl

    # ── Fill Price Simulation ────────────────────────────────────────────────

    def _simulate_fill_price(
        self,
        intended_price: float,
        direction: TradeDirection,
        bar_data: dict,
        entry_type: str,
    ) -> Optional[float]:
        """
        Simulate realistic fill given spread and slippage.
        Returns None if fill conditions are not met (e.g., gap through price).
        """
        spread = self._spread
        slip   = self._compute_slippage(bar_data)

        # For a long entry: we pay the ask (entry + spread)
        # For a short entry: we receive the bid (entry - spread for buyer side)
        if direction == TradeDirection.LONG:
            fill = intended_price + spread + slip
        else:
            fill = intended_price - spread - slip

        # Validate fill is within bar range
        bar_high = bar_data.get("high", fill + 100)
        bar_low  = bar_data.get("low",  fill - 100)
        if not (bar_low <= fill <= bar_high):
            return None

        return round(fill, 3)

    def _compute_slippage(self, bar_data: dict) -> float:
        if self._slip_model == "fixed":
            return self._max_slip
        elif self._slip_model == "random":
            return random.uniform(0, self._max_slip)
        elif self._slip_model == "volatility_scaled":
            bar_range = bar_data.get("high", 0) - bar_data.get("low", 0)
            atr_proxy = bar_data.get("atr_proxy", bar_range)
            vol_ratio = bar_range / (atr_proxy + 1e-10)
            return min(self._max_slip * vol_ratio, self._max_slip * 2)
        return 0.0

    def _apply_close_slippage(self, price: float, direction: TradeDirection) -> float:
        slip = random.uniform(0, self._max_slip * 0.5)
        if direction == TradeDirection.LONG:
            return price - slip   # Selling into a slightly lower bid
        return price + slip

    # ── Live Trading ─────────────────────────────────────────────────────────

    def _submit_live(self, setup: TradeSetup, risk: RiskReport) -> Optional[ActiveTrade]:
        if not self._broker:
            raise RuntimeError("Live mode requires a BrokerAPI adapter.")
        try:
            order_id = self._broker.place_order(
                symbol=self._symbol,
                direction=setup.direction.value,
                lots=risk.lot_size,
                sl=risk.sl_price,
                tp=risk.tp2_price,
            )
            bid, ask = self._broker.get_current_price(self._symbol)
            fill_price = ask if setup.direction == TradeDirection.LONG else bid
            trade = ActiveTrade(
                trade_id=hash(order_id),
                setup=setup,
                direction=setup.direction,
                entry_price=fill_price,
                lot_size=risk.lot_size,
                sl_price=risk.sl_price,
                tp1_price=risk.tp1_price,
                tp2_price=risk.tp2_price,
                state=TradeState.OPEN,
            )
            return trade
        except Exception as exc:
            logger.error("Live order failed: %s", exc)
            return None

    # ── Logging ──────────────────────────────────────────────────────────────

    def _log_order(self, action: str, setup: TradeSetup,
                   fill: Optional[OrderFill], extra: dict = None) -> None:
        record = {
            "action": action,
            "timestamp": setup.timestamp,
            "direction": setup.direction.value,
            "session": setup.session,
        }
        if fill:
            record.update({
                "fill_price": fill.filled_price,
                "lots": fill.lot_size,
                "commission": fill.commission,
                "slippage": fill.slippage_applied,
            })
        if extra:
            record.update(extra)
        self._order_log.append(record)

    @property
    def order_log(self) -> list[dict]:
        return list(self._order_log)
