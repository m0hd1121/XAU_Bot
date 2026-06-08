"""
strategy_engine.py
──────────────────
Translates raw market structure signals into concrete trade setups.

Entry logic (BOTH conditions must be true):
  1. Liquidity sweep occurred (stop hunt detected by MarketStructureEngine)
  2. Market structure shift confirmed (CHoCH or BOS in direction of trade)

Additionally filters by:
  - HTF bias alignment (optional)
  - Session window (optional)
  - Supply/demand zone proximity
  - Setup quality score (aggregated from multiple factors)

Exit logic:
  - Stop loss: structural level + buffer
  - TP1: 1.5R → partial close + move SL to break-even
  - TP2: 3R → full exit or trail
  - Trailing stop after break-even
  - Structural invalidation (price closes beyond SL structure)

No indicators used anywhere in this file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import pandas as pd

from .market_structure_engine import (
    MarketState, MarketStructureEngine, StructureEvent, Trend,
    SupplyDemandZone, ZoneType, SwingPoint,
)
from .data_handler import Candle

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

class TradeDirection(Enum):
    LONG  = "long"
    SHORT = "short"


class TradeState(Enum):
    PENDING  = auto()
    OPEN     = auto()
    PARTIAL  = auto()   # TP1 hit, runner active
    CLOSED   = auto()
    CANCELLED = auto()


@dataclass
class TradeSetup:
    """A candidate trade setup before execution."""
    bar_index: int
    timestamp: object
    direction: TradeDirection
    entry_price: float
    raw_sl_price: float        # SL at structural level (before buffer)
    nearest_zone: Optional[SupplyDemandZone]
    trigger_sweep_index: int
    trigger_shift_event: StructureEvent
    quality_score: float       # 0–1 composite score
    session: str
    session_weight: float
    atr_proxy: float
    notes: str = ""


@dataclass
class ActiveTrade:
    """A live position tracked through its lifecycle."""
    trade_id: int
    setup: TradeSetup
    direction: TradeDirection
    entry_price: float
    lot_size: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    state: TradeState = TradeState.OPEN
    open_bar: int = 0
    close_bar: int = -1
    close_price: float = 0.0
    pnl: float = 0.0
    pnl_r: float = 0.0          # PnL in R-multiples
    max_adverse_excursion: float = 0.0
    max_favourable_excursion: float = 0.0
    break_even_moved: bool = False
    tp1_hit: bool = False
    partial_close_pnl: float = 0.0
    close_reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# StrategyEngine
# ─────────────────────────────────────────────────────────────────────────────

class StrategyEngine:
    """
    Reads MarketState and produces TradeSetup objects when valid
    institutional-style entries are detected.
    """

    def __init__(self, cfg: dict, ms_engine: MarketStructureEngine) -> None:
        sc  = cfg.get("strategy", {})
        self._ms_engine = ms_engine
        self._require_htf_bias: bool   = sc.get("require_htf_bias", True)
        self._require_session: bool    = sc.get("require_session_window", True)
        self._entry_type: str          = sc.get("entry_type", "limit")
        self._limit_buffer_pct: float  = sc.get("limit_entry_buffer_pct", 0.0003)
        self._sl_buffer: float         = sc.get("sl_buffer_pips", 3.0)
        self._partial_tp_pct: float    = sc.get("partial_tp_pct", 0.5)
        self._tp1_rr: float            = sc.get("tp1_rr", 1.5)
        self._tp2_rr: float            = sc.get("tp2_rr", 3.0)
        self._use_be: bool             = sc.get("use_break_even", True)
        self._trail: bool              = sc.get("trail_after_be", True)
        self._trail_step: float        = sc.get("trail_step_pct", 0.003)

        self._min_quality: float       = cfg.get("psychology", {}).get("min_setup_quality_score", 0.6)

        # HTF bias — updated externally (e.g., from 4H analysis)
        self._htf_bias: Trend = Trend.UNKNOWN

        # Active trade counter (for open position awareness)
        self._next_trade_id: int = 1

    # ── Public API ──────────────────────────────────────────────────────────

    def set_htf_bias(self, bias: Trend) -> None:
        self._htf_bias = bias

    def evaluate(
        self,
        candle: Candle,
        state: MarketState,
        df: pd.DataFrame,
        open_trade_directions: list[TradeDirection],
    ) -> Optional[TradeSetup]:
        """
        Main entry-point: given the current candle and market state,
        return a TradeSetup if all conditions are met, else None.
        """
        i = candle.index

        # ── Session filter ───────────────────────────────────────────────────
        if self._require_session and candle.session in ("off_hours", "asian"):
            return None

        # ── Need a recent sweep ──────────────────────────────────────────────
        sweep = state.last_sweep
        if sweep is None or sweep.swept_at_index < i - 5:
            return None

        # ── Need a recent structure shift ────────────────────────────────────
        shift = state.last_structure_shift
        if shift is None or shift.index < i - 5:
            return None

        # ── Determine direction from the CHoCH / sweep pairing ──────────────
        direction = self._infer_direction(sweep, shift, state)
        if direction is None:
            return None

        # ── HTF bias alignment ────────────────────────────────────────────────
        if self._require_htf_bias and self._htf_bias != Trend.UNKNOWN:
            if (direction == TradeDirection.LONG  and self._htf_bias != Trend.BULLISH) or \
               (direction == TradeDirection.SHORT and self._htf_bias != Trend.BEARISH):
                return None

        # ── Avoid duplicate direction ─────────────────────────────────────────
        if direction in open_trade_directions:
            return None

        # ── Find entry zone ───────────────────────────────────────────────────
        entry_price, raw_sl, zone = self._compute_entry_sl(candle, state, direction, df, i)
        if entry_price is None or raw_sl is None:
            return None

        # ── Setup quality score ───────────────────────────────────────────────
        quality = self._score_setup(candle, state, direction, zone, shift, sweep)
        if quality < self._min_quality:
            logger.debug("Setup rejected: quality %.2f < %.2f at bar %d",
                         quality, self._min_quality, i)
            return None

        setup = TradeSetup(
            bar_index=i,
            timestamp=candle.timestamp,
            direction=direction,
            entry_price=entry_price,
            raw_sl_price=raw_sl,
            nearest_zone=zone,
            trigger_sweep_index=sweep.swept_at_index,
            trigger_shift_event=shift.event,
            quality_score=quality,
            session=candle.session,
            session_weight=candle.session_weight,
            atr_proxy=candle.range_size,   # fallback; backtester uses df atr_proxy
            notes=self._build_notes(sweep, shift, zone),
        )
        logger.info(
            "Setup found: %s @ %.2f  SL=%.2f  Q=%.2f  [bar %d  %s]",
            direction.value, entry_price, raw_sl, quality, i, shift.event.value
        )
        return setup

    def manage_open_trade(
        self,
        trade: ActiveTrade,
        candle: Candle,
        df: pd.DataFrame,
    ) -> ActiveTrade:
        """
        Update an open trade: check SL/TP hits, trail stop, partial close.
        Returns the modified trade object. Caller detects state change.
        """
        if trade.state not in (TradeState.OPEN, TradeState.PARTIAL):
            return trade

        high   = candle.high
        low    = candle.low
        close  = candle.close
        atr    = df["atr_proxy"].values[candle.index] if "atr_proxy" in df.columns else candle.range_size

        sl = trade.sl_price
        tp1 = trade.tp1_price
        tp2 = trade.tp2_price

        is_long  = trade.direction == TradeDirection.LONG
        is_short = trade.direction == TradeDirection.SHORT

        # ── Max Adverse / Favourable Excursion tracking ──────────────────────
        if is_long:
            mae = trade.entry_price - low
            mfe = high - trade.entry_price
        else:
            mae = high - trade.entry_price
            mfe = trade.entry_price - low

        trade.max_adverse_excursion  = max(trade.max_adverse_excursion, mae)
        trade.max_favourable_excursion = max(trade.max_favourable_excursion, mfe)

        # ── SL hit ───────────────────────────────────────────────────────────
        sl_hit = (is_long and low <= sl) or (is_short and high >= sl)
        if sl_hit:
            trade.close_price = sl
            trade.state = TradeState.CLOSED
            trade.close_bar = candle.index
            trade.close_reason = "stop_loss"
            return trade

        # ── TP1 hit ──────────────────────────────────────────────────────────
        tp1_hit = (is_long and high >= tp1) or (is_short and low <= tp1)
        if tp1_hit and not trade.tp1_hit:
            trade.tp1_hit = True
            # Partial close is recorded; state moves to PARTIAL
            trade.state = TradeState.PARTIAL
            trade.partial_close_pnl = self._calc_pnl_at(trade, tp1, is_long, partial_pct=self._partial_tp_pct)
            # Move SL to break-even
            if self._use_be:
                trade.sl_price = trade.entry_price
                trade.break_even_moved = True
                logger.debug("Break-even set at %.2f for trade %d", trade.entry_price, trade.trade_id)

        # ── TP2 / full close ─────────────────────────────────────────────────
        if trade.tp1_hit:
            tp2_hit = (is_long and high >= tp2) or (is_short and low <= tp2)
            if tp2_hit:
                trade.close_price = tp2
                trade.state = TradeState.CLOSED
                trade.close_bar = candle.index
                trade.close_reason = "tp2"
                return trade

            # ── Trailing stop ────────────────────────────────────────────────
            if self._trail and trade.break_even_moved:
                new_sl = self._compute_trail(trade, close, atr, is_long)
                if is_long and new_sl > trade.sl_price:
                    trade.sl_price = new_sl
                elif is_short and new_sl < trade.sl_price:
                    trade.sl_price = new_sl

        # ── Structural invalidation check ─────────────────────────────────────
        if self._is_structurally_invalidated(trade, candle, df):
            trade.close_price = close
            trade.state = TradeState.CLOSED
            trade.close_bar = candle.index
            trade.close_reason = "structure_invalidation"

        return trade

    # ── Private: Entry Calculation ──────────────────────────────────────────

    def _infer_direction(self, sweep, shift, state: MarketState) -> Optional[TradeDirection]:
        """
        Direction inference rules:
        - Sweep of lows + bullish CHoCH/BOS → LONG
        - Sweep of highs + bearish CHoCH/BOS → SHORT
        """
        if sweep.level_type in ("equal_low", "prev_low") and \
                shift.event in (StructureEvent.CHOCH_BULL, StructureEvent.BOS_BULLISH):
            return TradeDirection.LONG

        if sweep.level_type in ("equal_high", "prev_high") and \
                shift.event in (StructureEvent.CHOCH_BEAR, StructureEvent.BOS_BEARISH):
            return TradeDirection.SHORT

        # Fallback: use the shift event direction alone if sweep is ambiguous
        if shift.event in (StructureEvent.CHOCH_BULL, StructureEvent.BOS_BULLISH):
            return TradeDirection.LONG
        if shift.event in (StructureEvent.CHOCH_BEAR, StructureEvent.BOS_BEARISH):
            return TradeDirection.SHORT

        return None

    def _compute_entry_sl(
        self,
        candle: Candle,
        state: MarketState,
        direction: TradeDirection,
        df: pd.DataFrame,
        i: int,
    ) -> tuple[Optional[float], Optional[float], Optional[SupplyDemandZone]]:
        """
        Entry: at nearest S/D zone edge (limit order) or current close (market).
        SL: beyond the swing that was swept, plus buffer.
        """
        close = candle.close
        zone: Optional[SupplyDemandZone] = None

        if direction == TradeDirection.LONG:
            # Entry at demand zone top edge (buying at discount)
            zones = sorted(state.demand_zones, key=lambda z: abs(close - z.top))
            for z in zones:
                if z.bottom < close < z.top * (1 + 0.005):  # price near or in zone
                    zone = z
                    break

            if zone:
                entry = zone.top - (zone.top - zone.bottom) * self._limit_buffer_pct
            else:
                entry = close

            # SL below the sweep low or below swing low
            sweep = state.last_sweep
            if sweep and sweep.level_type in ("equal_low", "prev_low"):
                raw_sl = sweep.price - self._sl_buffer
            elif state.swing_lows:
                raw_sl = state.swing_lows[-1].price - self._sl_buffer
            else:
                return None, None, None

        else:  # SHORT
            zones = sorted(state.supply_zones, key=lambda z: abs(close - z.bottom))
            for z in zones:
                if z.bottom * (1 - 0.005) < close < z.top:
                    zone = z
                    break

            if zone:
                entry = zone.bottom + (zone.top - zone.bottom) * self._limit_buffer_pct
            else:
                entry = close

            sweep = state.last_sweep
            if sweep and sweep.level_type in ("equal_high", "prev_high"):
                raw_sl = sweep.price + self._sl_buffer
            elif state.swing_highs:
                raw_sl = state.swing_highs[-1].price + self._sl_buffer
            else:
                return None, None, None

        # Sanity: SL must be on the correct side of entry
        if direction == TradeDirection.LONG and raw_sl >= entry:
            return None, None, None
        if direction == TradeDirection.SHORT and raw_sl <= entry:
            return None, None, None

        return entry, raw_sl, zone

    # ── Private: Scoring ────────────────────────────────────────────────────

    def _score_setup(
        self,
        candle: Candle,
        state: MarketState,
        direction: TradeDirection,
        zone: Optional[SupplyDemandZone],
        shift,
        sweep,
    ) -> float:
        """
        Composite setup quality 0–1. Weights:
          0.30 — CHoCH (high quality) vs BOS (lower, continuation)
          0.20 — Session weight
          0.20 — Zone quality (if price is at a valid zone)
          0.15 — Candle confirmation (rejection wick / momentum)
          0.15 — Trend alignment (LTF trend matches HTF bias)
        """
        score = 0.0

        # ── Event quality ────────────────────────────────────────────────────
        choch_events = (StructureEvent.CHOCH_BULL, StructureEvent.CHOCH_BEAR)
        score += 0.30 if shift.event in choch_events else 0.15

        # ── Session ──────────────────────────────────────────────────────────
        score += candle.session_weight * 0.20

        # ── Zone quality ─────────────────────────────────────────────────────
        if zone:
            score += zone.quality_score * 0.20
        else:
            score += 0.05   # partial credit even without a clean zone

        # ── Candle confirmation ───────────────────────────────────────────────
        # Bullish entry: want a bullish rejection candle (lower wick > upper)
        # Bearish entry: want a bearish rejection candle (upper wick > lower)
        if direction == TradeDirection.LONG:
            if candle.lower_wick > candle.upper_wick * 1.5 and candle.lower_wick > 0:
                score += 0.15   # Strong bullish rejection
            elif candle.is_bullish:
                score += 0.08
        else:
            if candle.upper_wick > candle.lower_wick * 1.5 and candle.upper_wick > 0:
                score += 0.15
            elif candle.is_bearish:
                score += 0.08

        # ── Trend alignment ──────────────────────────────────────────────────
        ltf_trend = state.trend
        if (direction == TradeDirection.LONG  and ltf_trend == Trend.BULLISH) or \
           (direction == TradeDirection.SHORT and ltf_trend == Trend.BEARISH):
            score += 0.15
        elif ltf_trend == Trend.RANGING:
            score += 0.05   # Ranging markets are lower quality for trend entries

        return min(1.0, score)

    # ── Private: Trade Management ────────────────────────────────────────────

    def _compute_trail(self, trade: ActiveTrade, close: float,
                        atr: float, is_long: bool) -> float:
        step = close * self._trail_step
        if is_long:
            return close - step
        return close + step

    def _is_structurally_invalidated(
        self, trade: ActiveTrade, candle: Candle, df: pd.DataFrame
    ) -> bool:
        """
        A trade is structurally invalidated when the key structural level
        that justified the entry is broken on a candle close.
        This is separate from the SL — it's an early exit rule.
        """
        close = candle.close
        entry = trade.entry_price
        is_long = trade.direction == TradeDirection.LONG

        # If price closes below entry for a long (and SL not yet hit), warn
        # but only act if no partial close has occurred yet
        if not trade.tp1_hit:
            if is_long and close < entry * 0.997:     # 0.3% below entry
                return True
            if not is_long and close > entry * 1.003: # 0.3% above entry
                return True
        return False

    @staticmethod
    def _calc_pnl_at(trade: ActiveTrade, price: float,
                     is_long: bool, partial_pct: float) -> float:
        direction_sign = 1.0 if is_long else -1.0
        return direction_sign * (price - trade.entry_price) * trade.lot_size * 100 * partial_pct

    @staticmethod
    def _build_notes(sweep, shift, zone) -> str:
        parts = [f"sweep={sweep.level_type}@{sweep.price:.2f}",
                 f"shift={shift.event.value}"]
        if zone:
            parts.append(f"zone={zone.zone_type.value}[{zone.bottom:.2f}-{zone.top:.2f}]")
        return " | ".join(parts)
