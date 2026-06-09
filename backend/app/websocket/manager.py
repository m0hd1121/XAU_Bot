"""
websocket/manager.py
─────────────────────
WebSocket connection manager and background data streaming worker.

Features:
  • Per-client connection registry keyed by connection UUID
  • JWT token validation on WebSocket handshake (via ?token= query param)
  • Graceful disconnection handling and dead-connection pruning
  • Background asyncio tasks:
    - Dashboard snapshots broadcast to all clients every 1 second
    - Open trade updates broadcast every 5 seconds
  • Hard limit on simultaneous connections (settings.ws_max_connections)
  • Configurable intervals via settings

WebSocket endpoints exposed via ws_router:
  WS /ws/live     — authenticated live feed (dashboard + trades)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

logger = logging.getLogger(__name__)

ws_router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_message(msg_type: str, data: Any) -> str:
    """Wrap data in the standard message envelope."""
    return json.dumps(
        {
            "type": msg_type,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "payload": data,
        },
        default=str,
    )


# ── Client ────────────────────────────────────────────────────────────────────

class _Client:
    def __init__(self, ws: WebSocket, user_id: int, username: str) -> None:
        self.ws = ws
        self.user_id = user_id
        self.username = username
        self.conn_id = str(uuid.uuid4())
        self.connected_at = datetime.now(tz=timezone.utc)

    async def send(self, message: str) -> bool:
        """Returns False if the connection has dropped."""
        try:
            await self.ws.send_text(message)
            return True
        except Exception:
            return False


# ── Manager ───────────────────────────────────────────────────────────────────

class WebSocketManager:
    """Central registry and broadcaster for all connected WebSocket clients."""

    def __init__(self) -> None:
        self._clients: dict[str, _Client] = {}
        self._task_dashboard: Optional[asyncio.Task] = None
        self._task_trades: Optional[asyncio.Task] = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start_background_tasks(self) -> None:
        if self._running:
            return
        self._running = True
        self._task_dashboard = asyncio.create_task(
            self._dashboard_loop(), name="ws-dashboard"
        )
        self._task_trades = asyncio.create_task(
            self._trades_loop(), name="ws-trades"
        )
        logger.info(
            "WebSocket background tasks started (dashboard=%.1fs trades=%.1fs)",
            settings.ws_dashboard_interval_seconds,
            settings.ws_trades_interval_seconds,
        )

    async def shutdown(self) -> None:
        self._running = False
        for task in (self._task_dashboard, self._task_trades):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        for client in list(self._clients.values()):
            try:
                await client.ws.close(code=1001)
            except Exception:
                pass
        self._clients.clear()
        logger.info("WebSocket manager shut down cleanly")

    # ── Connection management ─────────────────────────────────────────────────

    async def connect(self, ws: WebSocket, user_id: int, username: str) -> _Client:
        if len(self._clients) >= settings.ws_max_connections:
            await ws.close(code=1013, reason="Server at capacity")
            raise ConnectionError("WebSocket capacity reached")
        await ws.accept()
        client = _Client(ws, user_id, username)
        self._clients[client.conn_id] = client
        logger.info(
            "WS connected conn=%s user=%s total=%d",
            client.conn_id[:8], username, len(self._clients),
        )
        return client

    def disconnect(self, conn_id: str) -> None:
        client = self._clients.pop(conn_id, None)
        if client:
            logger.info(
                "WS disconnected conn=%s user=%s total=%d",
                conn_id[:8], client.username, len(self._clients),
            )

    async def broadcast(self, message: str) -> None:
        """Send to all connected clients, pruning dead connections."""
        dead: list[str] = []
        for conn_id, client in list(self._clients.items()):
            if not await client.send(message):
                dead.append(conn_id)
        for conn_id in dead:
            self.disconnect(conn_id)

    async def send_to_user(self, user_id: int, message: str) -> None:
        dead: list[str] = []
        for conn_id, client in list(self._clients.items()):
            if client.user_id == user_id:
                if not await client.send(message):
                    dead.append(conn_id)
        for conn_id in dead:
            self.disconnect(conn_id)

    # ── Background loops ──────────────────────────────────────────────────────

    async def _dashboard_loop(self) -> None:
        from app.services.bot_service import bot_service

        while self._running:
            try:
                if self._clients:
                    snapshot = await bot_service.get_dashboard_snapshot()
                    msg = _make_message("dashboard", snapshot)
                    await self.broadcast(msg)
            except Exception as exc:
                logger.debug("Dashboard broadcast error: %s", exc)
            await asyncio.sleep(settings.ws_dashboard_interval_seconds)

    async def _trades_loop(self) -> None:
        from app.services.bot_service import bot_service

        while self._running:
            try:
                if self._clients:
                    trades = bot_service.get_open_trades()
                    msg = _make_message("open_trades", {
                        "trades": trades,
                        "count": len(trades),
                    })
                    await self.broadcast(msg)
            except Exception as exc:
                logger.debug("Trades broadcast error: %s", exc)
            await asyncio.sleep(settings.ws_trades_interval_seconds)


# Singleton
ws_manager = WebSocketManager()


# ── Authentication helper ─────────────────────────────────────────────────────

async def _authenticate_ws(websocket: WebSocket) -> tuple[int, str]:
    """
    Validate the Bearer token in the ?token= query string.
    Raises ValueError (after closing the socket) if invalid.
    Returns (user_id, username).
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        raise ValueError("Missing token")
    try:
        from app.auth.security import decode_token, TOKEN_TYPE_ACCESS
        payload = decode_token(token, TOKEN_TYPE_ACCESS)
        return int(payload["sub"]), payload.get("usr", "unknown")
    except Exception as exc:
        await websocket.close(code=4001, reason="Invalid token")
        raise ValueError(f"Token rejected: {exc}") from exc


