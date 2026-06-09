"""
routers/vps.py
───────────────
VPS monitoring and service management endpoints.

GET  /vps/stats                    — CPU, RAM, disk, network, uptime
GET  /vps/services                 — status of all managed systemd services
GET  /vps/services/{name}          — status of a single service
POST /vps/services/{name}/restart  — restart a managed service (admin only)
GET  /vps/processes                — list Python processes running on the VPS
"""

from __future__ import annotations

import logging
import platform
import sys
import time

import psutil

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.security import get_current_user, require_admin
from app.services.vps_service import vps_service, MANAGED_SERVICES

logger = logging.getLogger(__name__)
router = APIRouter()

# Track previous network counters for KB/s delta calculation
_prev_net: dict = {}


def _ios_stats() -> dict:
    """Build the flat VPSStats payload the iOS app expects."""
    global _prev_net

    raw   = vps_service.get_system_stats()
    cpu   = raw.get("cpu",     {})
    ram   = raw.get("ram",     {})
    disk  = raw.get("disk",    {})
    net   = raw.get("network", {})
    up    = raw.get("uptime",  {})

    # Network KB/s delta
    now = time.monotonic()
    net_in_kbs  = 0.0
    net_out_kbs = 0.0
    if _prev_net:
        elapsed = now - _prev_net["ts"]
        if elapsed > 0:
            net_in_kbs  = max(0.0, (net.get("bytes_recv", 0) - _prev_net["recv"]) / elapsed / 1024)
            net_out_kbs = max(0.0, (net.get("bytes_sent", 0) - _prev_net["sent"]) / elapsed / 1024)
    _prev_net = {
        "ts":   now,
        "recv": net.get("bytes_recv", 0),
        "sent": net.get("bytes_sent", 0),
    }

    # RAM in GB
    total_ram_mb = float(ram.get("total_mb", 0))
    used_ram_mb  = float(ram.get("used_mb",  0))

    # Services in iOS ServiceStatus format
    raw_services = vps_service.get_all_services()
    services = []
    for svc in raw_services:
        name        = svc.get("name", "")
        active_state = svc.get("active_state", "unknown")
        # Map systemd active states → iOS display states
        if active_state == "active":
            ios_status = "active"
        elif active_state in ("inactive", "dead"):
            ios_status = "inactive"
        elif active_state == "failed":
            ios_status = "failed"
        else:
            ios_status = "unknown"

        services.append({
            "name":         name,
            "display_name": name.replace("-", " ").replace("_", " ").title(),
            "status":       ios_status,
            "pid":          None,
            "uptime":       None,
            "memory_mb":    None,
            "can_restart":  name in MANAGED_SERVICES,
        })

    load_avg = [
        cpu.get("load_avg_1m",  0.0),
        cpu.get("load_avg_5m",  0.0),
        cpu.get("load_avg_15m", 0.0),
    ]

    return {
        "cpu_pct":        float(cpu.get("percent", 0.0)),
        "ram_pct":        float(ram.get("percent", 0.0)),
        "disk_pct":       float(disk.get("percent", 0.0)),
        "network_in":     round(net_in_kbs,  2),
        "network_out":    round(net_out_kbs, 2),
        "uptime_seconds": int(up.get("seconds", 0)),
        "os_version":     platform.platform(),
        "python_version": sys.version.split()[0],
        "bot_version":    "1.0.0",
        "services":       services,
        "load_average":   load_avg,
        "total_ram_gb":   round(total_ram_mb / 1024, 2),
        "used_ram_gb":    round(used_ram_mb  / 1024, 2),
        "total_disk_gb":  float(disk.get("total_gb", 0.0)),
        "used_disk_gb":   float(disk.get("used_gb",  0.0)),
    }


@router.get("/stats", summary="System resource stats (CPU, RAM, disk, network)")
async def system_stats(_user=Depends(get_current_user)) -> dict:
    """Returns real-time system resource utilization in iOS-compatible format."""
    return _ios_stats()


@router.get("/services", summary="Status of all managed systemd services")
async def list_services(_user=Depends(get_current_user)) -> dict:
    services = vps_service.get_all_services()
    return {"services": services, "count": len(services)}


@router.get("/services/{name}", summary="Status of a single systemd service")
async def service_status(name: str, _user=Depends(get_current_user)) -> dict:
    return vps_service.get_service_status(name)


@router.post("/services/{name}/restart", summary="Restart a managed systemd service")
async def restart_service(
    name: str,
    _user=Depends(require_admin),
) -> dict:
    result = vps_service.restart_service(name)
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("detail", "Failed to restart service"),
        )
    return result


@router.get("/processes", summary="Python processes currently running on the VPS")
async def python_processes(_user=Depends(require_admin)) -> dict:
    procs = vps_service.get_python_processes()
    return {"processes": procs, "count": len(procs)}
