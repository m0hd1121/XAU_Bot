"""
Routers package.  Each module exposes an `router` APIRouter instance.
Imported and mounted in app/main.py.
"""
from app.routers import (
    analytics,
    auth,
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

__all__ = [
    "analytics",
    "auth",
    "backup",
    "bot_control",
    "config_router",
    "dashboard",
    "learning",
    "logs",
    "notifications",
    "trades",
    "vps",
]
