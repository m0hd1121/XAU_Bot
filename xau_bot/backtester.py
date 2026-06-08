"""
backtester.py
─────────────
Event-driven backtest engine. Replays historical OHLC data bar by bar,
routing each bar through the full pipeline:

  DataHandler → MarketStructureEngine → StrategyEngine
      → PsychologyLayer → RiskManager → ExecutionEngine

Designed for:
  • Realistic simulation (spread, slippage, commission)
  • Partial fills (TP1 partial close)
  • Daily equity resets
  • Session-aware trade limits
  • Full trade-by-trade logging

No lookahead bias: each bar only sees data up to and including itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from .data_handler import DataHandler
from .market_structure_engine import MarketStructureEngine, Trend
from .strategy_engine import StrategyEngine, ActiveTrade, TradeDirection, TradeState
from .risk_manager import RiskManager
from .execution_engine import ExecutionEngine
from .psychology_layer import PsychologyLayer
from .performance_analyzer import PerformanceAnalyzer

try:
    from .learning import LearningEngine
    from .learning.feature_extractor import FeatureVector
    _LEARNING_AVAILABLE = True
except ImportError:
    LearningEngine = None       # type: ignore[assignment,misc]
    FeatureVector  = None       # type: ignore[assignment]
    _LEARNING_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    trades: list[dict]
    equity_curve: list[float]
    daily_equity: list[dict]
    metrics: dict
    config: dict


class Backtester:
    """
    Orchestrates a full backtest run. Entry point: `run()`.
    """

    def __init__(self, cfg: dict, learning_engine=None) -> None:
        self._cfg = cfg
        self._bot_cfg  = cfg.get("bot", {})
        self._bt_cfg   = cfg.get("backtest", {})
        self._strat_cfg = cfg.get("strategy", {})

        self._symbol       = self._bot_cfg.get("symbol", "XAUUSD")
        self._start        = self._bt_cfg.get("start_date", "2022-01-01")
        self._end          = self._bt_cfg.get("end_date", "2024-12-31")
        self._log_trades   = self._bt_cfg.get("log_trades", True)
        self._partial_pct  = self._strat_cfg.get("partial_tp_pct", 0.5)
        self._htf_tf       = self._bot_cfg.get("htf_timeframe", "4H")

        # Optional learning engine (passed in or auto-created from config)
        self._learning: Optional[object] = learning_engine
        if self._learning is None and _LEARNING_AVAILABLE:
            lc = cfg.get("learning", {})
            if lc.get("enabled", False):
                self._learning = LearningEngine(cfg)
                self._learning.initialize()

        # Feature cache: trade_id → FeatureVector (for post-close learning update)
        self._feature_cache: dict = {}

        # Sub-systems (initialised fresh per run)
        self._data_handler: Optional[DataHandler]             = None
        self._ms_engine:    Optional[MarketStructureEngine]   = None
        self._strategy:     Optional[StrategyEngine]          = None
        self._risk:         Optional[RiskManager]             = None
        self._execution:    Optional[ExecutionEngine]         = None
        self._psychology:   Optional[PsychologyLayer]         = None

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> BacktestResult:
        """Execute a complete backtest. Returns a BacktestResult."""
        logger.info("=== Backtest START: %s → %s ===", self._start, self._end)

        # ── Initialise subsystems ────────────────────────────────────────────
        self._data_handler = DataHandler(self._cfg)
        self._ms_engine    = MarketStructureEngine(self._cfg)
        self._strategy     = StrategyEngine(self._cfg, self._ms_engine)
        self._risk         = RiskManager(self._cfg)
        self._execution    = ExecutionEngine(self._cfg)
        self._psychology   = PsychologyLayer(self._cfg)

        # ── Load data ────────────────────────────────────────────────────────
        full_df = self._data_handler.load()
        df = self._data_handler.slice(full_df, self._start, self._end)
        if df.empty:
            raise ValueError("No data in specified backtest date range.")
        logger.info("Backtest window: %d bars", len(df))

        # ── Compute HTF bias if available ────────────────────────────────────
        htf_bias_map = self._compute_htf_bias(full_df, df)

        # ── Main loop ────────────────────────────────────────────────────────
        open_trades: list[ActiveTrade] = []
        closed_trades: list[dict]     = []
        equity_curve: list[float]     = [self._risk.equity]
        daily_equity: list[dict]      = []
        last_day                      = None
        last_trade_direction: Optional[TradeDirection] = None
        last_trade_was_loss: bool     = False
        last_outcome_str: str         = "NONE"
        current_regime_snapshot       = None

        n = len(df)
        for i in range(n):
            candle   = self._data_handler.get_candle(df, i)
            ts       = candle.timestamp
            bar_data = {
                "open": candle.open, "high": candle.high,
                "low":  candle.low,  "close": candle.close,
                "atr_proxy": df["atr_proxy"].values[i] if "atr_proxy" in df.columns else candle.range_size,
            }
            atr_proxy = bar_data["atr_proxy"]

            # ── Daily bookkeeping ────────────────────────────────────────────
            today = ts.date() if hasattr(ts, "date") else None
            if today and today != last_day:
                self._psychology.reset_daily()
                if last_day is not None:
                    daily_equity.append({"date": str(last_day), "equity": self._risk.equity})
                last_day = today

            # ── Update market structure ──────────────────────────────────────
            state = self._ms_engine.update(df, i)

            # ── Regime detection (learning subsystem) ────────────────────────
            if self._learning and self._learning.enabled:
                try:
                    current_regime_snapshot = self._learning.detect_regime(df, i)
                except Exception:
                    current_regime_snapshot = None

            # ── Apply HTF bias ────────────────────────────────────────────────
            if htf_bias_map is not None:
                ts_key = str(ts)[:10]
                bias = htf_bias_map.get(ts_key, Trend.UNKNOWN)
                self._strategy.set_htf_bias(bias)

            # ── Manage open trades ────────────────────────────────────────────
            for trade in list(open_trades):
                prev_state = trade.state
                trade = self._strategy.manage_open_trade(trade, candle, df)

                # TP1 partial close trigger
                if trade.tp1_hit and prev_state == TradeState.OPEN:
                    partial_pnl = self._execution.close_trade(
                        trade, trade.tp1_price, i, "tp1_partial", partial=True
                    )
                    trade.partial_close_pnl = partial_pnl
                    self._risk.register_trade_close(partial_pnl)
                    equity_curve.append(self._risk.equity)

                # Full close
                if trade.state == TradeState.CLOSED:
                    remaining_pnl = self._execution.close_trade(
                        trade, trade.close_price, i, trade.close_reason, partial=False
                    )
                    total_pnl = trade.partial_close_pnl + remaining_pnl
                    self._risk.register_trade_close(remaining_pnl)

                    won = total_pnl > 0
                    if won:
                        self._psychology.record_win(i, candle.session)
                    else:
                        self._psychology.record_loss(i, candle.session)
                        if self._risk.get_state().kill_switch_active:
                            self._psychology.apply_kill_cooldown(i)

                    last_trade_direction = trade.direction
                    last_trade_was_loss  = not won
                    last_outcome_str     = "WIN" if won else "LOSS"

                    self._record_trade(closed_trades, trade, total_pnl, atr_proxy)

                    # ── Learning: post-trade update ───────────────────────────
                    if self._learning and self._learning.enabled:
                        trade_record = closed_trades[-1]
                        features = self._feature_cache.pop(trade.trade_id, None)
                        if features is not None:
                            try:
                                self._learning.record_trade(trade_record, features)
                                self._learning.post_trade_review(trade_record, features)
                            except Exception as _le:
                                logger.debug("Learning update error (non-fatal): %s", _le)

                    open_trades.remove(trade)
                    equity_curve.append(self._risk.equity)

                    logger.info(
                        "Trade #%d closed | %s | PnL=%.2f (%.2fR) | equity=%.2f",
                        trade.trade_id, trade.close_reason,
                        total_pnl, trade.pnl_r, self._risk.equity
                    )

            # ── Entry evaluation ──────────────────────────────────────────────
            if not self._risk.is_trading_allowed:
                continue

            open_dirs = [t.direction for t in open_trades]
            setup = self._strategy.evaluate(candle, state, df, open_dirs)

            if setup is not None:
                # Psychology check
                psych_verdict = self._psychology.approve(
                    setup_quality=setup.quality_score,
                    current_bar=i,
                    session=candle.session,
                    setup_direction=setup.direction.value,
                    last_trade_direction=(last_trade_direction.value
                                         if last_trade_direction else None),
                    last_trade_was_loss=last_trade_was_loss,
                )

                if not psych_verdict.approved:
                    logger.debug("Setup rejected by psychology: %s", psych_verdict.reason)
                    continue

                # Risk evaluation
                risk_report = self._risk.evaluate_trade(
                    entry_price=setup.entry_price,
                    sl_price=setup.raw_sl_price,
                    direction=setup.direction.value,
                    atr_proxy=atr_proxy,
                    current_time=ts if isinstance(ts, datetime) else None,
                    open_trades=len(open_trades),
                    psychology_modifier=psych_verdict.size_modifier,
                )

                if not risk_report.allowed:
                    logger.debug("Trade blocked by risk: %s", risk_report.reason)
                    continue

                # ── Learning: confidence gate + feature extraction ────────────
                _features = None
                if self._learning and self._learning.enabled and current_regime_snapshot:
                    try:
                        htf_bias_str = str(
                            htf_bias_map.get(str(ts)[:10], Trend.UNKNOWN).value
                            if htf_bias_map else "UNKNOWN"
                        )
                        _features = self._learning.extract_features(
                            setup              = setup,
                            state              = state,
                            candle             = candle,
                            df                 = df,
                            bar_index          = i,
                            regime_snapshot    = current_regime_snapshot,
                            consecutive_losses = self._psychology.consecutive_losses,
                            prev_outcome       = last_outcome_str,
                            htf_bias           = htf_bias_str,
                        )
                        if _features is not None:
                            breakdown = self._learning.get_setup_confidence(_features)
                            if not self._learning.is_confidence_sufficient(breakdown):
                                logger.debug(
                                    "Trade filtered by learning confidence: %.2f",
                                    breakdown.final_score,
                                )
                                continue
                            logger.debug(
                                "Learning confidence: %s",
                                self._learning.summarise_confidence(breakdown),
                            )
                    except Exception as _le:
                        logger.debug("Learning confidence check error (non-fatal): %s", _le)

                # Execute
                trade = self._execution.submit_order(setup, risk_report, i, bar_data)
                if trade:
                    self._risk.register_trade_open(risk_report.lot_size)
                    open_trades.append(trade)
                    # Cache features for post-trade learning update
                    if _features is not None:
                        self._feature_cache[trade.trade_id] = _features

        # ── Close any remaining open trades at last price ────────────────────
        for trade in open_trades:
            last_close = df["close"].values[-1]
            pnl = self._execution.close_trade(trade, last_close, n - 1, "end_of_data")
            self._risk.register_trade_close(pnl)
            self._record_trade(closed_trades, trade, pnl, 0.0)
            equity_curve.append(self._risk.equity)

        # ── Learning engine shutdown ──────────────────────────────────────────
        if self._learning and self._learning.enabled:
            try:
                self._learning.shutdown()
            except Exception:
                pass

        # ── Performance analysis ──────────────────────────────────────────────
        analyzer = PerformanceAnalyzer(self._cfg)
        metrics  = analyzer.compute(closed_trades, equity_curve,
                                    self._risk.equity,
                                    self._cfg["risk"]["initial_capital"])

        result = BacktestResult(
            trades=closed_trades,
            equity_curve=equity_curve,
            daily_equity=daily_equity,
            metrics=metrics,
            config=self._cfg,
        )

        logger.info("=== Backtest COMPLETE ===")
        logger.info("Trades: %d  |  Final equity: %.2f  |  Return: %.2f%%",
                    len(closed_trades), self._risk.equity, metrics.get("total_return_pct", 0))

        return result

    # ── HTF Bias Computation ─────────────────────────────────────────────────

    def _compute_htf_bias(
        self, full_df: pd.DataFrame, ltf_df: pd.DataFrame
    ) -> Optional[dict]:
        """
        Resample the LTF OHLC to the HTF timeframe and run a lightweight
        structure analysis to derive daily bias (Bullish/Bearish/Ranging).

        Returns a dict mapping date-string → Trend.
        """
        try:
            tf_map = {"4H": "4h", "1D": "1D", "1H": "1h", "15min": "15min"}
            tf = tf_map.get(self._htf_tf, "4h")
            htf = full_df.resample(tf).agg({
                "open": "first", "high": "max", "low": "min", "close": "last",
            }).dropna()

            if len(htf) < 10:
                return None

            htf_engine = MarketStructureEngine(self._cfg)
            bias_map: dict[str, Trend] = {}

            for j in range(len(htf)):
                # Enrich minimally: we need atr_proxy
                if j > 0:
                    prev_c = htf["close"].values[j - 1]
                    tr = max(
                        htf["high"].values[j] - htf["low"].values[j],
                        abs(htf["high"].values[j] - prev_c),
                        abs(htf["low"].values[j] - prev_c),
                    )
                else:
                    tr = htf["high"].values[j] - htf["low"].values[j]

                # Inject atr_proxy for the engine
                if "atr_proxy" not in htf.columns:
                    htf["atr_proxy"] = (htf["high"] - htf["low"]).rolling(14, min_periods=1).mean()

                htf_engine.update(htf, j)
                bias = htf_engine.get_trend()
                date_str = str(htf.index[j])[:10]
                bias_map[date_str] = bias

            return bias_map
        except Exception as exc:
            logger.warning("HTF bias computation failed: %s — proceeding without HTF filter.", exc)
            return None

    # ── Trade Recording ──────────────────────────────────────────────────────

    def _record_trade(
        self, closed_trades: list[dict], trade: ActiveTrade,
        pnl: float, atr_proxy: float
    ) -> None:
        sl_dist = abs(trade.entry_price - trade.sl_price)
        r_value = pnl / (sl_dist * trade.lot_size * 100 + 1e-10)
        record = {
            "trade_id":       trade.trade_id,
            "direction":      trade.direction.value,
            "open_bar":       trade.open_bar,
            "close_bar":      trade.close_bar,
            "open_time":      str(trade.setup.timestamp),
            "entry_price":    trade.entry_price,
            "close_price":    trade.close_price,
            "sl_price":       trade.sl_price,
            "tp1_price":      trade.tp1_price,
            "tp2_price":      trade.tp2_price,
            "lot_size":       trade.lot_size,
            "pnl":            round(pnl, 2),
            "pnl_r":          round(r_value, 3),
            "close_reason":   trade.close_reason,
            "tp1_hit":        trade.tp1_hit,
            "session":        trade.setup.session,
            "quality_score":  trade.setup.quality_score,
            "sweep_event":    trade.setup.trigger_shift_event.value,
            "mae":            round(trade.max_adverse_excursion, 3),
            "mfe":            round(trade.max_favourable_excursion, 3),
            "equity_after":   round(self._risk.equity, 2),
        }
        closed_trades.append(record)
