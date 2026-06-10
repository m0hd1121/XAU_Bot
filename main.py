"""
main.py
───────
Entry point for the XAU/USD Price Action Bot.

Usage:
  python main.py                            # Run backtest with config.yaml
  python main.py --config config.yaml       # Explicit config path
  python main.py --mode paper               # Override mode
  python main.py --start 2023-01-01         # Override backtest start
  python main.py --end   2023-12-31         # Override backtest end
  python main.py --generate-data            # Generate synthetic sample data
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml


def setup_logging(cfg: dict) -> None:
    log_cfg  = cfg.get("logging", {})
    level    = getattr(logging, log_cfg.get("level", "INFO"), logging.INFO)
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_cfg.get("log_to_file", False):
        log_path = Path(log_cfg.get("log_file", "logs/xau_bot.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="XAU/USD Price Action Trading Bot"
    )
    p.add_argument("--config",        default="config.yaml", help="Path to config YAML")
    p.add_argument("--mode",          choices=["backtest", "paper", "live"],
                   help="Override operating mode")
    p.add_argument("--start",         help="Override backtest start date (YYYY-MM-DD)")
    p.add_argument("--end",           help="Override backtest end date (YYYY-MM-DD)")
    p.add_argument("--generate-data", action="store_true",
                   help="Generate synthetic OHLC data and exit")
    return p.parse_args()


def generate_sample_data(cfg: dict) -> None:
    """Generate realistic synthetic XAU/USD OHLC data for testing."""
    from data.generate_sample_data import generate_and_save
    csv_path = cfg.get("data", {}).get("csv_path", "data/XAUUSD_H1.csv")
    generate_and_save(csv_path)


def run_backtest(cfg: dict) -> None:
    from xau_bot.backtester import Backtester
    from xau_bot.performance_analyzer import PerformanceAnalyzer

    backtester = Backtester(cfg)
    result     = backtester.run()

    analyzer = PerformanceAnalyzer(cfg)
    analyzer.print_report(result.metrics)

    # Save metrics to YAML for later inspection
    output_dir = Path(cfg.get("backtest", {}).get("output_dir", "reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(output_dir / "metrics.json", "w") as f:
        # Monthly PnL and nested dicts need special handling
        serialisable = {}
        for k, v in result.metrics.items():
            if isinstance(v, dict):
                serialisable[k] = v
            else:
                serialisable[k] = v
        json.dump(serialisable, f, indent=2, default=str)
    logging.getLogger(__name__).info("Metrics saved to reports/metrics.json")


def _fetch_ohlc(yf_symbol: str, period: str) -> "pd.DataFrame | None":
    """Download OHLC bars from Yahoo Finance, returning UTC-naive DataFrame."""
    try:
        import yfinance as yf
        import pandas as pd
        ticker = yf.Ticker(yf_symbol)
        raw = ticker.history(period=period, interval="1h", auto_adjust=True)
        if raw is None or raw.empty:
            return None
        raw.columns = [c.lower() for c in raw.columns]
        # Normalise index to UTC-naive timestamps
        if hasattr(raw.index, "tz") and raw.index.tz is not None:
            raw.index = raw.index.tz_convert("UTC").tz_localize(None)
        raw = raw[["open", "high", "low", "close", "volume"]].dropna()
        return raw
    except Exception as exc:
        logging.getLogger(__name__).warning("yfinance fetch failed: %s", exc)
        return None


def _htf_bias_for_df(df: "pd.DataFrame", cfg: dict) -> dict:
    """Resample 1H DataFrame to 4H and return date→Trend bias map."""
    try:
        from xau_bot.market_structure_engine import MarketStructureEngine, Trend
        import pandas as pd
        htf = df[["open", "high", "low", "close"]].resample("4h").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna()
        if len(htf) < 10:
            return {}
        htf["atr_proxy"] = (htf["high"] - htf["low"]).rolling(14, min_periods=1).mean()
        engine = MarketStructureEngine(cfg)
        bias_map: dict = {}
        for j in range(len(htf)):
            engine.update(htf, j)
            bias_map[str(htf.index[j])[:10]] = engine.get_trend()
        return bias_map
    except Exception as exc:
        logging.getLogger(__name__).warning("HTF bias computation failed: %s", exc)
        return {}


def run_paper(cfg: dict) -> None:
    """
    Paper trading daemon — fetches live XAUUSD bars every hour, runs the full
    strategy pipeline (market structure → strategy → risk → execution), and
    writes account_snapshot.json + open_trades.json for the API to serve.
    """
    import json
    import signal
    import time
    from datetime import datetime, timezone

    import pandas as pd

    from xau_bot.data_handler import DataHandler
    from xau_bot.market_structure_engine import MarketStructureEngine, Trend
    from xau_bot.strategy_engine import StrategyEngine, TradeDirection, TradeState
    from xau_bot.risk_manager import RiskManager
    from xau_bot.execution_engine import ExecutionEngine

    logger = logging.getLogger(__name__)
    logger.info("Paper trading daemon starting")

    # ── Paths ────────────────────────────────────────────────────────────────
    data_dir    = Path(cfg.get("data", {}).get("csv_path", "data/XAUUSD_H1.csv")).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    snap_path   = data_dir / "account_snapshot.json"
    trades_path = data_dir / "open_trades.json"

    # ── Signal handling ──────────────────────────────────────────────────────
    _alive = [True]

    def _on_signal(sig, _frame):
        logger.info("Paper daemon received signal %d — shutting down", sig)
        _alive[0] = False

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    # ── Engines ──────────────────────────────────────────────────────────────
    dh        = DataHandler(cfg)
    ms_engine = MarketStructureEngine(cfg)
    strategy  = StrategyEngine(cfg, ms_engine)
    risk      = RiskManager(cfg)
    execution = ExecutionEngine(cfg)

    # Restore equity from last snapshot
    initial_capital = float(cfg.get("risk", {}).get("initial_capital", 10000.0))
    try:
        prev = json.loads(snap_path.read_text())
        risk.update_equity(float(prev.get("equity", initial_capital)))
        logger.info("Restored equity: $%.2f", risk.equity)
    except Exception:
        logger.info("Starting fresh with $%.2f", initial_capital)

    yf_symbol = "GC=F"   # Gold Futures — closest proxy for XAUUSD on Yahoo Finance

    # ── Status writer ────────────────────────────────────────────────────────
    open_trades: list = []    # list[ActiveTrade]
    last_price: list  = [0.0]

    def _write_status() -> None:
        try:
            eq = risk.equity
            trade_dicts = []
            for t in open_trades:
                cur = last_price[0]
                sign = 1.0 if t.direction == TradeDirection.LONG else -1.0
                unreal = sign * (cur - t.entry_price) * t.lot_size * 100 if cur else 0.0
                trade_dicts.append({
                    "ticket":        t.trade_id,
                    "symbol":        "XAUUSD",
                    "direction":     t.direction.value.upper(),
                    "lots":          t.lot_size,
                    "open_price":    t.entry_price,
                    "current_price": round(cur, 3) if cur else None,
                    "stop_loss":     t.sl_price,
                    "take_profit":   t.tp2_price,
                    "open_time":     str(t.setup.timestamp),
                    "close_time":    None,
                    "close_price":   None,
                    "pnl":           round(unreal, 2),
                    "commission":    0.0,
                    "swap":          0.0,
                    "session":       t.setup.session,
                    "status":        "open",
                    "rr":            round(t.setup.quality_score, 2),
                    "trigger_type":  str(t.setup.trigger_shift_event.value) if t.setup.trigger_shift_event else None,
                    "zone_quality":  round(t.setup.quality_score, 2),
                })
            trades_path.write_text(json.dumps(trade_dicts))
            snap = {
                "account_number": "PAPER-001",
                "broker":         "Paper Trading (GC=F)",
                "server":         "Yahoo Finance",
                "currency":       "USD",
                "leverage":       100,
                "balance":        round(eq, 2),
                "equity":         round(eq, 2),
                "margin":         0.0,
                "free_margin":    round(eq, 2),
                "margin_level":   None,
                "connected":      True,
                "latency_ms":     0,
                "timestamp":      datetime.now(timezone.utc).isoformat(),
            }
            snap_path.write_text(json.dumps(snap))
        except Exception as exc:
            logger.warning("Status write failed (non-fatal): %s", exc)

    # ── Download warmup data ─────────────────────────────────────────────────
    logger.info("Downloading 90 days of hourly bars from Yahoo Finance (%s)…", yf_symbol)
    raw_df = _fetch_ohlc(yf_symbol, "90d")
    if raw_df is None or raw_df.empty:
        logger.error("Failed to download warmup data — check network or yfinance install")
        _write_status()
        # Keep process alive so the API shows 'Running' even without data
        while _alive[0]:
            time.sleep(10)
            _write_status()
        return

    # Remove the last (still-forming) bar
    raw_df = raw_df.iloc[:-1].copy()

    try:
        df = dh.enrich(raw_df)
    except Exception as exc:
        logger.error("Data enrichment failed: %s", exc)
        return

    logger.info("Warming up market structure engine on %d bars…", len(df))
    htf_bias = _htf_bias_for_df(df, cfg)

    for i in range(len(df)):
        ts_key = str(df.index[i])[:10]
        strategy.set_htf_bias(htf_bias.get(ts_key, Trend.UNKNOWN))
        ms_engine.update(df, i)

    last_bar_time = df.index[-1]
    last_price[0] = float(df["close"].values[-1])
    logger.info("Warmup complete. Last bar: %s  price: %.2f", last_bar_time, last_price[0])

    _write_status()

    # ── Main loop — check for new bars every 60 s ────────────────────────────
    tick = 0
    while _alive[0]:
        time.sleep(30)
        tick += 1
        _write_status()

        # Heartbeat every 10 minutes
        if tick % 20 == 0:
            logger.info(
                "Heartbeat — equity $%.2f | open trades: %d | last bar: %s",
                risk.equity, len(open_trades), last_bar_time,
            )

        # Poll for new bars every ~2 minutes
        if tick % 4 != 0:
            continue

        try:
            fresh = _fetch_ohlc(yf_symbol, "5d")
            if fresh is None or fresh.empty:
                continue

            # Drop the last (still-forming) bar
            fresh = fresh.iloc[:-1]

            new_bars = fresh[fresh.index > last_bar_time]
            if new_bars.empty:
                continue

            logger.info("%d new bar(s) to process", len(new_bars))

            for bar_ts in new_bars.index:
                bar_row = new_bars.loc[bar_ts]

                # Append raw bar to DataFrame and re-enrich
                new_row = pd.DataFrame(
                    [[bar_row["open"], bar_row["high"], bar_row["low"],
                      bar_row["close"], bar_row.get("volume", 0.0)]],
                    index=[bar_ts],
                    columns=["open", "high", "low", "close", "volume"],
                )
                raw_df = pd.concat([raw_df, new_row])
                df = dh.enrich(raw_df)

                i = len(df) - 1
                last_price[0] = float(df["close"].values[-1])

                # Update HTF bias daily
                ts_key = str(bar_ts)[:10]
                if ts_key not in htf_bias:
                    htf_bias = _htf_bias_for_df(df, cfg)
                strategy.set_htf_bias(htf_bias.get(ts_key, Trend.UNKNOWN))

                candle = dh.get_candle(df, i)
                state  = ms_engine.update(df, i)

                # ── Manage open positions ─────────────────────────────────────
                still_open = []
                for trade in open_trades:
                    trade = strategy.manage_open_trade(trade, candle, df)

                    if trade.state == TradeState.CLOSED:
                        pnl = execution.close_trade(
                            trade, trade.close_price, i, trade.close_reason)
                        risk.register_trade_close(pnl)
                        logger.info("Trade #%d CLOSED [%s] pnl=$%.2f",
                                    trade.trade_id, trade.close_reason, pnl)

                    elif trade.state == TradeState.PARTIAL and not getattr(trade, "_tp1_booked", False):
                        pnl = execution.close_trade(
                            trade, trade.tp1_price, i, "tp1_partial", partial=True)
                        risk.register_trade_close(pnl)
                        trade._tp1_booked = True
                        still_open.append(trade)
                        logger.info("Trade #%d TP1 partial close pnl=$%.2f", trade.trade_id, pnl)

                    else:
                        still_open.append(trade)

                open_trades[:] = still_open

                # ── Evaluate new setup ────────────────────────────────────────
                if not risk.is_trading_allowed:
                    logger.info("Trading halted by risk manager at bar %d", i)
                    continue

                open_dirs = [t.direction for t in open_trades]
                setup = strategy.evaluate(candle, state, df, open_dirs)

                if setup is not None:
                    atr = float(df["atr_proxy"].values[i]) if "atr_proxy" in df.columns else candle.range_size
                    bar_data = {
                        "open": candle.open, "high": candle.high,
                        "low":  candle.low,  "close": candle.close,
                        "atr_proxy": atr,
                    }
                    risk_report = risk.evaluate_trade(
                        entry_price=setup.entry_price,
                        sl_price=setup.raw_sl_price,
                        direction=setup.direction.value,
                        atr_proxy=atr,
                        current_time=candle.timestamp if hasattr(candle.timestamp, "date") else None,
                        open_trades=len(open_trades),
                    )
                    if risk_report.allowed:
                        trade = execution.submit_order(setup, risk_report, i, bar_data)
                        if trade:
                            risk.register_trade_open(risk_report.lot_size)
                            open_trades.append(trade)
                            logger.info("Trade #%d OPENED %s @ %.2f  SL=%.2f  TP1=%.2f  TP2=%.2f",
                                        trade.trade_id, trade.direction.value,
                                        trade.entry_price, trade.sl_price,
                                        trade.tp1_price, trade.tp2_price)
                    else:
                        logger.debug("Trade blocked by risk: %s", risk_report.reason)

                last_bar_time = bar_ts
                _write_status()

        except Exception as exc:
            logger.error("Error processing bar: %s", exc, exc_info=True)

    _write_status()
    logger.info("Paper trading daemon stopped cleanly")


def run_live(cfg: dict) -> None:
    """
    Live trading daemon.

    Uses the broker adapter configured under cfg['broker']['type']:
      - 'paper'    → pure simulation (same as run_paper)
      - 'metaapi'  → real MT5/MT4 orders via MetaApi cloud
      - 'oanda'    → real orders via OANDA v20 REST API

    Price feed stays Yahoo Finance (1H GC=F) for strategy decisions;
    the broker adapter is used only for account queries and order placement.
    """
    logger = logging.getLogger(__name__)
    broker_type = cfg.get("broker", {}).get("type", "paper")

    if broker_type == "paper":
        logger.info("Live mode: broker=paper — running as paper simulation")
        run_paper(cfg)
        return

    # Build broker adapter
    try:
        from xau_bot.broker import build_broker
        broker = build_broker(cfg)
        ok, msg = broker.test_connection()
        if not ok:
            logger.error("Broker connection failed: %s — falling back to paper mode", msg)
            run_paper(cfg)
            return
        logger.info("Broker connected: %s", msg)
    except Exception as exc:
        logger.error("Failed to build broker adapter: %s — falling back to paper", exc)
        run_paper(cfg)
        return

    # Run the standard paper loop but with the real broker for account info
    # and order submission.  The execution_engine submit_order is called
    # normally; after it returns we forward the order to the live broker.
    import json
    import signal
    import time
    from datetime import datetime, timezone
    from pathlib import Path

    import pandas as pd

    from xau_bot.data_handler import DataHandler
    from xau_bot.market_structure_engine import MarketStructureEngine, Trend
    from xau_bot.strategy_engine import StrategyEngine, TradeDirection, TradeState
    from xau_bot.risk_manager import RiskManager
    from xau_bot.execution_engine import ExecutionEngine

    data_dir    = Path(cfg.get("data", {}).get("csv_path", "data/XAUUSD_H1.csv")).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    snap_path   = data_dir / "account_snapshot.json"
    trades_path = data_dir / "open_trades.json"

    _alive = [True]

    def _on_signal(sig, _frame):
        logger.info("Live daemon received signal %d — shutting down", sig)
        _alive[0] = False

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    dh        = DataHandler(cfg)
    ms_engine = MarketStructureEngine(cfg)
    strategy  = StrategyEngine(cfg, ms_engine)
    risk      = RiskManager(cfg)
    execution = ExecutionEngine(cfg)

    # Sync equity from broker
    try:
        acct_info = broker.get_account_info()
        risk.update_equity(float(acct_info.get("equity", cfg["risk"]["initial_capital"])))
        logger.info("Broker equity synced: $%.2f", risk.equity)
    except Exception as exc:
        logger.warning("Could not sync equity from broker: %s", exc)

    yf_symbol = "GC=F"
    open_trades: list = []
    last_price: list  = [0.0]
    broker_orders: dict = {}  # trade_id → broker order_id

    def _write_status():
        try:
            # Refresh account info from broker
            try:
                live_info = broker.get_account_info()
                live_info["timestamp"] = datetime.now(timezone.utc).isoformat()
                snap_path.write_text(json.dumps(live_info))
            except Exception:
                pass

            # Sync positions from broker
            try:
                live_positions = broker.get_positions()
                trades_path.write_text(json.dumps(live_positions))
            except Exception:
                pass
        except Exception as exc:
            logger.warning("Status write failed: %s", exc)

    logger.info("Downloading warmup data…")
    raw_df = _fetch_ohlc(yf_symbol, "90d")
    if raw_df is None or raw_df.empty:
        logger.error("Failed to download warmup data")
        while _alive[0]:
            time.sleep(30)
            _write_status()
        return

    raw_df = raw_df.iloc[:-1].copy()
    try:
        df = dh.enrich(raw_df)
    except Exception as exc:
        logger.error("Data enrichment failed during warmup: %s", exc, exc_info=True)
        while _alive[0]:
            time.sleep(30)
            _write_status()
        return

    htf_bias = _htf_bias_for_df(df, cfg)

    try:
        for i in range(len(df)):
            ts_key = str(df.index[i])[:10]
            strategy.set_htf_bias(htf_bias.get(ts_key, Trend.UNKNOWN))
            ms_engine.update(df, i)
    except Exception as exc:
        logger.error("Warmup market-structure failed at bar %d: %s", i, exc, exc_info=True)

    last_bar_time  = df.index[-1]
    last_price[0]  = float(df["close"].values[-1])
    logger.info("Warmup complete. Last bar: %s  price: %.2f", last_bar_time, last_price[0])
    _write_status()

    tick = 0
    while _alive[0]:
        time.sleep(30)
        tick += 1
        _write_status()

        # Heartbeat every 10 minutes
        if tick % 20 == 0:
            try:
                acct = broker.get_account_info()
                logger.info(
                    "Heartbeat — equity $%.2f | open trades: %d | last bar: %s",
                    acct.get("equity", 0), len(open_trades), last_bar_time,
                )
            except Exception as exc:
                logger.info(
                    "Heartbeat — open trades: %d | last bar: %s | broker: %s",
                    len(open_trades), last_bar_time, exc,
                )

        if tick % 4 != 0:
            continue

        try:
            fresh = _fetch_ohlc(yf_symbol, "5d")
            if fresh is None or fresh.empty:
                continue

            fresh    = fresh.iloc[:-1]
            new_bars = fresh[fresh.index > last_bar_time]
            if new_bars.empty:
                continue

            logger.info("%d new bar(s) to process", len(new_bars))
            for bar_ts in new_bars.index:
                bar_row = new_bars.loc[bar_ts]
                new_row = pd.DataFrame(
                    [[bar_row["open"], bar_row["high"], bar_row["low"],
                      bar_row["close"], bar_row.get("volume", 0.0)]],
                    index=[bar_ts],
                    columns=["open", "high", "low", "close", "volume"],
                )
                raw_df = pd.concat([raw_df, new_row])
                df     = dh.enrich(raw_df)
                i      = len(df) - 1
                last_price[0] = float(df["close"].values[-1])

                ts_key = str(bar_ts)[:10]
                if ts_key not in htf_bias:
                    htf_bias = _htf_bias_for_df(df, cfg)
                strategy.set_htf_bias(htf_bias.get(ts_key, Trend.UNKNOWN))

                candle = dh.get_candle(df, i)
                state  = ms_engine.update(df, i)

                still_open = []
                for trade in open_trades:
                    trade = strategy.manage_open_trade(trade, candle, df)
                    if trade.state == TradeState.CLOSED:
                        pnl = execution.close_trade(trade, trade.close_price, i, trade.close_reason)
                        risk.register_trade_close(pnl)
                        # Close on broker
                        oid = broker_orders.get(trade.trade_id)
                        if oid:
                            try:
                                broker.close_position(oid)
                                logger.info("Broker position %s closed", oid)
                            except Exception as exc:
                                logger.error("Failed to close broker position %s: %s", oid, exc)
                    elif trade.state == TradeState.PARTIAL and not getattr(trade, "_tp1_booked", False):
                        pnl = execution.close_trade(trade, trade.tp1_price, i, "tp1_partial", partial=True)
                        risk.register_trade_close(pnl)
                        trade._tp1_booked = True
                        still_open.append(trade)
                    else:
                        still_open.append(trade)
                open_trades[:] = still_open

                if not risk.is_trading_allowed:
                    continue

                open_dirs = [t.direction for t in open_trades]
                setup     = strategy.evaluate(candle, state, df, open_dirs)

                if setup is not None:
                    atr = float(df["atr_proxy"].values[i]) if "atr_proxy" in df.columns else candle.range_size
                    bar_data = {"open": candle.open, "high": candle.high,
                                "low": candle.low, "close": candle.close, "atr_proxy": atr}
                    risk_report = risk.evaluate_trade(
                        entry_price=setup.entry_price, sl_price=setup.raw_sl_price,
                        direction=setup.direction.value, atr_proxy=atr,
                        current_time=candle.timestamp if hasattr(candle.timestamp, "date") else None,
                        open_trades=len(open_trades),
                    )
                    if risk_report.allowed:
                        trade = execution.submit_order(setup, risk_report, i, bar_data)
                        if trade:
                            risk.register_trade_open(risk_report.lot_size)
                            # Submit to live broker
                            symbol = cfg.get("bot", {}).get("symbol", "XAUUSD")
                            try:
                                order_result = broker.place_order(
                                    symbol    = symbol,
                                    direction = trade.direction.value.upper(),
                                    lots      = trade.lot_size,
                                    entry     = trade.entry_price,
                                    sl        = trade.sl_price,
                                    tp        = trade.tp2_price,
                                    order_type = cfg.get("strategy", {}).get("entry_type", "LIMIT").upper(),
                                )
                                broker_orders[trade.trade_id] = order_result.get("order_id", "")
                                logger.info("Broker order placed: %s", order_result)
                            except Exception as exc:
                                logger.error("Failed to place broker order: %s", exc)
                            open_trades.append(trade)

                last_bar_time = bar_ts
                _write_status()

        except Exception as exc:
            logger.error("Error processing bar: %s", exc, exc_info=True)

    _write_status()
    logger.info("Live trading daemon stopped")


def main() -> None:
    args = parse_args()
    cfg  = load_config(args.config)

    # ── Apply CLI overrides ──────────────────────────────────────────────────
    if args.mode:
        cfg["bot"]["mode"] = args.mode
    if args.start:
        cfg["backtest"]["start_date"] = args.start
    if args.end:
        cfg["backtest"]["end_date"] = args.end

    setup_logging(cfg)
    logger = logging.getLogger(__name__)
    logger.info("XAU/USD Price Action Bot v%s", cfg["bot"].get("version", "1.0.0"))
    logger.info("Mode: %s", cfg["bot"].get("mode"))

    # ── Generate sample data if requested ───────────────────────────────────
    if args.generate_data:
        generate_sample_data(cfg)
        return

    mode = cfg["bot"].get("mode", "backtest")

    if mode == "backtest":
        run_backtest(cfg)
    elif mode == "paper":
        run_paper(cfg)
    elif mode == "live":
        run_live(cfg)
    else:
        logger.error("Unknown mode: %s", mode)
        sys.exit(1)


if __name__ == "__main__":
    main()