# ── Auth via first message (iOS client sends {"type":"auth","token":"..."}) ────

async def _authenticate_ws_message(websocket: WebSocket) -> tuple[int, str]:
    """
    Accept the WebSocket first, then wait up to 10 s for a JSON auth message.
    iOS sends: {"type": "auth", "token": "<access_token>"}
    """
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        msg = json.loads(raw)
        if msg.get("type") != "auth":
            await websocket.close(code=4001, reason="Expected auth message")
            raise ValueError("Expected auth message")
        token = msg.get("token", "")
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            raise ValueError("Missing token")
        from app.auth.security import decode_token, TOKEN_TYPE_ACCESS
        payload = decode_token(token, TOKEN_TYPE_ACCESS)
        return int(payload["sub"]), payload.get("usr", "unknown")
    except (asyncio.TimeoutError, json.JSONDecodeError, KeyError) as exc:
        await websocket.close(code=4001, reason="Auth failed")
        raise ValueError(f"Auth failed: {exc}") from exc


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@ws_router.websocket("/dashboard")
async def dashboard_feed(websocket: WebSocket) -> None:
    """
    iOS app connects here: wss://host/api/v1/ws/dashboard
    Auth via first JSON message: {"type":"auth","token":"<access_token>"}
    """
    client = None
    try:
        user_id, username = await _authenticate_ws_message(websocket)
    except ValueError:
        return

    try:
        client = await ws_manager.connect(websocket, user_id, username)

        from app.services.bot_service import bot_service
        try:
            snapshot = await asyncio.wait_for(bot_service.get_dashboard_snapshot(), timeout=5)
            await client.send(_make_message("dashboard", snapshot))
        except Exception:
            pass

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "ping":
                    await client.send(_make_message("pong", {"client_ts": msg.get("ts")}))
            except asyncio.TimeoutError:
                ok = await client.send(_make_message("ping", {}))
                if not ok:
                    break
            except (WebSocketDisconnect, Exception):
                break
    except Exception as exc:
        logger.debug("WS /dashboard exception: %s", exc)
    finally:
        if client:
            ws_manager.disconnect(client.conn_id)


@ws_router.websocket("/live")
async def live_feed(websocket: WebSocket) -> None:
    """
    Authenticated WebSocket endpoint for live data streaming.

    Connection: wss://host/api/v1/ws/live?token=<access_token>

    Server-sent message types:
      • dashboard    — AccountSnapshot dict, every 1 s
      • open_trades  — open trade list, every 5 s
      • pong         — keepalive response
      • ping         — server-initiated keepalive (when client is silent 30 s)

    Client-sent message types:
      • ping  — keepalive (server responds with pong)
    """
    try:
        user_id, username = await _authenticate_ws(websocket)
    except ValueError:
        return

    client = None
    try:
        client = await ws_manager.connect(websocket, user_id, username)

        # Push an immediate snapshot on connect
        from app.services.bot_service import bot_service
        snapshot = await bot_service.get_dashboard_snapshot()
        await client.send(_make_message("dashboard", snapshot))

        # Message pump
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "ping":
                    await client.send(_make_message("pong", {"client_ts": msg.get("ts")}))
            except asyncio.TimeoutError:
                # No message in 30 s — send keepalive
                ok = await client.send(_make_message("ping", {}))
                if not ok:
                    break
            except WebSocketDisconnect:
                break
            except Exception:
                break
    except Exception as exc:
        logger.debug(
            "WS handler exception conn=%s: %s",
            client.conn_id[:8] if client else "?",
            exc,
        )
    finally:
        if client:
            ws_manager.disconnect(client.conn_id)
