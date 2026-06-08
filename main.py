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
    logging.getLogger(__name__).warning(
        "Paper trading mode: connect a live data feed and broker adapter."
    )
    print("Paper trading mode requires a live data feed integration.")
    print("See xau_bot/execution_engine.py BrokerAPI protocol for the adapter interface.")


def run_live(cfg: dict) -> None:
    logging.getLogger(__name__).warning("Live trading mode: broker integration required.")
    print("Live mode requires a BrokerAPI adapter (MetaTrader 5, REST, etc.).")
    print("Implement the BrokerAPI protocol in xau_bot/execution_engine.py.")


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
