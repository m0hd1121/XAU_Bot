"""
services/vps_service.py
────────────────────────
VPS system monitoring and systemd service management.

Provides:
  • Real-time system resource stats via psutil
  • Systemd service status via `systemctl is-active`
  • Systemd service restart via `sudo systemctl restart`
  • List of Python processes currently running on the VPS
"""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

import psutil

from app.config import settings

logger = logging.getLogger(__name__)

# Managed service names — only these can be restarted via the API
MANAGED_SERVICES: list[str] = [
    settings.api_service_name,
    settings.worker_service_name,
    settings.bot_service_name,
]


class VPSService:

    # ── System stats ──────────────────────────────────────────────────────────

    def get_system_stats(self) -> dict:
        """Return a snapshot of CPU, RAM, disk, network and load average."""
        cpu_pct  = psutil.cpu_percent(interval=0.5)
        cpu_freq = psutil.cpu_freq()
        mem      = psutil.virtual_memory()
        swap     = psutil.swap_memory()
        disk     = psutil.disk_usage("/")
        net      = psutil.net_io_counters()
        boot_ts  = psutil.boot_time()
        uptime_s = int(time.time() - boot_ts)

        try:
            load_avg = list(psutil.getloadavg())
        except AttributeError:
            load_avg = [0.0, 0.0, 0.0]

        return {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "cpu": {
                "percent": cpu_pct,
                "count_logical": psutil.cpu_count(logical=True),
                "count_physical": psutil.cpu_count(logical=False),
                "freq_mhz": round(cpu_freq.current, 1) if cpu_freq else None,
                "load_avg_1m": round(load_avg[0], 2),
                "load_avg_5m": round(load_avg[1], 2),
                "load_avg_15m": round(load_avg[2], 2),
            },
            "ram": {
                "total_mb": mem.total // (1024 ** 2),
                "used_mb":  mem.used  // (1024 ** 2),
                "free_mb":  mem.available // (1024 ** 2),
                "percent":  mem.percent,
            },
            "swap": {
                "total_mb": swap.total // (1024 ** 2),
                "used_mb":  swap.used  // (1024 ** 2),
                "percent":  swap.percent,
            },
            "disk": {
                "total_gb":  round(disk.total / (1024 ** 3), 1),
                "used_gb":   round(disk.used  / (1024 ** 3), 1),
                "free_gb":   round(disk.free  / (1024 ** 3), 1),
                "percent":   disk.percent,
            },
            "network": {
                "bytes_sent":   net.bytes_sent,
                "bytes_recv":   net.bytes_recv,
                "packets_sent": net.packets_sent,
                "packets_recv": net.packets_recv,
                "errin":        net.errin,
                "errout":       net.errout,
            },
            "uptime": {
                "seconds": uptime_s,
                "human":   _fmt_uptime(uptime_s),
                "boot_at": datetime.fromtimestamp(boot_ts, tz=timezone.utc).isoformat(),
            },
        }

    # ── Systemd service management ────────────────────────────────────────────

    def get_service_status(self, name: str) -> dict:
        """Query systemctl for the active state of a service."""
        try:
            out = subprocess.check_output(
                ["systemctl", "is-active", name],
                text=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).strip()
            active_state = out
        except subprocess.CalledProcessError as exc:
            active_state = (exc.output or "").strip() if exc.output else "inactive"
        except FileNotFoundError:
            active_state = "unavailable"
        except Exception as exc:
            active_state = f"error: {exc}"

        # Also get enabled state
        try:
            enabled_out = subprocess.check_output(
                ["systemctl", "is-enabled", name],
                text=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).strip()
            enabled = enabled_out == "enabled"
        except Exception:
            enabled = None

        return {
            "name": name,
            "active_state": active_state,
            "is_active": active_state == "active",
            "is_enabled": enabled,
        }

    def get_all_services(self) -> list[dict]:
        return [self.get_service_status(s) for s in MANAGED_SERVICES]

    def restart_service(self, name: str) -> dict:
        """Restart a managed systemd service via D-Bus (no sudo required)."""
        if name not in MANAGED_SERVICES:
            return {"ok": False, "detail": f"Service '{name}' is not in the managed list"}

        # Try systemctl without sudo first (works if the process has sufficient privileges)
        for cmd in [
            ["systemctl", "restart", name],
            ["dbus-send", "--system", "--print-reply",
             "--dest=org.freedesktop.systemd1",
             "/org/freedesktop/systemd1",
             "org.freedesktop.systemd1.Manager.RestartUnit",
             f"string:{name}", "string:replace"],
        ]:
            try:
                subprocess.run(cmd, check=True, timeout=30,
                               capture_output=True, text=True)
                logger.info("Service restarted: %s (cmd=%s)", name, cmd[0])
                return {"ok": True, "service": name}
            except subprocess.CalledProcessError as exc:
                last_err = exc.stderr.strip() if exc.stderr else str(exc)
            except FileNotFoundError:
                last_err = f"{cmd[0]} not found"
            except Exception as exc:
                last_err = str(exc)

        logger.error("Failed to restart service %s: %s", name, last_err)
        return {"ok": False, "detail": last_err}

    # ── Process monitoring ────────────────────────────────────────────────────

    def get_python_processes(self) -> list[dict]:
        """List Python processes running on the VPS."""
        procs: list[dict] = []
        for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "cpu_percent", "memory_percent",
             "create_time", "status", "username"]
        ):
            try:
                name = proc.info["name"] or ""
                if "python" not in name.lower():
                    continue
                cmdline = proc.info.get("cmdline") or []
                procs.append({
                    "pid": proc.info["pid"],
                    "name": name,
                    "cmdline": " ".join(cmdline)[:200],
                    "status": proc.info.get("status"),
                    "cpu_percent": round(proc.info.get("cpu_percent") or 0.0, 2),
                    "memory_percent": round(proc.info.get("memory_percent") or 0.0, 2),
                    "uptime_seconds": int(time.time() - (proc.info.get("create_time") or time.time())),
                    "username": proc.info.get("username"),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return procs


def _fmt_uptime(seconds: int) -> str:
    d, rem  = divmod(seconds, 86400)
    h, rem  = divmod(rem, 3600)
    m       = rem // 60
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


# Singleton
vps_service = VPSService()
