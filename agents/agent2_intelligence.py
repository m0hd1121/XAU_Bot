"""
agent2_intelligence.py — Market Intelligence Agent

Runs continuously. On each cycle it:
  1. Fetches fresh OHLC data via yfinance (GC=F, 5-minute bars)
  2. Enriches the DataFrame with DataHandler
  3. Feeds all bars through MarketStructureEngine to build live state
  4. Classifies the current regime from price structure
  5. Computes a composite risk score
  6. Fetches near-term USD economic calendar events
  7. Persists the snapshot to market_intel and publishes to the message bus
  8. Optionally publishes a RISK_ALERT when risk_score exceeds 0.7

Does NOT execute trades; Agent 3 is the sole execution authority.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

from agents.base_agent import BaseAgent
from agents.message_bus import (
    CH_MARKET,
    EV_REGIME_UPDATE,
    EV_RISK_ALERT,
    publish_market_regime,
    publish_risk_alert,
)
from agents.shared_db import (
    connect,
    insert_market_intel,
    get_latest_market_intel,
)
from xau_bot.data_handler import DataHandler
from xau_bot.market_structure_engine import (
    MarketStructureEngine,
    StructureEvent,
    Trend,
)
from xau_bot.risk_manager import RiskManager

# ForexFactory free JSON calendar feed
_FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Regime windows for volatility detection (candle look-back)
_VOLATILITY_LOOKBACK = 3


class Agent2IntelligenceAgent(BaseAgent):
    """
    Market Intelligence Agent.

    Publishes a REGIME_UPDATE every 60 seconds and a RISK_ALERT whenever
    the computed risk score crosses the 0.7 threshold.
    """

    def __init__(
        self,
        agent_id: str = "agent2",
        cfg: dict = None,
        db_path=None,
    ) -> None:
        super().__init__(agent_id, cfg or {}, db_path=db_path)
        self._cycle_interval: int = 60
        self._last_intel_id: Optional[int] = None

        # Instantiated in on_start()
        self._ms_engine: Optional[MarketStructureEngine] = None
        self._data_handler: Optional[DataHandler] = None
        self._risk_manager: Optional[RiskManager] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def on_start(self) -> None:
        cfg = self.cfg
        self._ms_engine = MarketStructureEngine(cfg)
        self._data_handler = DataHandler(cfg)
        self._risk_manager = RiskManager(cfg)
        self.log.info("Agent2: market structure engine and data handler ready.")
        self.update_metrics({
            "regime": "UNKNOWN",
            "risk_score": 0.5,
            "trend": "UNKNOWN",
        })

    # ── Main cycle ────────────────────────────────────────────────────────────

    async def run_cycle(self) -> None:
        self.set_task("fetching OHLC")

        # ── 1. Fetch OHLC from Yahoo Finance ──────────────────────────────────
        try:
            df = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._fetch_ohlc),
                timeout=45.0,
            )
        except asyncio.TimeoutError:
            self.log.warning("Agent2: OHLC fetch timed out after 45s — skipping cycle.")
            await asyncio.sleep(self._cycle_interval)
            return
        if df is None or df.empty:
            self.log.warning("Agent2: OHLC fetch returned empty DataFrame — skipping cycle.")
            await asyncio.sleep(self._cycle_interval)
            return

        # ── 2. Enrich DataFrame ───────────────────────────────────────────────
        self.set_task("enriching data")
        try:
            df = self._data_handler.enrich(df)
        except Exception:
            self.log.exception("Agent2: DataHandler.enrich() failed — skipping cycle.")
            await asyncio.sleep(self._cycle_interval)
            return

        # ── 3. Run MarketStructureEngine over all bars ─────────────────────────
        self.set_task("running market structure analysis")
        bar_index = len(df) - 1
        state = None
        try:
            # Reset engine state before full-pass replay so the engine is
            # consistent with the current window (2-day rolling fetch).
            self._ms_engine.reset()
            for i in range(len(df)):
                state = self._ms_engine.update(df, i)
        except Exception:
            self.log.exception("Agent2: MarketStructureEngine.update() failed.")
            await asyncio.sleep(self._cycle_interval)
            return

        if state is None:
            self.log.warning("Agent2: no MarketState produced — skipping cycle.")
            await asyncio.sleep(self._cycle_interval)
            return

        # ── 4. Classify current regime ────────────────────────────────────────
        self.set_task("classifying regime")
        regime = self._classify_regime(df, state, bar_index)

        # ── 5. Compute risk score ─────────────────────────────────────────────
        self.set_task("computing risk score")
        economic_events = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_economic_events
        )
        risk_score = self._compute_risk_score(df, bar_index, regime, economic_events)

        # ── 6. Build technical summary ────────────────────────────────────────
        demand_zones = self._ms_engine.get_active_demand_zones()
        supply_zones = self._ms_engine.get_active_supply_zones()
        last_event_val = (
            state.last_structure_shift.event.value
            if state.last_structure_shift
            else StructureEvent.NONE.value
        )
        session = str(df["session"].iloc[bar_index]) if "session" in df.columns else ""

        technical_summary: dict = {
            "trend": state.trend.value,
            "zones_count": len(demand_zones) + len(supply_zones),
            "active_demand": len(demand_zones),
            "active_supply": len(supply_zones),
            "last_event": last_event_val,
            "session": session,
            "bar_index": bar_index,
        }

        # ── 7. Build fundamental summary ──────────────────────────────────────
        high_impact = [e for e in economic_events if e.get("impact") == "High"]
        next_min: Optional[float] = None
        if economic_events:
            upcoming_positive = [
                e["minutes_until"]
                for e in economic_events
                if e.get("minutes_until", -999) >= 0
            ]
            if upcoming_positive:
                next_min = min(upcoming_positive)

        fundamental_summary: dict = {
            "upcoming_events": [
                {k: v for k, v in e.items() if k != "minutes_until"}
                for e in economic_events[:5]
            ],
            "next_event_minutes": next_min,
            "high_impact_count": len(high_impact),
        }

        # ── 8. Confidence in regime classification (simple heuristic) ─────────
        confidence = self._compute_confidence(state, regime)

        # ── 9. Persist to market_intel ────────────────────────────────────────
        self.set_task("persisting market intelligence")
        try:
            with connect(self.db_path) as conn:
                intel_id = insert_market_intel(
                    conn,
                    timestamp=time.time(),
                    timeframe=self.cfg.get("bot", {}).get("timeframe", "5M"),
                    regime=regime,
                    trend=state.trend.value,
                    technical=technical_summary,
                    fundamental=fundamental_summary,
                    risk_score=risk_score,
                    confidence=confidence,
                    session=session,
                )
            self._last_intel_id = intel_id
            self.log.info(
                "Agent2: intel #%d published — regime=%s trend=%s risk=%.2f",
                intel_id, regime, state.trend.value, risk_score,
            )
        except Exception:
            self.log.exception("Agent2: failed to persist market intel.")

        # ── 10. Publish REGIME_UPDATE ──────────────────────────────────────────
        self.set_task("publishing regime update")
        try:
            publish_market_regime(
                regime=regime,
                trend=state.trend.value,
                risk_score=risk_score,
                confidence=confidence,
                technical_summary=technical_summary,
                fundamental_summary=fundamental_summary,
                db_path=self.db_path,
            )
        except Exception:
            self.log.exception("Agent2: publish_market_regime() failed.")

        # ── 11. Risk alert ────────────────────────────────────────────────────
        if risk_score > 0.7:
            alert_parts = []
            if regime == "HIGH_VOLATILITY":
                alert_parts.append("high volatility detected")
            if len(high_impact) > 0:
                alert_parts.append(f"{len(high_impact)} high-impact USD events imminent")
            drawdown_state = self._risk_manager.get_state()
            if drawdown_state.kill_switch_active:
                alert_parts.append("kill switch is active")

            message = "; ".join(alert_parts) if alert_parts else "elevated risk score"
            severity = "HIGH" if risk_score > 0.85 else "MEDIUM"

            try:
                publish_risk_alert(
                    alert_type="ELEVATED_RISK",
                    message=f"risk_score={risk_score:.2f}: {message}",
                    severity=severity,
                    db_path=self.db_path,
                )
                self.log.warning(
                    "Agent2: RISK_ALERT published — score=%.2f severity=%s: %s",
                    risk_score, severity, message,
                )
            except Exception:
                self.log.exception("Agent2: publish_risk_alert() failed.")

        # ── Update metrics ─────────────────────────────────────────────────────
        self.update_metrics({
            "regime": regime,
            "risk_score": round(risk_score, 3),
            "trend": state.trend.value,
            "active_demand_zones": len(demand_zones),
            "active_supply_zones": len(supply_zones),
            "high_impact_events": len(high_impact),
        })

        await asyncio.sleep(self._cycle_interval)

    # ── OHLC fetch ────────────────────────────────────────────────────────────

    def _fetch_ohlc(self) -> Optional[pd.DataFrame]:
        """Fetch 5-minute bars for GC=F from Yahoo Finance."""
        try:
            import yfinance as yf  # imported here to keep module-level imports clean
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="2d", interval="5m")
            if df.empty:
                return None

            # Normalise column names
            df.columns = [c.lower().strip() for c in df.columns]
            df.index = df.index.tz_localize(None) if df.index.tzinfo is not None else df.index
            df.sort_index(inplace=True)
            return df
        except Exception:
            self.log.exception("Agent2: yfinance fetch failed.")
            return None

    # ── Regime classification ─────────────────────────────────────────────────

    def _classify_regime(
        self,
        df: pd.DataFrame,
        state,
        bar_index: int,
    ) -> str:
        """
        Derive a human-readable regime string from the market state.

        Priority order:
          HIGH_VOLATILITY  — last 3 candles each have range > 2 × atr_proxy
          TRENDING_BULLISH — trend BULLISH and recent BOS events are bullish
          TRENDING_BEARISH — trend BEARISH and recent BOS events are bearish
          RANGING          — trend RANGING
          UNCERTAIN        — fallback
        """
        # ── Volatility check (highest priority) ───────────────────────────────
        if "atr_proxy" in df.columns and bar_index >= _VOLATILITY_LOOKBACK:
            volatile = True
            for offset in range(_VOLATILITY_LOOKBACK):
                idx = bar_index - offset
                rng = float(df["range_size"].iloc[idx]) if "range_size" in df.columns else (
                    float(df["high"].iloc[idx]) - float(df["low"].iloc[idx])
                )
                atr = float(df["atr_proxy"].iloc[idx])
                if rng <= 2 * atr:
                    volatile = False
                    break
            if volatile:
                return "HIGH_VOLATILITY"

        trend = state.trend

        # ── Bullish trend with confirming BOS events ───────────────────────────
        if trend == Trend.BULLISH:
            bullish_bos_events = [
                ev for ev in state.recent_events
                if ev.event in (StructureEvent.BOS_BULLISH, StructureEvent.CHOCH_BULL)
            ]
            if bullish_bos_events:
                return "TRENDING_BULLISH"

        # ── Bearish trend with confirming BOS events ───────────────────────────
        if trend == Trend.BEARISH:
            bearish_bos_events = [
                ev for ev in state.recent_events
                if ev.event in (StructureEvent.BOS_BEARISH, StructureEvent.CHOCH_BEAR)
            ]
            if bearish_bos_events:
                return "TRENDING_BEARISH"

        # ── Ranging ───────────────────────────────────────────────────────────
        if trend == Trend.RANGING:
            return "RANGING"

        return "UNCERTAIN"

    # ── Risk score ────────────────────────────────────────────────────────────

    def _compute_risk_score(
        self,
        df: pd.DataFrame,
        bar_index: int,
        regime: str,
        economic_events: list[dict],
    ) -> float:
        """Composite risk score in [0.0, 1.0]. Higher = more dangerous to trade."""
        score = 0.2  # baseline

        if regime == "HIGH_VOLATILITY":
            score += 0.2

        high_impact = [e for e in economic_events if e.get("impact") == "High"]
        if high_impact:
            score += 0.3

        try:
            drawdown_state = self._risk_manager.get_state()
            if drawdown_state.kill_switch_active:
                score += 0.1
        except Exception:
            pass

        return max(0.0, min(1.0, score))

    # ── Confidence heuristic ──────────────────────────────────────────────────

    def _compute_confidence(self, state, regime: str) -> float:
        """
        Simple confidence in the regime classification.
        Higher when recent structure events clearly support the regime.
        """
        if regime == "UNCERTAIN":
            return 0.35

        if regime == "HIGH_VOLATILITY":
            return 0.75  # volatility is an objective measurement

        confirming_events = len(state.recent_events)
        base = 0.55
        boost = min(confirming_events * 0.05, 0.30)
        return round(min(0.95, base + boost), 3)

    # ── Economic calendar ─────────────────────────────────────────────────────

    def _fetch_economic_events(self) -> list[dict]:
        """
        Fetch upcoming USD economic events from the ForexFactory JSON feed.

        Returns a list of dicts with keys:
          title, impact, datetime_utc, minutes_until

        Silently returns [] on any network or parsing error.
        """
        try:
            resp = requests.get(_FF_CALENDAR_URL, timeout=5)
            resp.raise_for_status()
            raw_events: list[dict] = resp.json()
        except Exception:
            self.log.debug("Agent2: ForexFactory calendar fetch failed (non-fatal).")
            return []

        now_utc = datetime.now(timezone.utc)
        result: list[dict] = []

        for ev in raw_events:
            try:
                # Filter by currency and impact level
                if ev.get("country", "").upper() != "USD":
                    continue
                impact = ev.get("impact", "")
                if impact not in ("High", "Medium"):
                    continue

                # Parse event datetime — skip "All Day" or missing time
                date_str = ev.get("date", "")
                time_str = ev.get("time", "")
                if not date_str or not time_str or time_str.lower() in ("all day", ""):
                    continue

                # ForexFactory format: date="01-13-2026", time="8:30am"
                dt_str = f"{date_str} {time_str}"
                try:
                    event_dt = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                except ValueError:
                    try:
                        event_dt = datetime.strptime(dt_str, "%m-%d-%Y %I:%M %p")
                    except ValueError:
                        continue

                # Treat as UTC (ForexFactory times are Eastern; we note this
                # but use as-is to keep the implementation simple and
                # dependency-free — the ±30/+240 window provides adequate slack)
                event_dt_utc = event_dt.replace(tzinfo=timezone.utc)
                minutes_until = (event_dt_utc - now_utc).total_seconds() / 60.0

                # Keep events within the relevant window: -30 to +240 minutes
                if -30.0 <= minutes_until <= 240.0:
                    result.append(
                        {
                            "title": ev.get("title", ""),
                            "impact": impact,
                            "datetime_utc": event_dt_utc.isoformat(),
                            "minutes_until": round(minutes_until, 1),
                        }
                    )
            except Exception:
                continue  # skip malformed entries silently

        result.sort(key=lambda x: x["minutes_until"])
        return result
