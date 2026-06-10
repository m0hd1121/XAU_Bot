"""
broker.py — Broker connectivity abstraction.

Supported adapters:
  - PaperBroker     : pure simulation, reads local JSON files
  - DWXBroker       : DWX Connect file-bridge to MT4/MT5 running under Wine
  - MetaApiBroker   : MetaApi cloud MT5/MT4 bridge (works from Linux VPS)
  - OANDABroker     : OANDA v20 REST API (practice or live)

Use build_broker(cfg) to get the configured adapter.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base
# ─────────────────────────────────────────────────────────────────────────────

class BrokerBase(ABC):

    @abstractmethod
    def get_account_info(self) -> dict: ...

    @abstractmethod
    def get_positions(self) -> list[dict]: ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        direction: str,        # "BUY" | "SELL"
        lots: float,
        entry: float,
        sl: float,
        tp: float,
        order_type: str = "LIMIT",
    ) -> dict: ...

    @abstractmethod
    def close_position(self, position_id: str, lots: Optional[float] = None) -> dict: ...

    def test_connection(self) -> tuple[bool, str]:
        """Quick connection test. Returns (ok, message)."""
        try:
            info = self.get_account_info()
            broker = info.get("broker", "Broker")
            bal    = info.get("balance", 0)
            return True, f"{broker} — balance ${bal:,.2f}"
        except Exception as exc:
            return False, str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# Paper Broker (local simulation)
# ─────────────────────────────────────────────────────────────────────────────

class PaperBroker(BrokerBase):

    def __init__(self, snap_path: Path, trades_path: Path) -> None:
        self._snap   = snap_path
        self._trades = trades_path

    def get_account_info(self) -> dict:
        try:
            data = json.loads(self._snap.read_text())
            data.setdefault("broker", "Paper Trading")
            data.setdefault("connected", True)
            return data
        except Exception:
            return {"balance": 0, "equity": 0, "connected": True, "broker": "Paper Trading"}

    def get_positions(self) -> list[dict]:
        try:
            return json.loads(self._trades.read_text())
        except Exception:
            return []

    def place_order(self, symbol, direction, lots, entry, sl, tp, order_type="LIMIT") -> dict:
        return {"order_id": "PAPER", "ok": True}

    def close_position(self, position_id, lots=None) -> dict:
        return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# DWX Connect Broker (file-based IPC bridge to MT4/MT5 under Wine)
# ─────────────────────────────────────────────────────────────────────────────

class DWXBroker(BrokerBase):
    """
    Communicates with MT4/MT5 running under Wine via the DWX Connect file bridge.

    DWX Connect EA writes JSON files to MT4's MQL4/Files directory;
    this class reads and writes those same files.

    mt4_files_path: absolute path to MT4's MQL4/Files directory on the VPS.
    Typical path:  ~/.wine-mt4/drive_c/Program Files (x86)/<broker>/MQL4/Files
    """

    _ORDER_TYPES = {
        "BUY":       0,
        "SELL":      1,
        "BUYLIMIT":  2,
        "SELLLIMIT": 3,
        "BUYSTOP":   4,
        "SELLSTOP":  5,
    }

    def __init__(self, mt4_files_path: str, magic: int = 88888) -> None:
        self._files = Path(mt4_files_path).expanduser()
        self._magic = magic
        self._cmd_id = 0
        # File names written by XAU_Bridge.mq5 EA
        self._ACCOUNTS_FILE  = "XAU_Accounts.json"
        self._POSITIONS_FILE = "XAU_Positions.json"
        self._ORDERS_FILE    = "XAU_Orders.json"

    # ── File paths ────────────────────────────────────────────────────────────

    def _f(self, name: str) -> Path:
        return self._files / name

    # ── Internal: write a command and wait for acknowledgement ────────────────

    def _send_command(self, payload: dict, timeout: float = 10.0) -> dict:
        import time
        self._cmd_id += 1
        payload["_magic"] = self._magic
        cmd_file = self._f(self._ORDERS_FILE)
        cmd_file.write_text(json.dumps(payload, separators=(',', ':')))

        # Wait for EA to consume the file (it deletes or empties it when done)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.1)
            try:
                content = cmd_file.read_text().strip()
                if not content or content == "{}":
                    return {"ok": True}
            except FileNotFoundError:
                return {"ok": True}
        logger.warning("DWX command timed out: %s", payload.get("_action"))
        return {"ok": False, "detail": "timeout"}

    # ── Interface ─────────────────────────────────────────────────────────────

    def get_account_info(self) -> dict:
        acct_file = self._f(self._ACCOUNTS_FILE)
        if not acct_file.exists():
            raise FileNotFoundError(
                f"{self._ACCOUNTS_FILE} not found at {self._files}. "
                "Is MT5 running with XAU_Bridge EA attached to a chart?"
            )
        data = json.loads(acct_file.read_text())
        return {
            "account_number": str(data.get("_login", "")),
            "broker":         data.get("_broker", "MT4 / DWX Connect"),
            "server":         data.get("_server", ""),
            "currency":       data.get("_currency", "USD"),
            "leverage":       data.get("_leverage", 0),
            "balance":        float(data.get("_balance", 0)),
            "equity":         float(data.get("_equity", 0)),
            "margin":         float(data.get("_margin", 0)),
            "free_margin":    float(data.get("_free_margin", 0)),
            "margin_level":   data.get("_margin_level"),
            "connected":      True,
        }

    def get_positions(self) -> list[dict]:
        orders_file = self._f(self._POSITIONS_FILE)
        if not orders_file.exists():
            return []
        try:
            data = json.loads(orders_file.read_text())
        except Exception:
            return []
        result = []
        for ticket, o in data.items():
            result.append({
                "ticket":        str(ticket),
                "symbol":        o.get("_symbol", ""),
                "direction":     "BUY" if o.get("_type", 1) == 0 else "SELL",
                "lots":          float(o.get("_lots", 0)),
                "open_price":    float(o.get("_open_price", 0)),
                "current_price": float(o.get("_close_price", 0)),
                "stop_loss":     o.get("_SL"),
                "take_profit":   o.get("_TP"),
                "pnl":           float(o.get("_pnl", 0)),
                "open_time":     o.get("_open_time", ""),
                "commission":    float(o.get("_commission", 0)),
                "swap":          float(o.get("_swap", 0)),
            })
        return result

    def place_order(self, symbol, direction, lots, entry, sl, tp,
                    order_type="LIMIT") -> dict:
        dir_upper = direction.upper()
        if order_type == "LIMIT":
            dwx_type = self._ORDER_TYPES.get(
                "BUYLIMIT" if dir_upper in ("BUY", "LONG") else "SELLLIMIT", 2
            )
        else:
            dwx_type = self._ORDER_TYPES.get(
                "BUY" if dir_upper in ("BUY", "LONG") else "SELL", 0
            )

        return self._send_command({
            "_action":  "OPEN",
            "_type":    dwx_type,
            "_symbol":  symbol,
            "_price":   round(entry, 3),
            "_SL":      round(sl, 3),
            "_TP":      round(tp, 3),
            "_lots":    round(lots, 2),
            "_comment": "XAU_BOT",
        })

    def close_position(self, position_id: str, lots: Optional[float] = None) -> dict:
        payload: dict = {"_action": "CLOSE", "_ticket": int(position_id)}
        if lots:
            payload["_lots"] = round(lots, 2)
        return self._send_command(payload)

    def test_connection(self) -> tuple[bool, str]:
        if not self._files.exists():
            return False, f"MT4 Files directory not found: {self._files}"
        try:
            info = self.get_account_info()
            return True, (
                f"{info['broker']} — {info['server']} — "
                f"#{info['account_number']} — balance ${info['balance']:,.2f}"
            )
        except FileNotFoundError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# MetaApi Broker (cloud MT5/MT4 bridge — Linux-compatible)
# ─────────────────────────────────────────────────────────────────────────────

class MetaApiBroker(BrokerBase):
    """
    Wraps the metaapi-cloud-sdk async SDK in synchronous calls.

    Setup:
      1. Sign up at https://metaapi.cloud (free tier available)
      2. Add your MT5 demo account
      3. Copy your Token and Account ID into config.yaml
    """

    def __init__(self, token: str, account_id: str) -> None:
        self._token      = token
        self._account_id = account_id

    # ── Async helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _run(coro):
        """Run an async coroutine synchronously, creating a new loop if needed."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=90)
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    async def _get_conn(self):
        from metaapi_cloud_sdk import MetaApi  # type: ignore
        api     = MetaApi(self._token)
        account = await api.metatrader_account_api.get_account(self._account_id)
        if account.state not in ("DEPLOYING", "DEPLOYED"):
            await account.deploy()
        await account.wait_connected(timeout_in_seconds=60)
        conn = account.get_rpc_connection()
        await conn.connect()
        await conn.wait_synchronized(timeout_in_seconds=60)
        return conn

    # ── Interface ─────────────────────────────────────────────────────────────

    def get_account_info(self) -> dict:
        async def _inner():
            conn = await self._get_conn()
            info = await conn.get_account_information()
            return {
                "account_number": str(info.get("login", "")),
                "broker":         info.get("broker", "MetaTrader"),
                "server":         info.get("server", ""),
                "currency":       info.get("currency", "USD"),
                "leverage":       info.get("leverage", 0),
                "balance":        float(info.get("balance", 0)),
                "equity":         float(info.get("equity", 0)),
                "margin":         float(info.get("margin", 0)),
                "free_margin":    float(info.get("freeMargin", 0)),
                "margin_level":   info.get("marginLevel"),
                "connected":      True,
            }
        return self._run(_inner())

    def get_positions(self) -> list[dict]:
        async def _inner():
            conn = await self._get_conn()
            positions = await conn.get_positions()
            result = []
            for p in positions:
                units = float(p.get("volume", 0))
                result.append({
                    "ticket":        str(p.get("id", "")),
                    "symbol":        p.get("symbol", ""),
                    "direction":     "BUY" if p.get("type") == "POSITION_TYPE_BUY" else "SELL",
                    "lots":          units,
                    "open_price":    float(p.get("openPrice", 0)),
                    "current_price": float(p.get("currentPrice", 0)),
                    "stop_loss":     p.get("stopLoss"),
                    "take_profit":   p.get("takeProfit"),
                    "pnl":           float(p.get("profit", 0)),
                    "open_time":     str(p.get("time", "")),
                    "commission":    float(p.get("commission", 0)),
                    "swap":          float(p.get("swap", 0)),
                })
            return result
        return self._run(_inner())

    def place_order(self, symbol, direction, lots, entry, sl, tp, order_type="LIMIT") -> dict:
        async def _inner():
            conn = await self._get_conn()
            is_buy = direction.upper() in ("BUY", "LONG")
            if order_type == "LIMIT":
                if is_buy:
                    result = await conn.create_limit_buy_order(symbol, lots, entry, sl, tp)
                else:
                    result = await conn.create_limit_sell_order(symbol, lots, entry, sl, tp)
            else:
                if is_buy:
                    result = await conn.create_market_buy_order(symbol, lots, sl, tp)
                else:
                    result = await conn.create_market_sell_order(symbol, lots, sl, tp)
            return {"order_id": result.get("orderId", ""), "ok": True}
        return self._run(_inner())

    def close_position(self, position_id, lots=None) -> dict:
        async def _inner():
            conn = await self._get_conn()
            if lots:
                result = await conn.close_position_partially(position_id, lots)
            else:
                result = await conn.close_position(position_id)
            return {"ok": True, "result": str(result)}
        return self._run(_inner())


