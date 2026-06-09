"""
routers/bot_control.py
───────────────────────
Bot lifecycle and operational control endpoints.

All mutating endpoints:
  • Require admin role (operator can read status)
  • Write an AuditLog entry via the audit middleware
  • Confirm action success/failure from the bot_service

Endpoints:
  POST /bot/start               — start bot process
  POST /bot/stop                — SIGTERM the bot process
  POST /bot/restart             — stop + start
  POST /bot/pause               — set .paused flag
  POST /bot/resume              — remove .paused flag
  POST /bot/emergency-stop      — SIGKILL + set .emergency_stop flag
  POST /bot/clear-emergency     — remove .emergency_stop flag (operator re-enables trading)
  POST /bot/maintenance/enable  — set .maintenance flag
  POST /bot/maintenance/disable — remove .maintenance flag
  POST /bot/learning/enable     — enable learning in config.yaml
  POST /bot/learning/disable    — disable learning in config.yaml
  GET  /bot/status              — full bot status dict
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.security import get_current_user, require_admin, require_operator
from app.services.bot_service import bot_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ControlResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[Any] = None

    @classmethod
    def from_result(cls, result: dict) -> "ControlResponse":
        return cls(
            success=result.get("ok", result.get("success", False)),
            message=result.get("detail", result.get("message", "")),
            data={"pid": result["pid"]} if result.get("pid") else None,
        )


class BotStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    paused: bool
    maintenance_mode: bool
    emergency_stopped: bool
    learning_enabled: bool
    mode: str
    uptime_seconds: Optional[int] = None


# ── Action helper ─────────────────────────────────────────────────────────────

async def _log_action(user: Any, action: str, result: dict) -> None:
    """Persist an explicit audit entry for critical bot control actions."""
    import asyncio
    asyncio.create_task(_write_bot_audit(user, action, result))


async def _write_bot_audit(user: Any, action: str, result: dict) -> None:
    try:
        from app.database import db_session
        from app.models.models import AuditLog
        async with db_session() as db:
            entry = AuditLog(
                user_id=user.id,
                username=user.username,
                action=f"bot_control:{action}",
                method="POST",
                path=f"/api/v1/bot/{action}",
                notes=f"Result: {result.get('detail', result.get('ok'))}",
            )
            db.add(entry)
    except Exception as exc:
        logger.warning("Bot audit write failed: %s", exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=BotStatusResponse, summary="Get bot runtime status")
async def bot_status(
    _user=Depends(get_current_user),
) -> BotStatusResponse:
    s = await bot_service.get_bot_status()
    return BotStatusResponse(**s)


@router.post("/start", response_model=ControlResponse, summary="Start the bot process")
async def start_bot(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.start_bot()
    await _log_action(user, "start", result)
    return ControlResponse.from_result(result)


@router.post("/stop", response_model=ControlResponse, summary="Stop the bot process (SIGTERM)")
async def stop_bot(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.stop_bot()
    await _log_action(user, "stop", result)
    return ControlResponse.from_result(result)


@router.post("/restart", response_model=ControlResponse, summary="Restart the bot process")
async def restart_bot(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.restart_bot()
    await _log_action(user, "restart", result)
    return ControlResponse.from_result(result)


@router.post("/pause", response_model=ControlResponse, summary="Pause trading (flag file)")
async def pause_bot(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.pause_bot()
    await _log_action(user, "pause", result)
    return ControlResponse.from_result(result)


@router.post("/resume", response_model=ControlResponse, summary="Resume trading (remove flag)")
async def resume_bot(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.resume_bot()
    await _log_action(user, "resume", result)
    return ControlResponse.from_result(result)


@router.post(
    "/emergency-stop",
    response_model=ControlResponse,
    summary="Emergency stop: SIGKILL + set flag (requires manual clear)",
)
async def emergency_stop(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.emergency_stop()
    await _log_action(user, "emergency_stop", result)
    return ControlResponse.from_result(result)


@router.post(
    "/clear-emergency",
    response_model=ControlResponse,
    summary="Clear emergency stop flag (re-enables start)",
)
async def clear_emergency(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.clear_emergency_stop()
    await _log_action(user, "clear_emergency", result)
    return ControlResponse.from_result(result)


@router.post(
    "/maintenance/enable",
    response_model=ControlResponse,
    summary="Enable maintenance mode",
)
async def enable_maintenance(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.enable_maintenance()
    await _log_action(user, "maintenance_enable", result)
    return ControlResponse.from_result(result)


@router.post(
    "/maintenance/disable",
    response_model=ControlResponse,
    summary="Disable maintenance mode",
)
async def disable_maintenance(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.disable_maintenance()
    await _log_action(user, "maintenance_disable", result)
    return ControlResponse.from_result(result)


@router.post(
    "/learning/enable",
    response_model=ControlResponse,
    summary="Enable the self-learning engine in config.yaml",
)
async def enable_learning(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.enable_learning()
    await _log_action(user, "learning_enable", result)
    return ControlResponse.from_result(result)


@router.post(
    "/learning/disable",
    response_model=ControlResponse,
    summary="Disable the self-learning engine in config.yaml",
)
async def disable_learning(user=Depends(require_admin)) -> ControlResponse:
    result = await bot_service.disable_learning()
    await _log_action(user, "learning_disable", result)
    return ControlResponse.from_result(result)
