"""
main.py
───────
FastAPI application entry point for the XAU Bot Control API.

Features:
  • Async SQLite via SQLAlchemy (separate from the bot's learning.db)
  • JWT auth with refresh tokens + optional TOTP 2FA
  • WebSocket live dashboard / trade feed
  • Full audit logging middleware for every mutating request
  • Sliding-window rate limiting (60 req/min general, 5 req/min auth)
  • All routers mounted under /api/v1
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db


# ── Structured logging setup ──────────────────────────────────────────────────

def _configure_logging() -> None:
    log_level = getattr(logging, settings.log_level, logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    # Also write to file (best-effort — skip if path is missing or unwritable)
    if settings.api_log_file:
        try:
            file_handler = logging.FileHandler(str(settings.api_log_file))
            file_handler.setLevel(log_level)
            logging.getLogger().addHandler(file_handler)
        except OSError:
            pass


_configure_logging()
logger = structlog.get_logger(__name__)


# ── Application lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("XAU Bot API starting up", version="1.0.0", environment=settings.environment)

    # Initialise the API database (create tables, bootstrap admin user)
    await init_db()

    # Start the WebSocket background worker
    from app.websocket.manager import ws_manager
    await ws_manager.start_background_tasks()

    logger.info("Startup complete", host=settings.api_host, port=settings.api_port)
    yield

    # Graceful shutdown
    await ws_manager.shutdown()
    logger.info("XAU Bot API shut down cleanly")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="XAU Bot Control API",
    description="Control and monitor the XAU/USD price-action trading bot from iOS.",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)


# ── Middleware stack (order matters — outermost registered first) ──────────────

# GZip compression for large responses
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS — restrict to configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Device-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "Retry-After"],
)

# Rate limiting
from app.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Audit logging (must be after auth so we can capture user identity)
from app.middleware.audit import AuditMiddleware
app.add_middleware(AuditMiddleware)


# ── Request ID injection ──────────────────────────────────────────────────────

@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    """Attach a unique request ID to every request for correlation in logs."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", path=str(request.url), exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

from app.routers import (
    account,
    auth,
    analytics,
    backup,
    bot_control,
    config_router,
    dashboard,
    learning,
    logs,
    notifications,
    trades,
    vps,
)
from app.routers.agents import router as agents_router
from app.websocket.manager import ws_router

API_PREFIX = "/api/v1"

app.include_router(auth.router,         prefix=f"{API_PREFIX}/auth",          tags=["Authentication"])
app.include_router(account.router,      prefix=f"{API_PREFIX}/account",       tags=["Account"])
app.include_router(dashboard.router,    prefix=f"{API_PREFIX}/dashboard",      tags=["Dashboard"])
app.include_router(bot_control.router,  prefix=f"{API_PREFIX}/bot",            tags=["Bot Control"])
app.include_router(trades.router,       prefix=f"{API_PREFIX}/trades",         tags=["Trades"])
app.include_router(config_router.router,prefix=f"{API_PREFIX}/config",         tags=["Configuration"])
app.include_router(analytics.router,    prefix=f"{API_PREFIX}/analytics",      tags=["Analytics"])
app.include_router(learning.router,     prefix=f"{API_PREFIX}/learning",       tags=["Learning Engine"])
app.include_router(vps.router,          prefix=f"{API_PREFIX}/vps",            tags=["VPS"])
app.include_router(logs.router,         prefix=f"{API_PREFIX}/logs",           tags=["Logs"])
app.include_router(backup.router,       prefix=f"{API_PREFIX}/backups",        tags=["Backup"])
app.include_router(notifications.router,prefix=f"{API_PREFIX}/notifications",  tags=["Notifications"])
app.include_router(agents_router,       prefix=f"{API_PREFIX}",                tags=["Agents"])
app.include_router(ws_router,           prefix=f"{API_PREFIX}/ws",             tags=["WebSocket"])


# ── Health check (unauthenticated) ────────────────────────────────────────────

@app.get("/health", tags=["Health"], include_in_schema=False)
async def health_check() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.get(f"{API_PREFIX}/health", tags=["Health"])
async def api_health_check() -> dict:
    """Authenticated health check endpoint — confirms the API is alive."""
    from app.services.bot_service import bot_service
    bot_alive = await bot_service.is_bot_running()
    return {
        "status": "ok",
        "version": "1.0.0",
        "bot_running": bot_alive,
        "environment": settings.environment,
    }
