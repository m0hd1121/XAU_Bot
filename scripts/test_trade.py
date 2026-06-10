#!/usr/bin/env python3
"""
test_trade.py — Place a minimal test trade and close it immediately.

Usage (from bot directory):
  python scripts/test_trade.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from xau_bot.broker import build_broker


def main():
    cfg = yaml.safe_load(open("config.yaml"))

    print("─" * 50)
    print("XAU Bot — Test Trade")
    print("─" * 50)

    # Build broker
    print("\n[1] Connecting to broker...")
    broker = build_broker(cfg)
    ok, msg = broker.test_connection()
    if not ok:
        print(f"    FAILED: {msg}")
        sys.exit(1)
    print(f"    OK — {msg}")

    info = broker.get_account_info()
    print(f"    Balance: ${info['balance']:.2f}  Equity: ${info['equity']:.2f}")

    symbol = cfg.get("bot", {}).get("symbol", "XAUUSD")
    print(f"    Symbol: {symbol}")

    # Snapshot positions before
    before = {p["ticket"] for p in broker.get_positions()}
    print(f"\n[2] Open positions before test: {len(before)}")

    # Place 0.01-lot market BUY (smallest possible, no SL/TP)
    print(f"\n[3] Placing 0.01-lot MARKET BUY on {symbol}...")
    result = broker.place_order(
        symbol=symbol,
        direction="BUY",
        lots=0.01,
        entry=0,
        sl=0,
        tp=0,
        order_type="MARKET",
    )
    print(f"    Result: {result}")

    if not result.get("ok"):
        print("    Order FAILED — check that MT5 is running with XAU_Bridge EA attached")
        sys.exit(1)

    # Wait for EA to update positions file
    print("\n[4] Waiting for position to appear (up to 10s)...")
    new_pos = None
    for _ in range(20):
        time.sleep(0.5)
        after = broker.get_positions()
        new = [p for p in after if p["ticket"] not in before]
        if new:
            new_pos = new[0]
            break

    if new_pos is None:
        print("    Position not found after 10s — order may have been rejected by broker")
        print("    Check MT5 journal in VNC for details")
        sys.exit(1)

    print(f"    Position opened!")
    print(f"    Ticket: #{new_pos['ticket']}")
    print(f"    Direction: {new_pos['direction']}")
    print(f"    Lots: {new_pos['lots']}")
    print(f"    Open price: {new_pos['open_price']}")
    print(f"    P&L: ${new_pos['pnl']:.2f}")

    # Close it immediately
    print(f"\n[5] Closing position #{new_pos['ticket']}...")
    close = broker.close_position(new_pos["ticket"])
    print(f"    Result: {close}")

    if close.get("ok"):
        print("\n✓ TEST TRADE SUCCESSFUL — broker connection is working perfectly!")
    else:
        print("\n✗ Close failed — position may still be open, close manually in MT5")

    print("─" * 50)


if __name__ == "__main__":
    main()
