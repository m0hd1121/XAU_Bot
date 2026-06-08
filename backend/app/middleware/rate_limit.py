"""
rate_limit.py
─────────────
Sliding-window in-memory rate limiter middleware.

Limits:
  • Auth endpoints  — 5 requests / 60 s
  • All other       — 60 requests / 60 s

Returns 429 with Retry-After header when limit exceeded.
Identifies clients by IP; falls back to a global bucket if behind a proxy.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


_AUTH_LIMIT    = 5
_GENERAL_LIMIT = 60
_WINDOW_SEC    = 60


class _Bucket:
    """Sliding-window counter for one (client, endpoint_type) pair."""

    def __init__(self, limit: int, window: int) -> None:
        self._limit  = limit
        self._window = window
        self._hits:  Deque[float] = deque()

    def allow(self) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        # Evict old timestamps
        cutoff = now - self._window
        while self._hits and self._hits[0] < cutoff:
            self._hits.popleft()

        if len(self._hits) >= self._limit:
            oldest = self._hits[0]
            retry_after = int(oldest + self._window - now) + 1
            return False, retry_after

        self._hits.append(now)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):

    def __init__(self, app) -> None:
        super().__init__(app)
        self._auth_buckets:    dict[str, _Bucket] = defaultdict(lambda: _Bucket(_AUTH_LIMIT,    _WINDOW_SEC))
        self._general_buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(_GENERAL_LIMIT, _WINDOW_SEC))

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip WebSocket upgrades and health check
        if request.url.path in ("/health", "/") or "upgrade" in request.headers.get("connection", "").lower():
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_auth   = "/auth/" in request.url.path

        bucket  = self._auth_buckets[client_ip] if is_auth else self._general_buckets[client_ip]
        allowed, retry_after = bucket.allow()

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(_AUTH_LIMIT if is_auth else _GENERAL_LIMIT),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
