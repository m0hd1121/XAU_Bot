"""
agent3_trader.py — Live Trader Agent

The ONLY agent that executes real trades. Consumes market intelligence from
Agent 2 and strategy signals from Agent 1, then decides whether to enter,
manage, or exit positions.

Decision pipeline per cycle:
  1. Consume Agent 2 regime/risk update
  2. Consume Agent 1 strategy signals (STRATEGY_PROMOTED)
  3. Fetch fresh OHLC data
  4. Run MarketStructureEngine
  5. Manage existing open trades (SL/TP/trail)
  6. Evaluate new setups via StrategyEngine
  7. Risk check → Psychology filter → Learning confidence check
  8. Execute via ExecutionEngine → publish result

All decisions are persisted to trade_decisions with a full explanation dict.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from agents.base_agent import BaseAgent
from agents.message_bus import (
    CH_MARKET,
    CH_STRATEGY,
    CH_TRADES,
    EV_REGIME_UPDATE,
    EV_STRATEGY_PROMOTED,
    EV_TRADE_EXECUTED,
    EV_TRADE_CLOSED,
    EV_TRADE_REJECTED,
    publish_trade_executed,
    publish_trade_closed,
)
from agents.shared_db import (
    connect,
    insert_trade_decision,
    get_latest_market_intel,
    get_strategy_candidates,
)
from xau_bot.broker import build_broker
from xau_bot.data_handler import DataHandler
from xau_bot.execution_engine import ExecutionEngine
from xau_bot.learning.learning_engine import LearningEngine
from xau_bot.market_structure_engine import MarketStructureEngine, Trend
from xau_bot.psychology_layer import PsychologyLayer
from xau_bot.risk_manager import RiskManager
from xau_bot.strategy_engine import ActiveTrade, StrategyEngine, TradeDirection, TradeState

_CYCLE_SLEEP = 30  # seconds between trading cycles
_MAX_OPEN_TRADES = 2  # hard cap; also enforced by RiskManager


class Agent3TraderAgent(BaseAgent):
    """
    Live Trader Agent.

    Consumes intelligence from Agent 2 and promoted strategies from Agent 1,
    applies a full risk/psychology/learning filter stack, and executes trades
    via ExecutionEngine.  Maintains a closed-loop feedback channel to Agent 1
    for learning.
    """

    def __init__(
        self,
        agent_id: str = "agent3",
        cfg: dict = None,
        db_path=None,
    ) -> None:
        super().__init__(agent_id, cfg or {}, db_path=db_path)

        # Instantiated in on_start()
        self._broker = None
        self._risk_manager: Optional[RiskManager] = None
        self._psychology: Optional[PsychologyLayer] = None
        self._data_handler: Optional[DataHandler] = None
        self._ms_engine: Optional[MarketStructureEngine] = None
        self._strategy: Optional[StrategyEngine] = None
        self._learning_engine: Optional[LearningEngine] = None
        self._execution: Optional[ExecutionEngine] = None

        # Runtime state
        self._open_trades: dict[str, dict] = {}          # trade_id → state dict
        self._current_strategy_hash: Optional[str] = None
        self._current_features: dict = {}
        self._prev_outcome: str = "NONE"
        self._consecutive_losses: int = 0

        # Cache of latest market intel (refreshed from message bus each cycle)
        self._latest_intel: Optional[dict] = None
        self._latest_regime: str = "UNKNOWN"
        self._latest_risk_score: float = 0.5
        self._latest_fundamental: dict = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def on_start(self) -> None:
        cfg = self.cfg

        self._broker = build_broker(cfg)
        self._risk_manager = RiskManager(cfg)
        self._psychology = PsychologyLayer(cfg)
        self._data_handler = DataHandler(cfg)
        self._ms_engine = MarketStructureEngine(cfg)
        self._strategy = StrategyEngine(cfg, self._ms_engine)
        self._learning_engine = LearningEngine(cfg)
        self._execution = ExecutionEngine(cfg, self._broker)

        self._learning_engine.initialize()

        # Sync account equity into risk manager so drawdown tracking is accurate
        try:
            account_info = self._broker.get_account_info()
            equity = account_info.get("equity", 0.0)
            if equity > 0:
                self._risk_manager.update_equity(equity)
        except Exception:
            self.log.warning("Agent3: could not sync initial account equity.")

        self.log.info("Agent3: all subsystems initialised.")
        self.update_metrics({
            "open_trades_count": 0,
            "consecutive_losses": 0,
        })

    async def on_stop(self) -> None:
        if self._learning_engine is not None:
            try:
                self._learning_engine.shutdown()
            except Exception:
                self.log.exception("Agent3: learning engine shutdown error.")
        self.log.info("Agent3: stopped.")

    # ── Main cycle ────────────────────────────────────────────────────────────

    async def run_cycle(self) -> None:

        # ── Step 1: Consume Agent 2 market intelligence ───────────────────────
        self.set_task("consuming market intelligence")
        self._consume_market_intelligence()

        if self._latest_risk_score > 0.75:
            self.log.warning(
                "Agent3: risk_score=%.2f exceeds 0.75 threshold — deferring trading this cycle.",
                self._latest_risk_score,
            )
            self._record_decision("DEFER", f"risk_score={self._latest_risk_score:.2f} > 0.75")
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        # ── Step 2: Consume Agent 1 strategy signals ──────────────────────────
        self.set_task("consuming strategy signals")
        self._consume_strategy_signals()

        # ── Step 3: Fetch fresh OHLC data ─────────────────────────────────────
        self.set_task("fetching OHLC data")
        df = await asyncio.get_event_loop().run_in_executor(None, self._fetch_ohlc)
        if df is None or df.empty:
            self.log.warning("Agent3: OHLC fetch failed — skipping cycle.")
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        try:
            df = self._data_handler.enrich(df)
        except Exception:
            self.log.exception("Agent3: DataHandler.enrich() failed — skipping cycle.")
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        bar_index = len(df) - 1
        candle = self._data_handler.get_candle(df, bar_index)

        # ── Step 4: Run market structure ──────────────────────────────────────
        self.set_task("running market structure analysis")
        try:
            self._ms_engine.reset()
            state = None
            for i in range(len(df)):
                state = self._ms_engine.update(df, i)
        except Exception:
            self.log.exception("Agent3: MarketStructureEngine.update() failed.")
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        if state is None:
            self.log.warning("Agent3: no MarketState — skipping cycle.")
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        # ── Step 5: Manage existing open trades ───────────────────────────────
        self.set_task("managing open trades")
        await self._manage_open_trades(candle, df)

        # ── Step 6: Check trading gate ─────────────────────────────────────────
        if not self._risk_manager.is_trading_allowed:
            self.log.info("Agent3: trading halted by RiskManager — no new entries.")
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        if len(self._open_trades) >= _MAX_OPEN_TRADES:
            self.log.debug(
                "Agent3: %d/%d open trades — no new entries.",
                len(self._open_trades), _MAX_OPEN_TRADES,
            )
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        # ── Step 6 (cont.): Evaluate new setup ───────────────────────────────
        self.set_task("evaluating new setups")

        # Inject current HTF bias into the strategy engine
        htf_trend = self._trend_from_regime(self._latest_regime)
        self._strategy.set_htf_bias(htf_trend)

        open_directions = [
            t["direction"] for t in self._open_trades.values()
        ]

        setup = None
        try:
            setup = self._strategy.evaluate(candle, state, df, open_directions)
        except Exception:
            self.log.exception("Agent3: StrategyEngine.evaluate() raised an exception.")

        if setup is None:
            self.log.debug("Agent3: no setup at bar %d.", bar_index)
            self._record_decision(
                "REJECT",
                "no_setup",
                explanation={"bar_index": bar_index, "reason": "StrategyEngine returned None"},
            )
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        # ── Step 7: Risk check ─────────────────────────────────────────────────
        self.set_task("risk evaluation")
        risk_report = self._risk_manager.evaluate_trade(
            entry_price=setup.entry_price,
            sl_price=setup.raw_sl_price,
            direction=setup.direction.value,
            atr_proxy=setup.atr_proxy,
            current_time=datetime.now(),
            open_trades=len(self._open_trades),
        )
        if not risk_report.allowed:
            self.log.info("Agent3: trade rejected by RiskManager: %s", risk_report.reason)
            self._record_decision(
                "REJECT",
                f"risk_manager: {risk_report.reason}",
                explanation={
                    "direction": setup.direction.value,
                    "entry_price": setup.entry_price,
                    "risk_reason": risk_report.reason,
                },
            )
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        # ── Step 8: Psychology filter ─────────────────────────────────────────
        self.set_task("psychology filter")
        psych_verdict = self._psychology.approve(
            setup_quality=setup.quality_score,
            current_bar=bar_index,
            session=setup.session,
            setup_direction=setup.direction.value,
            last_trade_was_loss=(self._prev_outcome == "LOSS"),
        )
        if not psych_verdict.approved:
            self.log.info("Agent3: trade blocked by PsychologyLayer: %s", psych_verdict.reason)
            self._record_decision(
                "REJECT",
                f"psychology: {psych_verdict.reason}",
                explanation={
                    "direction": setup.direction.value,
                    "psych_reason": psych_verdict.reason,
                    "consecutive_losses": self._consecutive_losses,
                },
            )
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        # ── Step 9: Learning confidence check ─────────────────────────────────
        self.set_task("learning confidence check")
        confidence_score: Optional[float] = None
        features = None

        if self._learning_engine.enabled:
            try:
                regime_snapshot = self._learning_engine.detect_regime(df, bar_index)
                features = self._learning_engine.extract_features(
                    setup=setup,
                    state=state,
                    candle=candle,
                    df=df,
                    bar_index=bar_index,
                    regime_snapshot=regime_snapshot,
                    consecutive_losses=self._consecutive_losses,
                    prev_outcome=self._prev_outcome,
                    htf_bias=htf_trend.value if htf_trend else "UNKNOWN",
                )
                if features is not None:
                    breakdown = self._learning_engine.get_setup_confidence(features)
                    confidence_score = breakdown.final_score

                    if not self._learning_engine.is_confidence_sufficient(breakdown):
                        reason = (
                            f"confidence_too_low ({confidence_score:.3f} < threshold)"
                        )
                        self.log.info("Agent3: %s", reason)
                        self._record_decision(
                            "REJECT",
                            f"learning: {reason}",
                            explanation={
                                "confidence_score": confidence_score,
                                "direction": setup.direction.value,
                            },
                        )
                        await asyncio.sleep(_CYCLE_SLEEP)
                        return
            except Exception:
                self.log.exception(
                    "Agent3: learning engine check raised exception (non-fatal — proceeding)."
                )
                features = None
                confidence_score = None

        # ── Step 10: Execute trade ────────────────────────────────────────────
        self.set_task("executing trade")

        account_info: dict = {}
        try:
            account_info = self._broker.get_account_info()
        except Exception:
            self.log.debug("Agent3: could not fetch account info for explanation dict.")

        drawdown_state = self._risk_manager.get_state()

        explanation = {
            "strategy_hash": self._current_strategy_hash,
            "regime": self._latest_regime,
            "risk_score": self._latest_risk_score,
            "quality_score": setup.quality_score,
            "direction": setup.direction.value,
            "entry_price": setup.entry_price,
            "sl_price": risk_report.sl_price,
            "tp1_price": risk_report.tp1_price,
            "tp2_price": risk_report.tp2_price,
            "lot_size": risk_report.lot_size,
            "session": setup.session,
            "consecutive_losses": self._consecutive_losses,
            "account_equity": account_info.get("equity", 0),
            "current_drawdown_pct": drawdown_state.current_drawdown_pct,
            "learning_confidence": confidence_score,
            "fundamental_events": self._latest_fundamental.get("upcoming_events", [])[:2],
            "why_executed": (
                "All filters passed: risk OK, regime OK, quality OK, confidence OK"
            ),
        }

        # Submit via ExecutionEngine
        bar_data = {
            "open": float(df["open"].iloc[bar_index]),
            "high": float(df["high"].iloc[bar_index]),
            "low": float(df["low"].iloc[bar_index]),
            "close": float(df["close"].iloc[bar_index]),
            "atr_proxy": float(df["atr_proxy"].iloc[bar_index])
            if "atr_proxy" in df.columns else setup.atr_proxy,
        }

        active_trade: Optional[ActiveTrade] = None
        try:
            active_trade = self._execution.submit_order(
                setup=setup,
                risk_report=risk_report,
                current_bar=bar_index,
                current_bar_data=bar_data,
            )
        except Exception:
            self.log.exception("Agent3: ExecutionEngine.submit_order() raised an exception.")

        if active_trade is None:
            broker_error = "execution_engine returned None (order not filled)"
            self.log.warning("Agent3: trade not filled — %s", broker_error)
            self._record_decision(
                "REJECT",
                broker_error,
                explanation={**explanation, "broker_error": broker_error},
            )
            await asyncio.sleep(_CYCLE_SLEEP)
            return

        # ── Trade registered ───────────────────────────────────────────────────
        trade_id = str(active_trade.trade_id)
        self._risk_manager.register_trade_open(risk_report.lot_size)

        self._open_trades[trade_id] = {
            "active_trade": active_trade,
            "setup": setup,
            "risk_report": risk_report,
            "features": features,
            "regime_at_entry": self._latest_regime,
            "session_at_entry": setup.session,
            "explanation": explanation,
        }

        # Store features for post-trade learning
        if features is not None:
            self._current_features[trade_id] = features

        self.log.info(
            "Agent3: trade EXECUTED #%s %s %.2f lots @ %.2f  SL=%.2f  Q=%.2f",
            trade_id, setup.direction.value, risk_report.lot_size,
            setup.entry_price, risk_report.sl_price, setup.quality_score,
        )

        # Publish trade executed event
        try:
            publish_trade_executed(
                trade_id=trade_id,
                direction=setup.direction.value,
                lots=risk_report.lot_size,
                entry_price=active_trade.entry_price,
                sl_price=risk_report.sl_price,
                tp1_price=risk_report.tp1_price,
                tp2_price=risk_report.tp2_price,
                explanation=explanation,
                db_path=self.db_path,
            )
        except Exception:
            self.log.exception("Agent3: publish_trade_executed() failed.")

        # Persist EXECUTE decision
        self._record_decision(
            "EXECUTE",
            "all_filters_passed",
            trade_id=trade_id,
            strategy_id=self._current_strategy_hash,
            intel_id=self._get_latest_intel_id(),
            explanation=explanation,
        )

        self.update_metrics({
            "last_trade_direction": setup.direction.value,
            "last_trade_entry": setup.entry_price,
            "open_trades_count": len(self._open_trades),
            "consecutive_losses": self._consecutive_losses,
        })

        await asyncio.sleep(_CYCLE_SLEEP)

    # ── Trade management ──────────────────────────────────────────────────────

    async def _manage_open_trades(self, candle, df: pd.DataFrame) -> None:
        """
        Iterate over all open trades, update via StrategyEngine.manage_open_trade(),
        and handle closures with learning feedback.
        """
        closed_ids: list[str] = []

        for trade_id, trade_state in list(self._open_trades.items()):
            active_trade: ActiveTrade = trade_state["active_trade"]

            # Skip if already closed from a previous sub-step
            if active_trade.state == TradeState.CLOSED:
                closed_ids.append(trade_id)
                continue

            try:
                updated_trade = self._strategy.manage_open_trade(active_trade, candle, df)
                trade_state["active_trade"] = updated_trade
            except Exception:
                self.log.exception("Agent3: manage_open_trade() raised an exception for trade %s.", trade_id)
                continue

            if updated_trade.state == TradeState.CLOSED:
                closed_ids.append(trade_id)
                await self._handle_trade_closure(trade_id, trade_state, updated_trade)

        for trade_id in closed_ids:
            self._open_trades.pop(trade_id, None)

    async def _handle_trade_closure(
        self,
        trade_id: str,
        trade_state: dict,
        active_trade: ActiveTrade,
    ) -> None:
        """Post-closure bookkeeping: risk, psychology, learning, and publishing."""
        setup = trade_state.get("setup")
        pnl = active_trade.pnl
        pnl_r = active_trade.pnl_r
        close_reason = active_trade.close_reason or "unknown"
        outcome = "WIN" if pnl > 1e-9 else ("LOSS" if pnl < -1e-9 else "BE")

        self.log.info(
            "Agent3: trade CLOSED #%s %s  PnL=%.2f (%.2fR)  reason=%s",
            trade_id, active_trade.direction.value, pnl, pnl_r, close_reason,
        )

        # Update RiskManager
        self._risk_manager.register_trade_close(pnl)

        # Update psychology
        session = setup.session if setup else ""
        close_bar = active_trade.close_bar if active_trade.close_bar >= 0 else 0
        if outcome == "WIN":
            self._psychology.record_win(close_bar, session)
            self._consecutive_losses = 0
        else:
            self._psychology.record_loss(close_bar, session)
            if outcome == "LOSS":
                self._consecutive_losses += 1

        self._prev_outcome = outcome

        # Learning feedback
        features = trade_state.get("features") or self._current_features.pop(trade_id, None)
        if features is not None and self._learning_engine.enabled:
            trade_record = {
                "trade_id": int(trade_id) if trade_id.isdigit() else hash(trade_id) & 0x7FFFFFFF,
                "pnl": pnl,
                "pnl_r": pnl_r,
                "outcome": outcome,
                "close_reason": close_reason,
                "regime": trade_state.get("regime_at_entry", "UNKNOWN"),
                "session": session,
                "strategy_hash": self._current_strategy_hash,
            }
            try:
                self._learning_engine.record_trade(trade_record, features)
            except Exception:
                self.log.exception("Agent3: learning_engine.record_trade() failed.")

        # Publish TRADE_CLOSED to feedback channel for Agent 1
        try:
            publish_trade_closed(
                trade_id=trade_id,
                pnl=pnl,
                pnl_r=pnl_r,
                close_reason=close_reason,
                outcome=outcome,
                db_path=self.db_path,
            )
        except Exception:
            self.log.exception("Agent3: publish_trade_closed() failed.")

        # Also publish an enriched feedback event on CH_TRADES for Agent 1
        try:
            self.publish(
                CH_TRADES,
                EV_TRADE_CLOSED,
                {
                    "trade_id": trade_id,
                    "pnl": pnl,
                    "pnl_r": pnl_r,
                    "outcome": outcome,
                    "close_reason": close_reason,
                    "genome_hash": self._current_strategy_hash,
                    "session": session,
                    "regime_at_entry": trade_state.get("regime_at_entry", "UNKNOWN"),
                    "timestamp": time.time(),
                },
                ttl_seconds=86400,
            )
        except Exception:
            self.log.exception("Agent3: CH_TRADES feedback publish failed.")

        # Persist closure decision
        self._record_decision(
            "EXECUTE",
            f"closed_{outcome.lower()}: {close_reason}",
            trade_id=trade_id,
            explanation={
                "outcome": outcome,
                "pnl": pnl,
                "pnl_r": pnl_r,
                "close_reason": close_reason,
            },
        )

    # ── Message bus consumers ─────────────────────────────────────────────────

    def _consume_market_intelligence(self) -> None:
        """
        Poll CH_MARKET for REGIME_UPDATE events.  Keeps the most recent one.
        If the database read fails, fall back to the last known intel from
        the shared_db market_intel table.
        """
        try:
            events = self.poll_events(
                [CH_MARKET],
                hwm_key="market",
                limit=20,
                event_types=[EV_REGIME_UPDATE],
            )
            if events:
                # Take the latest event payload
                latest_ev = events[-1]["payload"]
                self._latest_regime = latest_ev.get("regime", "UNKNOWN")
                self._latest_risk_score = float(latest_ev.get("risk_score", 0.5))
                self._latest_fundamental = latest_ev.get("fundamental", {})
                self._latest_intel = latest_ev
                self.log.debug(
                    "Agent3: consumed regime update — regime=%s risk=%.2f",
                    self._latest_regime, self._latest_risk_score,
                )
        except Exception:
            self.log.debug("Agent3: message bus poll failed, falling back to DB.")
            try:
                with connect(self.db_path) as conn:
                    row = get_latest_market_intel(conn)
                if row:
                    self._latest_regime = row.get("regime", "UNKNOWN")
                    self._latest_risk_score = float(row.get("risk_score", 0.5))
                    self._latest_fundamental = row.get("fundamental", {})
            except Exception:
                self.log.debug("Agent3: market_intel DB fallback also failed.")

    def _consume_strategy_signals(self) -> None:
        """Poll CH_STRATEGY for STRATEGY_PROMOTED events and update the active genome hash."""
        try:
            events = self.poll_events(
                [CH_STRATEGY],
                hwm_key="strategy",
                limit=10,
                event_types=[EV_STRATEGY_PROMOTED],
            )
            for ev in events:
                genome_hash = ev["payload"].get("genome_hash")
                if genome_hash:
                    self._current_strategy_hash = genome_hash
                    self.log.info(
                        "Agent3: strategy promoted — genome_hash=%s", genome_hash
                    )
        except Exception:
            self.log.debug("Agent3: strategy signal poll failed (non-fatal).")

    # ── OHLC fetch ────────────────────────────────────────────────────────────

    def _fetch_ohlc(self) -> Optional[pd.DataFrame]:
        """Fetch 5-minute OHLC for GC=F from Yahoo Finance."""
        try:
            import yfinance as yf
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="2d", interval="5m")
            if df.empty:
                return None
            df.columns = [c.lower().strip() for c in df.columns]
            df.index = df.index.tz_localize(None) if df.index.tzinfo is not None else df.index
            df.sort_index(inplace=True)
            return df
        except Exception:
            self.log.exception("Agent3: yfinance fetch failed.")
            return None

    # ── Helper: trend from regime ─────────────────────────────────────────────

    @staticmethod
    def _trend_from_regime(regime: str) -> Trend:
        """Map a regime string published by Agent 2 back to a Trend enum."""
        mapping = {
            "TRENDING_BULLISH": Trend.BULLISH,
            "TRENDING_BEARISH": Trend.BEARISH,
            "RANGING": Trend.RANGING,
        }
        return mapping.get(regime, Trend.UNKNOWN)

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _record_decision(
        self,
        decision: str,
        reason: str,
        *,
        trade_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        intel_id: Optional[int] = None,
        explanation: Optional[dict] = None,
    ) -> None:
        """Persist a trade decision row with full explanation."""
        try:
            with connect(self.db_path) as conn:
                insert_trade_decision(
                    conn,
                    decision=decision,
                    reason=reason,
                    trade_id=trade_id,
                    strategy_id=strategy_id or self._current_strategy_hash,
                    intel_id=intel_id,
                    explanation=explanation or {},
                )
        except Exception:
            self.log.debug("Agent3: insert_trade_decision() failed (non-fatal).")

    def _get_latest_intel_id(self) -> Optional[int]:
        """Return the row-id of the most recent market_intel row, or None."""
        try:
            with connect(self.db_path) as conn:
                row = get_latest_market_intel(conn)
            if row:
                return row.get("id")
        except Exception:
            pass
        return None
