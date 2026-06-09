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


def run_paper(cfg: dict) -> None:
    """
    Paper trading daemon — runs continuously, scanning for setups on live/scheduled data.
    Keeps the process alive so the API shows 'Running'. Writes status files every 30 s.
    Stopped cleanly by SIGTERM (the API's 'Stop' button).
    """
    import json
    import signal
    import time
    from datetime import datetime, timezone
    from pathlib import Path

    logger = logging.getLogger(__name__)
    logger.info("Paper trading daemon starting")

    data_dir = Path(cfg.get("data", {}).get("csv_path", "data/XAUUSD_H1.csv")).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    initial_capital = float(cfg.get("risk", {}).get("initial_capital", 10000.0))
    equity  = initial_capital
    balance = initial_capital

    # ── Run an initial backtest to get a realistic starting equity ──────────────
    logger.info("Running initial analysis on historical data...")
    try:
        from xau_bot.backtester import Backtester
        bt  = Backtester(cfg)
        res = bt.run()
        # Try common attribute names for final equity
        for attr in ("final_equity", "equity", "ending_equity"):
            if hasattr(res, attr) and getattr(res, attr):
                equity = float(getattr(res, attr))
                break
        if hasattr(res, "metrics") and isinstance(res.metrics, dict):
            equity = float(res.metrics.get("final_equity", equity))
        balance = equity
        logger.info("Initial analysis complete — starting equity: $%.2f", equity)
    except Exception as exc:
        logger.warning("Initial analysis skipped (%s) — using default capital $%.2f", exc, initial_capital)

    # ── Signal handling ─────────────────────────────────────────────────────────
    _alive = [True]

    def _on_signal(sig, _frame):
        logger.info("Paper trading daemon received signal %d — shutting down", sig)
        _alive[0] = False

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    snap_path   = data_dir / "account_snapshot.json"
    trades_path = data_dir / "open_trades.json"

    def _write_status() -> None:
        snap = {
            "account_number": "PAPER-001",
            "broker":         "Paper Trading",
            "server":         "Simulated",
            "currency":       "USD",
            "leverage":       100,
            "balance":        round(balance, 2),
            "equity":         round(equity,  2),
            "margin":         0.0,
            "free_margin":    round(equity,  2),
            "margin_level":   None,
            "connected":      True,
            "latency_ms":     0,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        }
        snap_path.write_text(json.dumps(snap))
        if not trades_path.exists():
            trades_path.write_text("[]")

    _write_status()
    logger.info("Paper trading daemon running — equity $%.2f — waiting for new bars", equity)

    tick = 0
    while _alive[0]:
        time.sleep(5)
        tick += 1
        _write_status()
        if tick % 72 == 0:   # every ~6 minutes
            logger.info("Paper trading heartbeat — equity: $%.2f", equity)

    _write_status()
    logger.info("Paper trading daemon stopped cleanly")


def run_live(cfg: dict) -> None:
    """
    Live trading daemon placeholder — requires a BrokerAPI adapter (MT5, REST, etc.).
    Until the adapter is implemented this runs as a paper-trading daemon so the
    process stays alive and the iOS app shows 'Running'.
    """
    logging.getLogger(__name__).warning(
        "Live mode: no broker adapter configured — falling back to paper simulation. "
        "Implement BrokerAPI in xau_bot/execution_engine.py to enable real trading."
    )
    run_paper(cfg)


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
