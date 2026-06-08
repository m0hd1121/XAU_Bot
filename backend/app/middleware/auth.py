"""
middleware/auth.py
──────────────────
Re-exports FastAPI auth dependencies from app.auth.security.
Kept as a compatibility shim so existing routers that import from
app.middleware.auth continue to work.
"""
from __future__ import annotations

# Re-export from canonical location
from app.auth.security import (
    get_current_user,
    require_admin,
    require_operator,
    decode_token as decode_access_token,
)

__all__ = ["get_current_user", "require_admin", "require_operator", "decode_access_token"]
