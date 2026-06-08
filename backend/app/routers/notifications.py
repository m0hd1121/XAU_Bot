"""
routers/notifications.py
─────────────────────────
iOS APNs push notification management.

POST /notifications/device/register     — register a device token
POST /notifications/device/unregister   — unregister a device token
GET  /notifications/devices             — list registered devices for this user
PUT  /notifications/preferences         — update notification preferences
GET  /notifications/preferences         — get current notification preferences
POST /notifications/test                — send a test push notification
GET  /notifications/recent              — list recent notification records
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import APNSDevice, Notification
from app.services.notification_service import NotificationService, PushPayload, notification_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Default notification preferences ─────────────────────────────────────────

DEFAULT_PREFERENCES = {
    "trade_opened":  True,
    "trade_closed":  True,
    "bot_stopped":   True,
    "drawdown_alert": True,
    "daily_summary": True,
    "error":         True,
    "general":       True,
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterDeviceRequest(BaseModel):
    device_token: str = Field(..., min_length=32, max_length=256)
    device_name: Optional[str] = Field(None, max_length=128)
    os_version: Optional[str] = Field(None, max_length=32)
    app_version: Optional[str] = Field(None, max_length=32)


class UnregisterDeviceRequest(BaseModel):
    device_token: str


class UpdatePreferencesRequest(BaseModel):
    trade_opened: Optional[bool] = None
    trade_closed: Optional[bool] = None
    bot_stopped: Optional[bool] = None
    drawdown_alert: Optional[bool] = None
    daily_summary: Optional[bool] = None
    error: Optional[bool] = None
    general: Optional[bool] = None


class TestNotificationRequest(BaseModel):
    title: str = Field("XAU Bot Test", max_length=128)
    body: str = Field("Push notifications are working correctly.", max_length=256)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/device/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register iOS device for push notifications",
)
async def register_device(
    req: RegisterDeviceRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Upsert device record
    result = await db.execute(
        select(APNSDevice).where(APNSDevice.device_token == req.device_token)
    )
    device = result.scalar_one_or_none()

    if device is None:
        device = APNSDevice(
            user_id=current_user.id,
            device_token=req.device_token,
            device_name=req.device_name,
            os_version=req.os_version,
            app_version=req.app_version,
            preferences_json=json.dumps(DEFAULT_PREFERENCES),
            active=True,
        )
        db.add(device)
    else:
        device.active = True
        device.last_seen = datetime.now(tz=timezone.utc)
        device.device_name = req.device_name or device.device_name
        device.os_version   = req.os_version or device.os_version
        device.app_version  = req.app_version or device.app_version

    await db.commit()

    # Register with in-memory notification service
    notification_service.register_device(req.device_token)

    logger.info("Device registered user=%s token=%s...", current_user.username, req.device_token[:8])
    return {"ok": True, "device_token": req.device_token[:8] + "..."}


@router.post(
    "/device/unregister",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Unregister device",
)
async def unregister_device(
    req: UnregisterDeviceRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        update(APNSDevice)
        .where(
            APNSDevice.device_token == req.device_token,
            APNSDevice.user_id == current_user.id,
        )
        .values(active=False)
    )
    await db.commit()
    notification_service.unregister_device(req.device_token)


@router.get("/devices", summary="List registered devices for current user")
async def list_devices(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(APNSDevice).where(
            APNSDevice.user_id == current_user.id,
            APNSDevice.active == True,  # noqa: E712
        )
    )
    devices = result.scalars().all()
    return {
        "devices": [
            {
                "id": d.id,
                "device_token": d.device_token[:8] + "...",
                "device_name": d.device_name,
                "os_version": d.os_version,
                "app_version": d.app_version,
                "registered_at": d.registered_at.isoformat() if d.registered_at else None,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            }
            for d in devices
        ],
        "count": len(devices),
    }


@router.get("/preferences", summary="Get notification preferences")
async def get_preferences(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(APNSDevice).where(
            APNSDevice.user_id == current_user.id,
            APNSDevice.active == True,  # noqa: E712
        )
    )
    device = result.scalars().first()
    if device is None:
        return {"preferences": DEFAULT_PREFERENCES}
    try:
        prefs = json.loads(device.preferences_json or "{}")
    except Exception:
        prefs = {}
    merged = {**DEFAULT_PREFERENCES, **prefs}
    return {"preferences": merged}


@router.put(
    "/preferences",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Update notification preferences",
)
async def update_preferences(
    req: UpdatePreferencesRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(APNSDevice).where(
            APNSDevice.user_id == current_user.id,
            APNSDevice.active == True,  # noqa: E712
        )
    )
    devices = result.scalars().all()
    if not devices:
        return

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    for device in devices:
        try:
            prefs = json.loads(device.preferences_json or "{}")
        except Exception:
            prefs = {}
        prefs.update(updates)
        device.preferences_json = json.dumps(prefs)

    await db.commit()


@router.post("/test", summary="Send a test push notification to all registered devices")
async def send_test_notification(
    req: TestNotificationRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(APNSDevice).where(
            APNSDevice.user_id == current_user.id,
            APNSDevice.active == True,  # noqa: E712
        )
    )
    devices = result.scalars().all()
    if not devices:
        return {"sent": 0, "detail": "No registered devices"}

    results = []
    for device in devices:
        ok = await notification_service.send(
            PushPayload(
                device_token=device.device_token,
                title=req.title,
                body=req.body,
                category="test",
                data={"type": "test"},
            )
        )
        results.append({"device_name": device.device_name, "sent": ok})

    # Record notification
    try:
        notif = Notification(
            user_id=current_user.id,
            title=req.title,
            body=req.body,
            category="general",
            priority="normal",
            sent=any(r["sent"] for r in results),
            sent_at=datetime.now(tz=timezone.utc) if any(r["sent"] for r in results) else None,
        )
        db.add(notif)
        await db.commit()
    except Exception:
        pass

    return {"sent": sum(1 for r in results if r["sent"]), "results": results}


@router.get("/recent", summary="List recent notification records")
async def recent_notifications(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifs = result.scalars().all()
    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "category": n.category,
                "priority": n.priority,
                "sent": n.sent,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "read": n.read,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifs
        ],
        "count": len(notifs),
    }