# ─────────────────────────────────────────────────────────────────────────────
# OANDA Broker (REST v20)
# ─────────────────────────────────────────────────────────────────────────────

class OANDABroker(BrokerBase):
    """OANDA v20 REST API. Supports XAU_USD (Gold)."""

    _PRACTICE_URL = "https://api-fxpractice.oanda.com/v3"
    _LIVE_URL     = "https://api-fxtrade.oanda.com/v3"

    def __init__(self, api_key: str, account_id: str, environment: str = "practice") -> None:
        import requests
        self._session    = requests.Session()
        self._account_id = account_id
        self._base       = self._LIVE_URL if environment == "live" else self._PRACTICE_URL
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self._base}/accounts/{self._account_id}{path}"

    def get_account_info(self) -> dict:
        r = self._session.get(self._url("/summary"), timeout=15)
        r.raise_for_status()
        acct = r.json()["account"]
        return {
            "account_number": acct.get("id", ""),
            "broker":         "OANDA",
            "server":         "OANDA v20 REST",
            "currency":       acct.get("currency", "USD"),
            "leverage":       acct.get("marginRate", 0),
            "balance":        float(acct.get("balance", 0)),
            "equity":         float(acct.get("NAV", 0)),
            "margin":         float(acct.get("marginUsed", 0)),
            "free_margin":    float(acct.get("marginAvailable", 0)),
            "margin_level":   None,
            "connected":      True,
        }

    def get_positions(self) -> list[dict]:
        r = self._session.get(self._url("/openTrades"), timeout=15)
        r.raise_for_status()
        result = []
        for t in r.json().get("trades", []):
            units = float(t.get("currentUnits", 0))
            result.append({
                "ticket":        t.get("id", ""),
                "symbol":        t.get("instrument", "").replace("_", ""),
                "direction":     "BUY" if units > 0 else "SELL",
                "lots":          abs(units) / 100,
                "open_price":    float(t.get("price", 0)),
                "current_price": None,
                "stop_loss":     float((t.get("stopLossOrder") or {}).get("price", 0)) or None,
                "take_profit":   float((t.get("takeProfitOrder") or {}).get("price", 0)) or None,
                "pnl":           float(t.get("unrealizedPL", 0)),
                "open_time":     t.get("openTime", ""),
                "commission":    float(t.get("financing", 0)),
                "swap":          0.0,
            })
        return result

    def place_order(self, symbol, direction, lots, entry, sl, tp, order_type="LIMIT") -> dict:
        oanda_sym = symbol[:3] + "_" + symbol[3:] if "_" not in symbol else symbol
        units = int(lots * 100) * (1 if direction.upper() in ("BUY", "LONG") else -1)
        body: dict = {
            "order": {
                "type":       "LIMIT" if order_type == "LIMIT" else "MARKET",
                "instrument": oanda_sym,
                "units":      str(units),
                "stopLossOnFill":   {"price": str(round(sl, 3))},
                "takeProfitOnFill": {"price": str(round(tp, 3))},
            }
        }
        if order_type == "LIMIT":
            body["order"]["price"] = str(round(entry, 3))
        r = self._session.post(self._url("/orders"), json=body, timeout=15)
        r.raise_for_status()
        oid = r.json().get("orderCreateTransaction", {}).get("id", "")
        return {"order_id": oid, "ok": True}

    def close_position(self, position_id, lots=None) -> dict:
        url = self._url(f"/trades/{position_id}/close")
        if lots:
            r = self._session.put(url, json={"units": str(int(lots * 100))}, timeout=15)
        else:
            r = self._session.put(url, timeout=15)
        r.raise_for_status()
        return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def build_broker(cfg: dict) -> BrokerBase:
    """Build the correct broker adapter from config."""
    broker_cfg = cfg.get("broker", {})
    btype      = broker_cfg.get("type", "paper").lower()

    if btype == "dwx":
        dwx = broker_cfg.get("dwx", {})
        files_path = dwx.get("mt4_files_path", "")
        if not files_path:
            raise ValueError("broker.dwx.mt4_files_path is required")
        return DWXBroker(files_path, magic=int(dwx.get("magic", 88888)))

    elif btype == "metaapi":
        ma = broker_cfg.get("metaapi", {})
        token      = ma.get("token", "")
        account_id = ma.get("account_id", "")
        if not token or not account_id:
            raise ValueError("broker.metaapi.token and broker.metaapi.account_id are required")
        return MetaApiBroker(token, account_id)

    elif btype == "oanda":
        oa = broker_cfg.get("oanda", {})
        return OANDABroker(
            api_key     = oa.get("api_key", ""),
            account_id  = oa.get("account_id", ""),
            environment = oa.get("environment", "practice"),
        )

    else:
        data_dir    = Path(cfg.get("data", {}).get("csv_path", "data/XAUUSD_H1.csv")).parent
        return PaperBroker(data_dir / "account_snapshot.json",
                           data_dir / "open_trades.json")
