"""
services/notification_service.py
──────────────────────────────────
APNs push notification service.

Implementation:
  • HTTP/2 connection to APNs via httpx (with http2=True)
  • JWT-based provider authentication (ES256) signed with the APNs private key
  • Token cached for 45 minutes (APNs tokens are valid for 60 min)
  • In-memory queue for pending notifications with retry logic
  • Falls back gracefully (logs a warning) if APNs credentials are not configured

Configuration (via settings / .env):
  APNS_KEY_ID      — 10-character APNs key ID from Apple Developer portal
  APNS_TEAM_ID     — 10-character Apple Developer Team ID
  APNS_KEY_PATH    — path to the .p8 private key file
  APNS_BUNDLE_ID   — iOS app bundle ID (e.g. com.xaubot.app)
  APNS_USE_SANDBOX — true for development, false for production
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

APNS_HOST_PROD    = "https://api.push.apple.com"
APNS_HOST_SANDBOX = "https://api.sandbox.push.apple.com"
_TOKEN_VALID_SECONDS = 2700  # Refresh at 45 min; APNs tokens valid for 60 min


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PushPayload:
    device_token: str
    title: str
    body: str
    category: str = ""
    badge: Optional[int] = None
    sound: str = "default"
    data: dict = field(default_factory=dict)
    priority: int = 10  # 10 = immediate, 5 = power-saving
    collapse_id: Optional[str] = None


@dataclass
class _QueuedNotification:
    payload: PushPayload
    attempts: int = 0
    max_attempts: int = 3
    next_attempt_at: float = field(default_factory=time.time)


# ── NotificationService ───────────────────────────────────────────────────────

class NotificationService:

    def __init__(self) -> None:
        self._jwt_token: Optional[str] = None
        self._jwt_issued_at: float = 0.0
        self._device_tokens: list[str] = []
        self._queue: list[_QueuedNotification] = []
        self._queue_task: Optional[asyncio.Task] = None
        self._apns_configured = bool(
            settings.apns_key_id and settings.apns_team_id and settings.apns_key_path
        )
        if not self._apns_configured:
            logger.warning(
                "APNs not configured — push notifications disabled. "
                "Set APNS_KEY_ID, APNS_TEAM_ID, APNS_KEY_PATH in environment."
            )

    # ── Device registry ───────────────────────────────────────────────────────

    def register_device(self, token: str) -> None:
        if token not in self._device_tokens:
            self._device_tokens.append(token)
            logger.debug("Device registered token=%s...", token[:8])

    def unregister_device(self, token: str) -> None:
        self._device_tokens = [t for t in self._device_tokens if t != token]

    # ── JWT token management ──────────────────────────────────────────────────

    def _build_apns_jwt(self) -> Optional[str]:
        """Build and cache the APNs provider JWT using ES256."""
        now = time.time()
        if self._jwt_token and (now - self._jwt_issued_at) < _TOKEN_VALID_SECONDS:
            return self._jwt_token

        if not self._apns_configured:
            return None

        key_path = settings.apns_key_path
        if not key_path or not key_path.exists():
            logger.error("APNs key file not found: %s", key_path)
            return None

        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

            with open(key_path, "rb") as f:
                private_key = load_pem_private_key(f.read(), password=None)

            def _b64url(data: bytes) -> str:
                return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

            header  = json.dumps({"alg": "ES256", "kid": settings.apns_key_id},
                                  separators=(",", ":"))
            payload = json.dumps({"iss": settings.apns_team_id, "iat": int(now)},
                                  separators=(",", ":"))

            h_enc = _b64url(header.encode())
            p_enc = _b64url(payload.encode())
            signing_input = f"{h_enc}.{p_enc}".encode()

            sig_der = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
            r, s = decode_dss_signature(sig_der)
            sig = _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

            self._jwt_token = f"{h_enc}.{p_enc}.{sig}"
            self._jwt_issued_at = now
            return self._jwt_token

        except Exception as exc:
            logger.error("APNs JWT generation failed: %s", exc)
            return None

    # ── Send ──────────────────────────────────────────────────────────────────

    async def send(self, payload: PushPayload) -> bool:
        """
        Send one push notification.  Returns True on success.
        Silently returns False if APNs is not configured.
        """
        token = self._build_apns_jwt()
        if not token:
            return False

        host = APNS_HOST_SANDBOX if settings.apns_use_sandbox else APNS_HOST_PROD
        url  = f"{host}/3/device/{payload.device_token}"

        apns_body: dict = {
            "aps": {
                "alert": {
                    "title": payload.title,
                    "body":  payload.body,
                },
                "sound": payload.sound,
            },
            **payload.data,
        }
        if payload.badge is not None:
            apns_body["aps"]["badge"] = payload.badge
        if payload.category:
            apns_body["aps"]["category"] = payload.category

        headers: dict = {
            "authorization":  f"bearer {token}",
            "apns-topic":     settings.apns_bundle_id,
            "apns-priority":  str(payload.priority),
            "apns-push-type": "alert",
            "content-type":   "application/json",
        }
        if payload.collapse_id:
            headers["apns-collapse-id"] = payload.collapse_id

        try:
            async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=apns_body)
                if resp.status_code == 200:
                    logger.debug(
                        "APNs send ok token=%s... title=%r", payload.device_token[:8], payload.title
                    )
                    return True
                logger.warning(
                    "APNs error status=%d body=%s token=%s...",
                    resp.status_code, resp.text[:200], payload.device_token[:8],
                )
                # 410 = device unregistered — remove from list
                if resp.status_code == 410:
                    self.unregister_device(payload.device_token)
                return False
        except Exception as exc:
            logger.error("APNs send exception: %s", exc)
            return False

    async def broadcast(
        self,
        title: str,
        body: str,
        category: str = "",
        data: Optional[dict] = None,
        badge: Optional[int] = None,
    ) -> dict:
        """Send a notification to all registered devices."""
        results: dict[str, bool] = {}
        for token in list(self._device_tokens):
            ok = await self.send(PushPayload(
                device_token=token,
                title=title,
                body=body,
                category=category,
                data=data or {},
                badge=badge,
            ))
            results[token[:8]] = ok
        sent = sum(1 for v in results.values() if v)
        logger.info("Broadcast sent=%d/%d title=%r", sent, len(results), title)
        return {"sent": sent, "total": len(results), "results": results}

    # ── Queue ─────────────────────────────────────────────────────────────────

    def enqueue(self, payload: PushPayload) -> None:
        """Add a notification to the retry queue."""
        self._queue.append(_QueuedNotification(payload=payload))

    async def process_queue(self) -> None:
        """Drain the pending notification queue (call from background task)."""
        now = time.time()
        remaining: list[_QueuedNotification] = []
        for item in self._queue:
            if item.next_attempt_at > now:
                remaining.append(item)
                continue
            ok = await self.send(item.payload)
            if not ok:
                item.attempts += 1
                if item.attempts < item.max_attempts:
                    item.next_attempt_at = now + (2 ** item.attempts) * 30  # exponential backoff
                    remaining.append(item)
                else:
                    logger.warning(
                        "Notification dropped after %d attempts title=%r",
                        item.attempts, item.payload.title,
                    )
        self._queue = remaining


# Singleton
notification_service = NotificationService()
