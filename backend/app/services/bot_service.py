"""
services/bot_service.py
────────────────────────
Interfaces with the XAU/USD trading bot process and its data stores.

Responsibilities:
  • Process lifecycle management (start / stop / restart / pause / resume)
    via PID file + signals + subprocess.  Falls back to systemd if available.
  • State flag files (.paused, .maintenance, .emergency_stop) in bot root
  • Reads config.yaml and writes back validated updates
  • Reads trade history and open trades from learning.db and JSON state files
  • Reads learning engine statistics from learning.db
  • Computes PnL, win rate, and equity curve from raw trade records
  • Builds the dashboard snapshot payload consumed by the dashboard router
    and the WebSocket background worker
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import psutil
import yaml

from app.config import settings

logger = logging.getLogger(__name__)

# ── Resolved paths ────────────────────────────────────────────────────────────

BOT_ROOT    = settings.bot_root
CONFIG_PATH = settings.bot_config_path
LEARNING_DB = settings.bot_learning_db
PID_FILE    = settings.bot_pid_file
BOT_LOG     = settings.bot_log_file
BOT_PYTHON  = settings.bot_venv_python
BOT_SCRIPT  = settings.bot_main_script

# Runtime state flag files (the bot polls these)
_FLAG_PAUSED    = BOT_ROOT / ".paused"
_FLAG_MAINT     = BOT_ROOT / ".maintenance"
_FLAG_EMERGENCY = BOT_ROOT / ".emergency_stop"

# Live data files written by the bot every heartbeat
_OPEN_TRADES_FILE    = BOT_ROOT / "data" / "open_trades.json"
_ACCOUNT_SNAP_FILE   = BOT_ROOT / "data" / "account_snapshot.json"
_CLOSE_REQ_FILE      = BOT_ROOT / "data" / "close_requests.json"
_MODIFY_REQ_FILE     = BOT_ROOT / "data" / "modify_requests.json"


# ── SQLite helper ─────────────────────────────────────────────────────────────

def _db_conn() -> Optional[sqlite3.Connection]:
    if not LEARNING_DB.exists():
        return None
    conn = sqlite3.connect(str(LEARNING_DB), timeout=1)  # 1s max — prevents event-loop block
    conn.row_factory = sqlite3.Row
    return conn


def _query_one(sql: str, args: tuple = ()) -> Any:
    conn = _db_conn()
    if conn is None:
        return None
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _query_all(sql: str, args: tuple = ()) -> list[dict]:
    conn = _db_conn()
    if conn is None:
        return []
    try:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── JSON file helpers ─────────────────────────────────────────────────────────

def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return default if default is not None else {}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str))


def _default_config() -> dict:
    return {
        "risk": {
            "risk_per_trade": 1.0,
            "max_risk_per_trade": 2.0,
            "daily_drawdown_limit": 5.0,
            "max_open_trades": 3,
            "max_daily_loss": 100.0,
        },
        "strategy": {
            "min_confidence": 0.6,
            "min_zone_quality": 0.5,
            "require_sweep": False,
            "timeframe_primary": "H1",
            "symbols": ["XAUUSD"],
        },
        "psychology": {
            "max_consecutive_losses": 3,
            "cooldown_minutes": 60,
            "break_even_after_r": 1.0,
            "trailing_stop_enabled": True,
            "max_daily_trades": 5,
        },
        "learning": {
            "enabled": True,
            "min_samples": 30,
            "retrain_interval": 24,
            "validation_folds": 5,
            "min_win_rate_threshold": 0.5,
        },
        "sessions": {
            "london": True,
            "new_york": True,
            "tokyo": False,
            "sydney": False,
            "overlap": True,
        },
        "execution": {
            "slippage_pips": 1.0,
            "max_spread_pips": 3.0,
            "magic_number": 20240101,
            "comment": "XAUBot",
            "use_market_orders": True,
        },
    }


# ── Trade / session helpers ───────────────────────────────────────────────────

def _normalize_trade(t: dict) -> dict:
    """Reformat a raw open-trade dict to match iOS TradeRecord CodingKeys."""
    return {
        "ticket":         int(t.get("ticket", t.get("trade_id", 0))),
        "symbol":         str(t.get("symbol", "XAUUSD")),
        "direction":      str(t.get("direction", t.get("type", "BUY"))).upper(),
        "lots":           float(t.get("lots", t.get("volume", 0.0))),
        "open_price":     float(t.get("open_price", t.get("price_open", 0.0))),
        "current_price":  t.get("current_price"),
        "stop_loss":      t.get("stop_loss", t.get("sl")),
        "take_profit":    t.get("take_profit", t.get("tp")),
        "open_time":      str(t.get("open_time", "")),
        "close_time":     t.get("close_time"),
        "close_price":    t.get("close_price"),
        "pnl":            float(t.get("pnl", t.get("profit", 0.0))),
        "pips":           t.get("pips"),
        "commission":     float(t.get("commission", 0.0)),
        "swap":           float(t.get("swap", 0.0)),
        "session":        t.get("session"),
        "regime":         t.get("regime"),
        "confidence":     t.get("confidence"),
        "trigger_type":   t.get("trigger_type"),
        "sweep_detected": t.get("sweep_detected"),
        "zone_quality":   t.get("zone_quality"),
        "rr":             t.get("rr"),
        "status":         str(t.get("status", "open")),
        "ai_explanation": t.get("ai_explanation"),
    }


def _compute_session_quality(connected: bool, running: bool) -> str:
    if not connected or not running:
        return "poor"
    utc_hour = datetime.now(tz=timezone.utc).hour
    if 13 <= utc_hour < 17:
        return "excellent"
    if 8 <= utc_hour < 21:
        return "good"
    return "fair"


# ── BotService ────────────────────────────────────────────────────────────────

class BotService:

    # ── Process lifecycle ─────────────────────────────────────────────────────

    def _read_pid(self) -> Optional[int]:
        """Read the bot PID from the PID file."""
        if not PID_FILE.exists():
            return None
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            return None

    async def is_bot_running(self) -> bool:
        """Return True if the bot process is alive."""
        pid = self._read_pid()
        if pid is None:
            return False
        try:
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    async def get_bot_status(self) -> dict:
        """Return a dict with full bot runtime status."""
        running = await self.is_bot_running()
        pid = self._read_pid()

        uptime: Optional[int] = None
        if running and pid:
            try:
                uptime = int(datetime.now().timestamp() - psutil.Process(pid).create_time())
            except Exception:
                pass

        cfg = self.read_config()
        mode = cfg.get("bot", {}).get("mode", "backtest")
        learning_enabled = cfg.get("learning", {}).get("enabled", False)

        return {
            "running": running,
            "pid": pid,
            "paused": _FLAG_PAUSED.exists(),
            "maintenance_mode": _FLAG_MAINT.exists(),
            "emergency_stopped": _FLAG_EMERGENCY.exists(),
            "learning_enabled": learning_enabled,
            "mode": mode,
            "uptime_seconds": uptime,
        }

    async def start_bot(self) -> dict:
        if await self.is_bot_running():
            return {"ok": False, "detail": "Bot is already running"}

        # Determine Python executable
        python = str(BOT_PYTHON) if BOT_PYTHON.exists() else "python3"

        # Read mode from config
        cfg = self.read_config()
        mode = cfg.get("bot", {}).get("mode", "backtest")

        # Write log file path so we can capture startup errors
        log_path = BOT_ROOT / "logs" / "bot_startup.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(log_path, "a") as log_fh:
                proc = subprocess.Popen(
                    [python, str(BOT_SCRIPT), "--mode", mode],
                    cwd=str(BOT_ROOT),
                    start_new_session=True,
                    stdout=log_fh,
                    stderr=log_fh,
                )
            PID_FILE.write_text(str(proc.pid))
            logger.info("Bot started pid=%d mode=%s", proc.pid, mode)

            # Brief wait — verify the process didn't crash immediately
            await asyncio.sleep(2)
            try:
                p = psutil.Process(proc.pid)
                if not (p.is_running() and p.status() != psutil.STATUS_ZOMBIE):
                    PID_FILE.unlink(missing_ok=True)
                    # Try to surface the error from the log
                    try:
                        tail = log_path.read_text()[-500:]
                    except Exception:
                        tail = "(no log)"
                    return {"ok": False, "detail": f"Bot exited immediately. Log tail: {tail}"}
            except psutil.NoSuchProcess:
                PID_FILE.unlink(missing_ok=True)
                try:
                    tail = log_path.read_text()[-500:]
                except Exception:
                    tail = "(no log)"
                return {"ok": False, "detail": f"Bot process died on startup. Log tail: {tail}"}

            return {"ok": True, "detail": f"Bot started in {mode} mode (PID {proc.pid})", "pid": proc.pid}
        except Exception as exc:
            logger.error("Failed to start bot: %s", exc)
            return {"ok": False, "detail": str(exc)}

    async def stop_bot(self) -> dict:
        pid = self._read_pid()
        if pid is None:
            # Try systemd as fallback
            try:
                subprocess.run(
                    ["systemctl", "stop", settings.bot_service_name],
                    timeout=10,
                    check=False,
                )
                return {"ok": True, "detail": "Sent stop via systemd"}
            except FileNotFoundError:
                pass
            return {"ok": False, "detail": "Bot is not running (no PID file)"}

        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("SIGTERM sent to bot pid=%d", pid)
            return {"ok": True, "detail": f"SIGTERM sent to PID {pid}"}
        except ProcessLookupError:
            PID_FILE.unlink(missing_ok=True)
            return {"ok": False, "detail": "Process not found (stale PID file removed)"}
        except PermissionError:
            return {"ok": False, "detail": "Permission denied sending signal to bot process"}

    async def restart_bot(self) -> dict:
        stop_result = await self.stop_bot()
        await asyncio.sleep(2)
        start_result = await self.start_bot()
        return {
            "ok": start_result["ok"],
            "stop": stop_result,
            "start": start_result,
        }

    async def pause_bot(self) -> dict:
        """Create the .paused flag file — the bot checks this each bar."""
        _FLAG_PAUSED.touch()
        logger.info("Bot paused (flag file created)")
        return {"ok": True, "detail": "Bot paused"}

    async def resume_bot(self) -> dict:
        """Remove the .paused flag file."""
        if _FLAG_PAUSED.exists():
            _FLAG_PAUSED.unlink()
        logger.info("Bot resumed (flag file removed)")
        return {"ok": True, "detail": "Bot resumed"}

    async def emergency_stop(self) -> dict:
        """
        Emergency stop: write flag file, then SIGKILL the process.
        The flag file remains until explicitly cleared by the operator.
        """
        _FLAG_EMERGENCY.touch()
        pid = self._read_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
                PID_FILE.unlink(missing_ok=True)
                logger.warning("EMERGENCY STOP: SIGKILL sent to bot pid=%d", pid)
            except ProcessLookupError:
                pass
        return {"ok": True, "detail": "Emergency stop executed — manual clearance required"}

    async def clear_emergency_stop(self) -> dict:
        if _FLAG_EMERGENCY.exists():
            _FLAG_EMERGENCY.unlink()
        logger.info("Emergency stop flag cleared by operator")
        return {"ok": True, "detail": "Emergency stop flag cleared"}

    async def enable_maintenance(self) -> dict:
        _FLAG_MAINT.touch()
        return {"ok": True, "detail": "Maintenance mode enabled"}

    async def disable_maintenance(self) -> dict:
        if _FLAG_MAINT.exists():
            _FLAG_MAINT.unlink()
        return {"ok": True, "detail": "Maintenance mode disabled"}

    async def enable_learning(self) -> dict:
        cfg = self.read_config()
        cfg.setdefault("learning", {})["enabled"] = True
        self.write_config(cfg)
        return {"ok": True, "detail": "Learning engine enabled"}

    async def disable_learning(self) -> dict:
        cfg = self.read_config()
        cfg.setdefault("learning", {})["enabled"] = False
        self.write_config(cfg)
        return {"ok": True, "detail": "Learning engine disabled"}

    # ── Config management ─────────────────────────────────────────────────────

    def read_config(self) -> dict:
        if not CONFIG_PATH.exists():
            return _default_config()
        try:
            with open(CONFIG_PATH) as f:
                cfg = yaml.safe_load(f) or {}
            # Merge with defaults so missing keys don't break the iOS app
            defaults = _default_config()
            for section, values in defaults.items():
                cfg.setdefault(section, values)
            return cfg
        except Exception as exc:
            logger.error("Failed to read config: %s", exc)
            return _default_config()

    def write_config(self, config: dict) -> None:
        CONFIG_PATH.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
        )
        logger.info("Config written to %s", CONFIG_PATH)

    def update_config_section(self, section: str, values: dict) -> dict:
        cfg = self.read_config()
        if section in cfg and isinstance(cfg[section], dict):
            cfg[section].update(values)
        else:
            cfg[section] = values
        self.write_config(cfg)
        return cfg

    # ── Trade data ────────────────────────────────────────────────────────────

    def get_open_trades(self) -> list[dict]:
        return _read_json(_OPEN_TRADES_FILE, default=[])

    def get_account_snapshot(self) -> dict:
        return _read_json(_ACCOUNT_SNAP_FILE, default={})

    def get_trade_history(
        self,
        limit: int = 100,
        offset: int = 0,
        outcome: Optional[str] = None,
        session: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT * FROM trades WHERE 1=1"
        args: list[Any] = []
        if outcome:
            sql += " AND outcome = ?"
            args.append(outcome.upper())
        if session:
            sql += " AND session = ?"
            args.append(session)
        if start_date:
            sql += " AND date(open_time) >= ?"
            args.append(start_date)
        if end_date:
            sql += " AND date(open_time) <= ?"
            args.append(end_date)
        sql += " ORDER BY recorded_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        return _query_all(sql, tuple(args))

    def get_trade_by_id(self, trade_id: int) -> Optional[dict]:
        rows = _query_all(
            "SELECT t.*, f.* FROM trades t "
            "LEFT JOIN trade_features f ON t.trade_id = f.trade_id "
            "WHERE t.trade_id = ?",
            (trade_id,),
        )
        return rows[0] if rows else None

    def count_trades(self) -> int:
        return _query_one("SELECT COUNT(*) FROM trades") or 0

    def count_trades_filtered(
        self,
        outcome: Optional[str] = None,
        session: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        sql = "SELECT COUNT(*) FROM trades WHERE 1=1"
        args: list[Any] = []
        if outcome:
            sql += " AND outcome = ?"
            args.append(outcome.upper())
        if session:
            sql += " AND session = ?"
            args.append(session)
        if start_date:
            sql += " AND date(open_time) >= ?"
            args.append(start_date)
        if end_date:
            sql += " AND date(open_time) <= ?"
            args.append(end_date)
        return _query_one(sql, tuple(args)) or 0

    def get_performance_metrics(self) -> dict:
        """Compute trading performance metrics from the learning DB."""
        conn = _db_conn()
        if conn is None:
            return {}
        try:
            total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] or 0
            wins = conn.execute("SELECT COUNT(*) FROM trades WHERE outcome='WIN'").fetchone()[0] or 0

            pf_row = conn.execute("""
                SELECT
                  SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END),
                  ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END))
                FROM trades
            """).fetchone()
            gross_w = (pf_row[0] or 0.0)
            gross_l = (pf_row[1] or 0.0)

            today_str = date.today().isoformat()
            week_str  = (date.today() - timedelta(days=date.today().weekday())).isoformat()
            month_str = date.today().replace(day=1).isoformat()

            daily   = conn.execute("SELECT SUM(pnl) FROM trades WHERE date(open_time)=?",  (today_str,)).fetchone()[0] or 0.0
            weekly  = conn.execute("SELECT SUM(pnl) FROM trades WHERE date(open_time)>=?", (week_str,)).fetchone()[0] or 0.0
            monthly = conn.execute("SELECT SUM(pnl) FROM trades WHERE date(open_time)>=?", (month_str,)).fetchone()[0] or 0.0
            total_p = conn.execute("SELECT SUM(pnl) FROM trades").fetchone()[0] or 0.0
            avg_r   = conn.execute("SELECT AVG(pnl_r) FROM trades").fetchone()[0] or 0.0

            # Recent win rate (last 50)
            recent = conn.execute(
                "SELECT outcome FROM trades ORDER BY recorded_at DESC LIMIT 50"
            ).fetchall()
            recent_wins = sum(1 for r in recent if r[0] == "WIN")
            recent_wr = recent_wins / len(recent) if recent else 0.0

            initial_capital = self.read_config().get("risk", {}).get("initial_capital", 10000.0)

            return {
                "total_trades": total,
                "win_rate": round(wins / total, 4) if total else 0.0,
                "win_rate_recent_50": round(recent_wr, 4),
                "profit_factor": round(gross_w / gross_l, 3) if gross_l > 0 else 0.0,
                "avg_r": round(avg_r, 3),
                "daily_pnl": round(daily, 2),
                "daily_pnl_pct": round(daily / initial_capital * 100, 4) if initial_capital else 0.0,
                "weekly_pnl": round(weekly, 2),
                "weekly_pnl_pct": round(weekly / initial_capital * 100, 4) if initial_capital else 0.0,
                "monthly_pnl": round(monthly, 2),
                "monthly_pnl_pct": round(monthly / initial_capital * 100, 4) if initial_capital else 0.0,
                "total_pnl": round(total_p, 2),
            }
        finally:
            conn.close()

    def get_equity_curve(self) -> list[dict]:
        """Return a list of {ts, equity} points building the equity curve."""
        initial = self.read_config().get("risk", {}).get("initial_capital", 10000.0)
        rows = _query_all(
            "SELECT open_time, pnl FROM trades ORDER BY recorded_at ASC"
        )
        equity = initial
        curve = []
        for r in rows:
            equity += (r.get("pnl") or 0.0)
            curve.append({"ts": r.get("open_time"), "equity": round(equity, 2)})
        return curve

    def get_drawdown_series(self) -> list[dict]:
        """Return {ts, drawdown_pct} series computed from the equity curve."""
        curve = self.get_equity_curve()
        if not curve:
            return []
        peak = curve[0]["equity"]
        series = []
        for point in curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
            series.append({"ts": point["ts"], "drawdown_pct": round(dd, 4), "equity": eq})
        return series

    # ── Learning stats ────────────────────────────────────────────────────────

    def get_learning_stats(self) -> dict:
        conn = _db_conn()
        if conn is None:
            return {"trade_count": 0, "significant_patterns": 0, "learning_enabled": False}
        try:
            trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] or 0
            pattern_count = conn.execute(
                "SELECT COUNT(*) FROM pattern_stats WHERE is_significant=1"
            ).fetchone()[0] or 0
            last_val_row = conn.execute(
                "SELECT run_at, passed, overfit_score, oos_expectancy, is_expectancy "
                "FROM validation_results ORDER BY run_at DESC LIMIT 1"
            ).fetchone()
            last_val: dict = {}
            if last_val_row:
                last_val = {
                    "run_at": last_val_row[0],
                    "passed": bool(last_val_row[1]),
                    "overfit_score": last_val_row[2],
                    "oos_expectancy": last_val_row[3],
                    "is_expectancy": last_val_row[4],
                }
            last_event = conn.execute(
                "SELECT ts FROM learning_events ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            cfg = self.read_config()
            return {
                "trade_count": trade_count,
                "significant_patterns": pattern_count,
                "last_validation": last_val,
                "last_analysis_time": last_event[0] if last_event else None,
                "learning_enabled": cfg.get("learning", {}).get("enabled", False),
            }
        finally:
            conn.close()

    def get_pattern_stats(self, min_samples: int = 0) -> list[dict]:
        sql = "SELECT * FROM pattern_stats WHERE sample_count >= ? ORDER BY abs(expectancy_r) DESC"
        return _query_all(sql, (min_samples,))

    def get_regime_history(self, limit: int = 200) -> list[dict]:
        return _query_all(
            "SELECT ts, regime, volatility_regime, trend_strength, atr_ratio "
            "FROM regime_history ORDER BY bar_index DESC LIMIT ?",
            (limit,),
        )

    def get_validation_results(self, limit: int = 20) -> list[dict]:
        return _query_all(
            "SELECT * FROM validation_results ORDER BY run_at DESC LIMIT ?",
            (limit,),
        )

    def get_learning_events(self, limit: int = 50) -> list[dict]:
        return _query_all(
            "SELECT * FROM learning_events ORDER BY ts DESC LIMIT ?",
            (limit,),
        )

    def get_confidence_weights_top(self, n: int = 30) -> list[dict]:
        return _query_all(
            "SELECT feature_name, feature_value, regime, weight, sample_count "
            "FROM confidence_weights ORDER BY ABS(weight - 0.5) DESC LIMIT ?",
            (n,),
        )

    # ── Trade modification ────────────────────────────────────────────────────

    def close_trade(self, trade_id: int, partial: bool = False, pct: float = 1.0) -> dict:
        """
        Write a close request to the shared request file.
        The bot's execution engine reads this file each bar and acts on it.
        """
        existing = _read_json(_CLOSE_REQ_FILE, default=[])
        existing.append({
            "trade_id": trade_id,
            "type": "partial" if partial else "full",
            "pct": pct,
            "requested_at": datetime.now(tz=timezone.utc).isoformat(),
        })
        _write_json(_CLOSE_REQ_FILE, existing)
        return {"ok": True, "trade_id": trade_id, "type": "partial" if partial else "full"}

    def modify_trade(
        self, trade_id: int, sl: Optional[float] = None, tp: Optional[float] = None
    ) -> dict:
        existing = _read_json(_MODIFY_REQ_FILE, default=[])
        req: dict[str, Any] = {
            "trade_id": trade_id,
            "requested_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        if sl is not None:
            req["sl"] = sl
        if tp is not None:
            req["tp"] = tp
        existing.append(req)
        _write_json(_MODIFY_REQ_FILE, existing)
        return {"ok": True, "trade_id": trade_id}

    def get_trade_ai_explanation(self, trade_id: int) -> dict:
        """
        Return the AI explanation from the post-trade review and learning stats
        for a specific completed trade.
        """
        conn = _db_conn()
        if conn is None:
            return {"explanation": "Learning database not available"}
        try:
            review = conn.execute(
                "SELECT * FROM post_trade_reviews WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            trade = conn.execute(
                "SELECT t.*, f.* FROM trades t "
                "LEFT JOIN trade_features f ON t.trade_id = f.trade_id "
                "WHERE t.trade_id = ?",
                (trade_id,),
            ).fetchone()
            if review is None:
                return {"explanation": "No AI analysis available for this trade"}
            review_d = dict(review)
            trade_d  = dict(trade) if trade else {}
            narrative = review_d.get("narrative", "")
            recs_raw = review_d.get("recommendations", "[]")
            try:
                recs = json.loads(recs_raw) if isinstance(recs_raw, str) else recs_raw
            except Exception:
                recs = []
            return {
                "trade_id": trade_id,
                "outcome": trade_d.get("outcome"),
                "pnl_r": trade_d.get("pnl_r"),
                "pattern_key": trade_d.get("pattern_key"),
                "regime": trade_d.get("regime"),
                "narrative": narrative,
                "recommendations": recs,
                "entry_timing_score": review_d.get("entry_timing_score"),
                "confirmation_score": review_d.get("confirmation_score"),
                "sl_quality_score": review_d.get("sl_quality_score"),
                "overall_decision_score": review_d.get("overall_decision_score"),
            }
        finally:
            conn.close()

    # ── Dashboard snapshot ────────────────────────────────────────────────────

    async def get_dashboard_snapshot(self) -> dict:
        """
        Build the full dashboard payload in iOS DashboardSnapshot format.
        Called by the REST dashboard endpoint and the WebSocket worker.
        All blocking I/O runs in a thread pool to avoid stalling the event loop.
        """
        # Run all blocking operations concurrently in a thread pool
        bot_status, account, metrics, open_trades = await asyncio.gather(
            self.get_bot_status(),
            asyncio.to_thread(self.get_account_snapshot),
            asyncio.to_thread(self.get_performance_metrics),
            asyncio.to_thread(self.get_open_trades),
        )

        # Fallback to active_account.json for display when no live MT5 snapshot
        if not account:
            active_path = BOT_ROOT / "data" / "active_account.json"
            if active_path.exists():
                try:
                    creds   = await asyncio.to_thread(
                        lambda: json.loads(active_path.read_text())
                    )
                    account = {
                        "account_number": str(creds.get("login", "—")),
                        "server":         str(creds.get("server", "—")),
                        "connected":      False,
                    }
                except Exception:
                    pass

        cfg = await asyncio.to_thread(self.read_config)
        initial_capital = cfg.get("risk", {}).get("initial_capital", 10000.0)
        balance   = float(account.get("balance",  initial_capital))
        equity    = float(account.get("equity",   balance))
        connected = bool(account.get("connected", False))
        running   = bot_status["running"]
        now       = datetime.now(tz=timezone.utc).isoformat()

        return {
            "bot_status": {
                "running":           running,
                "paused":            bot_status["paused"],
                "maintenance_mode":  bot_status["maintenance_mode"],
                "emergency_stopped": bot_status["emergency_stopped"],
                "learning_enabled":  bot_status["learning_enabled"],
                "pid":               bot_status["pid"],
                "mode":              bot_status["mode"],
                "last_heartbeat":    None,
                "last_trade_at":     None,
                "open_trades_count": len(open_trades),
                "daily_pnl":         float(metrics.get("daily_pnl",  0.0)),
                "equity":            round(equity, 2),
                "updated_at":        now,
            },
            "account_info": {
                "account_number": str(account.get("account_number", account.get("login", "—"))),
                "broker":         str(account.get("broker", account.get("company", "Unknown"))),
                "server":         str(account.get("server", "—")),
                "currency":       str(account.get("currency", "USD")),
                "leverage":       int(account.get("leverage", 100)),
                "balance":        round(balance, 2),
                "equity":         round(equity, 2),
                "margin":         round(float(account.get("margin",      account.get("used_margin",  0.0))), 2),
                "free_margin":    round(float(account.get("free_margin", account.get("margin_free", equity))), 2),
                "margin_level":   account.get("margin_level"),
                "connected":      connected,
                "latency_ms":     account.get("latency_ms"),
            },
            "open_trades":    [_normalize_trade(t) for t in open_trades],
            "daily_pnl":      float(metrics.get("daily_pnl",   0.0)),
            "weekly_pnl":     float(metrics.get("weekly_pnl",  0.0)),
            "monthly_pnl":    float(metrics.get("monthly_pnl", 0.0)),
            "unrealized_pnl": round(sum(float(t.get("pnl", 0.0)) for t in open_trades), 2),
            "session_quality": _compute_session_quality(connected, running),
            "timestamp":      now,
        }


# Singleton instance
bot_service = BotService()
