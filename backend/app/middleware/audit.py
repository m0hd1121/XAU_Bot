"""
audit.py
────────
Middleware that records every state-mutating HTTP request (POST, PUT,
DELETE, PATCH) to the AuditLog table.

Captured fields:
  • user_id (extracted from verified JWT)
  • client IP
  • HTTP method + path
  • SHA-256 of request body (so payload is never stored in plain text)
  • HTTP status code of response
  • Timestamp
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.database import AsyncSessionLocal
from app.models.models import AuditLog

logger = structlog.get_logger(__name__)

_MUTATING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class AuditMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        # Skip WebSocket upgrades
        if "upgrade" in request.headers.get("connection", "").lower():
            return await call_next(request)

        user_id  = await self._extract_user_id(request)
        client_ip = self._get_client_ip(request)

        # Consume and cache body so the route can also read it
        body_bytes = await request.body()
        body_hash  = hashlib.sha256(body_bytes).hexdigest() if body_bytes else None

        # Restore body for downstream handlers — signal disconnect after first read
        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.disconnect"}

        request._receive = receive  # type: ignore[attr-defined]

        t0       = time.monotonic()
        response = await call_next(request)
        elapsed  = int((time.monotonic() - t0) * 1000)

        try:
            async with AsyncSessionLocal() as db:
                entry = AuditLog(
                    user_id    = user_id,
                    client_ip  = client_ip,
                    method     = request.method,
                    path       = str(request.url.path),
                    body_hash  = body_hash,
                    status_code= response.status_code,
                    elapsed_ms = elapsed,
                )
                db.add(entry)
                await db.commit()
        except Exception as exc:
            logger.warning("AuditMiddleware: failed to write audit log", exc=str(exc))

        return response

    @staticmethod
    async def _extract_user_id(request: Request) -> Optional[str]:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:]
        try:
            from app.auth.security import decode_access_token
            payload = decode_access_token(token)
            return payload.get("sub")
        except Exception:
            return None

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
