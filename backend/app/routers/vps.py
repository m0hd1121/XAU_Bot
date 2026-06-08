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

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.security import get_current_user, require_admin
from app.services.vps_service import vps_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stats", summary="System resource stats (CPU, RAM, disk, network)")
async def system_stats(_user=Depends(get_current_user)) -> dict:
    """Returns real-time system resource utilization via psutil."""
    return vps_service.get_system_stats()


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
