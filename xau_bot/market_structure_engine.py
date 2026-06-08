"""
market_structure_engine.py
──────────────────────────
Core intelligence of the bot. Analyzes raw OHLC to derive:

  • Swing highs and lows (fractal-based, no indicators)
  • Market structure: Higher Highs / Higher Lows / Lower Highs / Lower Lows
  • Break of Structure (BOS)
  • Change of Character (CHoCH)
  • Liquidity levels: equal highs/lows, previous session highs/lows
  • Liquidity sweeps (stop hunts above/below key levels)
  • Inducement zones
  • Supply and demand zones from price impulse + consolidation

All logic is pure price-based. Zero indicator dependency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class Trend(Enum):
    BULLISH = auto()
    BEARISH = auto()
    RANGING = auto()
    UNKNOWN = auto()


class StructureEvent(Enum):
    BOS_BULLISH  = "BOS_BULL"   # Bullish Break of Structure
    BOS_BEARISH  = "BOS_BEAR"   # Bearish Break of Structure
    CHOCH_BULL   = "CHoCH_BULL" # Change of Character → bullish
    CHOCH_BEAR   = "CHoCH_BEAR" # Change of Character → bearish
    SWEEP_HIGH   = "SWEEP_HIGH" # Liquidity swept above high
    SWEEP_LOW    = "SWEEP_LOW"  # Liquidity swept below low
    NONE         = "NONE"


class ZoneType(Enum):
    DEMAND = "demand"
    SUPPLY = "supply"


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SwingPoint:
    index: int
    timestamp: object
    price: float
    is_high: bool              # True = swing high, False = swing low
    broken: bool = False       # True once price closes beyond this level
    broken_at_index: int = -1

    @property
    def is_low(self) -> bool:
        return not self.is_high


@dataclass
class StructureLevel:
    index: int
    timestamp: object
    price: float
    level_type: str      # "HH", "HL", "LH", "LL"
    broken: bool = False
    broken_at_index: int = -1


@dataclass
class StructureShift:
    index: int
    timestamp: object
    event: StructureEvent
    broken_price: float
    direction: Trend
    sweep_index: int = -1   # Index of sweep that preceded this shift


@dataclass
class LiquidityLevel:
    index: int
    timestamp: object
    price: float
    level_type: str          # "equal_high", "equal_low", "prev_high", "prev_low", "inducement"
    swept: bool = False
    swept_at_index: int = -1
    session: str = ""


@dataclass
class SupplyDemandZone:
    zone_type: ZoneType
    top: float
    bottom: float
    origin_index: int
    origin_timestamp: object
    tested: bool = False
    test_count: int = 0
    invalidated: bool = False
    impulse_magnitude: float = 0.0   # Size of move that created the zone
    quality_score: float = 0.0


@dataclass
class MarketState:
    """Complete snapshot of market structure at a given bar."""
    bar_index: int
    trend: Trend
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows:  list[SwingPoint] = field(default_factory=list)
    structure_levels: list[StructureLevel] = field(default_factory=list)
    recent_events: list[StructureShift] = field(default_factory=list)
    liquidity_levels: list[LiquidityLevel] = field(default_factory=list)
    supply_zones: list[SupplyDemandZone] = field(default_factory=list)
    demand_zones: list[SupplyDemandZone] = field(default_factory=list)
    last_sweep: Optional[LiquidityLevel] = None
    last_structure_shift: Optional[StructureShift] = None


# ─────────────────────────────────────────────────────────────────────────────
# MarketStructureEngine
# ─────────────────────────────────────────────────────────────────────────────

class MarketStructureEngine:
    """
    Processes OHLC data bar by bar to maintain a live picture of market
    structure. Designed for both backtesting (full pass) and live streaming
    (incremental update).
    """

    def __init__(self, cfg: dict) -> None:
        sc = cfg.get("market_structure", {})
        self._swing_lookback: int    = sc.get("swing_lookback", 5)
        self._bos_confirm: int       = sc.get("bos_confirmation_candles", 1)
        self._choch_need_sweep: bool = sc.get("choch_require_sweep", True)
        self._eq_threshold: float    = sc.get("liquidity_equal_threshold", 0.0015)
        self._ind_lookback: int      = sc.get("inducement_lookback", 20)
        self._zone_merge_thr: float  = sc.get("zone_merge_threshold", 0.002)
        self._zone_max_age: int      = sc.get("zone_max_age_candles", 200)
        self._min_impulse: float     = sc.get("min_zone_impulse_ratio", 1.5)

        # Mutable state — updated incrementally
        self._swing_highs: list[SwingPoint]      = []
        self._swing_lows:  list[SwingPoint]      = []
        self._struct_levels: list[StructureLevel] = []
        self._shifts:  list[StructureShift]       = []
        self._liq_levels: list[LiquidityLevel]    = []
        self._supply_zones: list[SupplyDemandZone] = []
        self._demand_zones: list[SupplyDemandZone] = []
        self._trend: Trend = Trend.UNKNOWN
        self._last_sweep: Optional[LiquidityLevel] = None
        self._last_shift: Optional[StructureShift] = None

    # ── Public API ──────────────────────────────────────────────────────────

    def analyze(self, df: pd.DataFrame) -> list[MarketState]:
        """
        Full-pass analysis over a DataFrame. Returns a MarketState per bar.
        Only states from bar `swing_lookback` onwards are reliable.
        """
        states: list[MarketState] = []
        n = len(df)
        for i in range(n):
            state = self.update(df, i)
            states.append(state)
        return states

    def update(self, df: pd.DataFrame, i: int) -> MarketState:
        """Incremental update — call for each new bar."""
        self._detect_swings(df, i)
        self._classify_structure(i, df)
        self._detect_bos_choch(df, i)
        self._detect_liquidity_levels(df, i)
        self._detect_sweeps(df, i)
        self._detect_supply_demand_zones(df, i)
        self._expire_old_zones(i)

        return MarketState(
            bar_index=i,
            trend=self._trend,
            swing_highs=list(self._swing_highs),
            swing_lows=list(self._swing_lows),
            structure_levels=list(self._struct_levels),
            recent_events=list(self._shifts[-10:]),
            liquidity_levels=[l for l in self._liq_levels if not l.swept],
            supply_zones=[z for z in self._supply_zones if not z.invalidated],
            demand_zones=[z for z in self._demand_zones if not z.invalidated],
            last_sweep=self._last_sweep,
            last_structure_shift=self._last_shift,
        )

    def get_trend(self) -> Trend:
        return self._trend

    def reset(self) -> None:
        """Reset state — useful between backtest runs."""
        self.__init__({
            "market_structure": {
                "swing_lookback": self._swing_lookback,
                "bos_confirmation_candles": self._bos_confirm,
                "choch_require_sweep": self._choch_need_sweep,
                "liquidity_equal_threshold": self._eq_threshold,
                "inducement_lookback": self._ind_lookback,
                "zone_merge_threshold": self._zone_merge_thr,
                "zone_max_age_candles": self._zone_max_age,
                "min_zone_impulse_ratio": self._min_impulse,
            }
        })

    # ── Swing Detection ─────────────────────────────────────────────────────

    def _detect_swings(self, df: pd.DataFrame, i: int) -> None:
        """
        Identify swing highs/lows using a symmetric lookback window.
        A swing high at bar i: high[i] > all highs in [i-n, i-1] and [i+1, i+n].
        Requires future bars, so confirmation is naturally delayed by `lookback`.
        """
        n = self._swing_lookback
        if i < n or i + n >= len(df):
            return

        highs = df["high"].values
        lows  = df["low"].values
        ts    = df.index

        center_h = highs[i]
        center_l = lows[i]
        left_h   = highs[i - n : i]
        right_h  = highs[i + 1 : i + n + 1]
        left_l   = lows[i - n : i]
        right_l  = lows[i + 1 : i + n + 1]

        # Swing High: strict maximum in window
        if center_h > left_h.max() and center_h > right_h.max():
            # Avoid duplicate
            if not self._swing_highs or self._swing_highs[-1].index != i:
                self._swing_highs.append(SwingPoint(i, ts[i], center_h, is_high=True))

        # Swing Low: strict minimum in window
        if center_l < left_l.min() and center_l < right_l.min():
            if not self._swing_lows or self._swing_lows[-1].index != i:
                self._swing_lows.append(SwingPoint(i, ts[i], center_l, is_high=False))

    # ── Structure Classification ─────────────────────────────────────────────

    def _classify_structure(self, i: int, df: pd.DataFrame) -> None:
        """
        Classify the last two swing highs and swing lows to determine:
        HH/HL (bullish), LH/LL (bearish), or mixed (ranging).
        """
        if len(self._swing_highs) < 2 or len(self._swing_lows) < 2:
            return

        sh1, sh2 = self._swing_highs[-2], self._swing_highs[-1]  # older, newer
        sl1, sl2 = self._swing_lows[-2],  self._swing_lows[-1]

        hh = sh2.price > sh1.price
        hl = sl2.price > sl1.price
        lh = sh2.price < sh1.price
        ll = sl2.price < sl1.price

        level_type_h = "HH" if hh else ("LH" if lh else "EH")
        level_type_l = "HL" if hl else ("LL" if ll else "EL")

        # Update or add structure level for this swing high
        self._upsert_struct_level(sh2.index, sh2.timestamp, sh2.price, level_type_h)
        self._upsert_struct_level(sl2.index, sl2.timestamp, sl2.price, level_type_l)

        # Determine trend
        if hh and hl:
            self._trend = Trend.BULLISH
        elif lh and ll:
            self._trend = Trend.BEARISH
        else:
            self._trend = Trend.RANGING

    def _upsert_struct_level(self, idx, ts, price, ltype) -> None:
        for lvl in self._struct_levels:
            if lvl.index == idx:
                lvl.level_type = ltype
                return
        self._struct_levels.append(StructureLevel(idx, ts, price, ltype))
        # Keep only the last 50 structure levels
        if len(self._struct_levels) > 50:
            self._struct_levels = self._struct_levels[-50:]

    # ── BOS / CHoCH Detection ────────────────────────────────────────────────

    def _detect_bos_choch(self, df: pd.DataFrame, i: int) -> None:
        """
        Break of Structure (BOS): price closes beyond a same-direction swing point
        in the current trend — trend continuation confirmation.

        Change of Character (CHoCH): price closes beyond a COUNTER-trend swing
        point — first signal of trend reversal. Requires a liquidity sweep
        if choch_require_sweep is True.
        """
        if i < self._bos_confirm:
            return

        closes = df["close"].values
        highs  = df["high"].values
        lows   = df["low"].values
        ts     = df.index
        close  = closes[i]

        # ── Bullish BOS: close above last significant swing high ─────────────
        if self._trend == Trend.BULLISH and self._swing_highs:
            last_sh = self._swing_highs[-1]
            if close > last_sh.price and not last_sh.broken:
                last_sh.broken = True
                last_sh.broken_at_index = i
                shift = StructureShift(i, ts[i], StructureEvent.BOS_BULLISH,
                                       last_sh.price, Trend.BULLISH)
                self._register_shift(shift)

        # ── Bearish BOS: close below last significant swing low ──────────────
        elif self._trend == Trend.BEARISH and self._swing_lows:
            last_sl = self._swing_lows[-1]
            if close < last_sl.price and not last_sl.broken:
                last_sl.broken = True
                last_sl.broken_at_index = i
                shift = StructureShift(i, ts[i], StructureEvent.BOS_BEARISH,
                                       last_sl.price, Trend.BEARISH)
                self._register_shift(shift)

        # ── CHoCH: close beyond counter-trend swing ──────────────────────────
        sweep_ok = (self._last_sweep is not None and
                    self._last_sweep.swept_at_index >= i - 5)

        if self._trend == Trend.BULLISH and self._swing_lows and len(self._swing_lows) >= 2:
            # Price closing below the most recent higher low = potential CHoCH
            last_hl = self._swing_lows[-1]
            if close < last_hl.price:
                if not self._choch_need_sweep or sweep_ok:
                    shift = StructureShift(i, ts[i], StructureEvent.CHOCH_BEAR,
                                           last_hl.price, Trend.BEARISH,
                                           sweep_index=getattr(self._last_sweep, "swept_at_index", -1))
                    self._register_shift(shift)
                    self._trend = Trend.BEARISH

        elif self._trend == Trend.BEARISH and self._swing_highs and len(self._swing_highs) >= 2:
            # Price closing above the most recent lower high = potential CHoCH
            last_lh = self._swing_highs[-1]
            if close > last_lh.price:
                if not self._choch_need_sweep or sweep_ok:
                    shift = StructureShift(i, ts[i], StructureEvent.CHOCH_BULL,
                                           last_lh.price, Trend.BULLISH,
                                           sweep_index=getattr(self._last_sweep, "swept_at_index", -1))
                    self._register_shift(shift)
                    self._trend = Trend.BULLISH

    def _register_shift(self, shift: StructureShift) -> None:
        # Prevent duplicate shifts at the same index
        if self._shifts and self._shifts[-1].index == shift.index:
            return
        self._shifts.append(shift)
        self._last_shift = shift
        logger.debug("Structure event: %s @ %.2f [bar %d]",
                     shift.event.value, shift.broken_price, shift.index)

    # ── Liquidity Level Detection ────────────────────────────────────────────

    def _detect_liquidity_levels(self, df: pd.DataFrame, i: int) -> None:
        """
        Identify key liquidity pools:
        - Equal highs / equal lows (clustered stops)
        - Previous session highs/lows (obvious stop targets)
        - Inducement levels (minor swing points that trap traders)
        """
        if i < 2:
            return

        highs  = df["high"].values
        lows   = df["low"].values
        ts     = df.index
        sess   = df["session"].values if "session" in df.columns else [""] * len(df)

        # ── Equal highs / equal lows ─────────────────────────────────────────
        lookback = min(i, self._ind_lookback)
        for j in range(max(0, i - lookback), i - 1):
            h_ratio = abs(highs[j] - highs[i]) / (highs[i] + 1e-10)
            l_ratio = abs(lows[j]  - lows[i])  / (lows[i]  + 1e-10)

            if h_ratio < self._eq_threshold:
                lvl = LiquidityLevel(j, ts[j], highs[j], "equal_high", session=sess[j])
                if not self._liq_duplicate(lvl):
                    self._liq_levels.append(lvl)

            if l_ratio < self._eq_threshold:
                lvl = LiquidityLevel(j, ts[j], lows[j], "equal_low", session=sess[j])
                if not self._liq_duplicate(lvl):
                    self._liq_levels.append(lvl)

        # ── Previous session high/low ────────────────────────────────────────
        if i > 0 and sess[i] != sess[i - 1] and sess[i - 1] not in ("", "off_hours"):
            # Session just changed — mark yesterday's high/low as liquidity
            prev_sess = sess[i - 1]
            window = [k for k in range(max(0, i - 30), i) if sess[k] == prev_sess]
            if window:
                prev_h = highs[window].max()
                prev_l = lows[window].min()
                ph = LiquidityLevel(window[-1], ts[window[-1]], prev_h,
                                    "prev_high", session=prev_sess)
                pl = LiquidityLevel(window[-1], ts[window[-1]], prev_l,
                                    "prev_low", session=prev_sess)
                for lvl in (ph, pl):
                    if not self._liq_duplicate(lvl):
                        self._liq_levels.append(lvl)

        # Keep list manageable
        if len(self._liq_levels) > 200:
            self._liq_levels = [l for l in self._liq_levels if not l.swept][-100:]

    def _liq_duplicate(self, new_lvl: LiquidityLevel) -> bool:
        thr = new_lvl.price * self._eq_threshold * 2
        for existing in self._liq_levels:
            if (existing.level_type == new_lvl.level_type and
                    abs(existing.price - new_lvl.price) < thr):
                return True
        return False

    # ── Sweep Detection ──────────────────────────────────────────────────────

    def _detect_sweeps(self, df: pd.DataFrame, i: int) -> None:
        """
        A sweep occurs when price wicks beyond a liquidity level but then
        closes back on the other side — the classic 'stop hunt' pattern.
        """
        if i < 1:
            return

        high  = df["high"].values[i]
        low   = df["low"].values[i]
        close = df["close"].values[i]
        ts    = df.index[i]

        for lvl in self._liq_levels:
            if lvl.swept:
                continue

            # Sweep above a high: wick above the level, close below it
            if lvl.level_type in ("equal_high", "prev_high") and \
                    high > lvl.price and close < lvl.price:
                lvl.swept = True
                lvl.swept_at_index = i
                self._last_sweep = lvl
                shift = StructureShift(i, ts, StructureEvent.SWEEP_HIGH,
                                       lvl.price, Trend.BEARISH, sweep_index=i)
                self._shifts.append(shift)
                logger.debug("Sweep HIGH @ %.2f [bar %d]", lvl.price, i)

            # Sweep below a low: wick below the level, close above it
            elif lvl.level_type in ("equal_low", "prev_low") and \
                    low < lvl.price and close > lvl.price:
                lvl.swept = True
                lvl.swept_at_index = i
                self._last_sweep = lvl
                shift = StructureShift(i, ts, StructureEvent.SWEEP_LOW,
                                       lvl.price, Trend.BULLISH, sweep_index=i)
                self._shifts.append(shift)
                logger.debug("Sweep LOW @ %.2f [bar %d]", lvl.price, i)

    # ── Supply / Demand Zone Detection ──────────────────────────────────────

    def _detect_supply_demand_zones(self, df: pd.DataFrame, i: int) -> None:
        """
        Identify supply/demand zones from raw price impulses.

        Demand zone: consolidation base before a strong upward impulse.
        Supply zone: consolidation top before a strong downward impulse.

        Criteria:
        - Base candle(s): small range, indecision
        - Impulse candle: large body, minimum impulse_ratio × base range
        """
        n = self._swing_lookback
        if i < n + 2:
            return

        closes = df["close"].values
        opens  = df["open"].values
        highs  = df["high"].values
        lows   = df["low"].values
        ranges = highs - lows
        ts     = df.index
        atr    = df["atr_proxy"].values if "atr_proxy" in df.columns else ranges

        impulse_idx = i
        impulse_range = abs(closes[i] - opens[i])

        # Need impulse to be significantly larger than the base
        avg_recent_range = atr[max(0, i - 1)]
        if avg_recent_range < 1e-10:
            return

        if impulse_range < self._min_impulse * avg_recent_range:
            return

        # Bullish impulse → demand zone from the base before it
        if closes[i] > opens[i]:
            base_idx = i - 1
            base_top    = max(opens[base_idx], closes[base_idx])
            base_bottom = min(opens[base_idx], closes[base_idx])
            zone = SupplyDemandZone(
                zone_type=ZoneType.DEMAND,
                top=base_top,
                bottom=lows[base_idx],
                origin_index=base_idx,
                origin_timestamp=ts[base_idx],
                impulse_magnitude=impulse_range,
                quality_score=self._score_zone(df, base_idx, impulse_idx, ZoneType.DEMAND),
            )
            if not self._zone_duplicate(zone, self._demand_zones):
                self._demand_zones.append(zone)

        # Bearish impulse → supply zone from the base before it
        elif closes[i] < opens[i]:
            base_idx = i - 1
            base_top    = max(opens[base_idx], closes[base_idx])
            base_bottom = min(opens[base_idx], closes[base_idx])
            zone = SupplyDemandZone(
                zone_type=ZoneType.SUPPLY,
                top=highs[base_idx],
                bottom=base_bottom,
                origin_index=base_idx,
                origin_timestamp=ts[base_idx],
                impulse_magnitude=impulse_range,
                quality_score=self._score_zone(df, base_idx, impulse_idx, ZoneType.SUPPLY),
            )
            if not self._zone_duplicate(zone, self._supply_zones):
                self._supply_zones.append(zone)

        # Check existing zones for price re-entry (test/invalidation)
        self._check_zone_tests(df, i)

    def _check_zone_tests(self, df: pd.DataFrame, i: int) -> None:
        high  = df["high"].values[i]
        low   = df["low"].values[i]
        close = df["close"].values[i]

        for zone in self._demand_zones:
            if zone.invalidated:
                continue
            # Price re-enters the zone from above
            if low <= zone.top and close >= zone.bottom:
                zone.tested = True
                zone.test_count += 1
            # Price closes below zone bottom → invalidated
            if close < zone.bottom:
                zone.invalidated = True

        for zone in self._supply_zones:
            if zone.invalidated:
                continue
            # Price re-enters the zone from below
            if high >= zone.bottom and close <= zone.top:
                zone.tested = True
                zone.test_count += 1
            # Price closes above zone top → invalidated
            if close > zone.top:
                zone.invalidated = True

    def _score_zone(self, df: pd.DataFrame, base_idx: int,
                    impulse_idx: int, zone_type: ZoneType) -> float:
        """
        Score zone quality 0–1 based on:
        - Impulse magnitude vs ATR
        - Whether zone is at a swing point
        - Number of base candles (fewer = fresher)
        """
        score = 0.0
        atr = df["atr_proxy"].values[base_idx] if "atr_proxy" in df.columns else 1.0
        impulse_body = abs(df["close"].values[impulse_idx] - df["open"].values[impulse_idx])

        impulse_ratio = impulse_body / (atr + 1e-10)
        score += min(impulse_ratio / 4.0, 0.4)   # max 0.4 from impulse size

        # Reward if zone forms at a swing point
        at_swing = any(abs(sp.price - df["high"].values[base_idx]) < atr * 0.3
                       for sp in self._swing_highs + self._swing_lows)
        if at_swing:
            score += 0.3

        # Reward first-time test (untested zones are stronger)
        score += 0.2

        # Penalise if price has revisited zone area multiple times already
        revisits = sum(1 for z in (self._demand_zones if zone_type == ZoneType.DEMAND
                                   else self._supply_zones)
                       if abs(z.top - df["high"].values[base_idx]) < atr)
        score -= revisits * 0.05

        return max(0.0, min(1.0, score))

    def _zone_duplicate(self, new_zone: SupplyDemandZone,
                        existing: list[SupplyDemandZone]) -> bool:
        for z in existing:
            if z.invalidated:
                continue
            overlap = min(new_zone.top, z.top) - max(new_zone.bottom, z.bottom)
            zone_size = max(new_zone.top - new_zone.bottom, 1e-10)
            if overlap / zone_size > (1 - self._zone_merge_thr):
                return True
        return False

    def _expire_old_zones(self, current_index: int) -> None:
        cutoff = current_index - self._zone_max_age
        for zone in self._demand_zones + self._supply_zones:
            if zone.origin_index < cutoff and not zone.tested:
                zone.invalidated = True

    # ── Utility ─────────────────────────────────────────────────────────────

    def get_recent_bos_choch(self, lookback: int = 10) -> list[StructureShift]:
        """Return the most recent BOS/CHoCH events."""
        structural = [s for s in self._shifts
                      if s.event in (StructureEvent.BOS_BULLISH, StructureEvent.BOS_BEARISH,
                                     StructureEvent.CHOCH_BULL, StructureEvent.CHOCH_BEAR)]
        return structural[-lookback:]

    def get_active_demand_zones(self) -> list[SupplyDemandZone]:
        return [z for z in self._demand_zones if not z.invalidated]

    def get_active_supply_zones(self) -> list[SupplyDemandZone]:
        return [z for z in self._supply_zones if not z.invalidated]

    def price_in_zone(self, price: float,
                      zones: list[SupplyDemandZone]) -> Optional[SupplyDemandZone]:
        """Return the first zone containing `price`, or None."""
        for z in zones:
            if not z.invalidated and z.bottom <= price <= z.top:
                return z
        return None
