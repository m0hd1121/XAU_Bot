"""
auth/security.py
────────────────
Security primitives for the XAU Bot API:

  • JWT access tokens (short-lived, 15 min default)
  • JWT refresh tokens (long-lived, stored as hashed value in DB)
  • JWT biometric tokens (device-bound, 90-day)
  • bcrypt password hashing with per-installation pepper
  • TOTP / 2FA helpers via pyotp
  • Brute-force lockout tracker (in-memory dict with optional Redis backend)
  • FastAPI dependency get_current_user
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────────

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash password with bcrypt after applying the global pepper."""
    peppered = _apply_pepper(plain)
    return _pwd_ctx.hash(peppered)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against its stored bcrypt hash."""
    peppered = _apply_pepper(plain)
    return _pwd_ctx.verify(peppered, hashed)


def _apply_pepper(plain: str) -> str:
    """
    HMAC-SHA256 the password with the server-side pepper before bcrypt.
    This means even a leaked DB hash is useless without the pepper secret.
    """
    return hmac.new(
        settings.password_pepper.encode(),
        plain.encode(),
        hashlib.sha256,
    ).hexdigest()


# ── JWT token helpers ─────────────────────────────────────────────────────────

_ALGORITHM = settings.jwt_algorithm
_SECRET    = settings.secret_key

TOKEN_TYPE_ACCESS    = "access"
TOKEN_TYPE_REFRESH   = "refresh"
TOKEN_TYPE_BIOMETRIC = "biometric"


def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub":  str(user_id),
        "usr":  username,
        "role": role,
        "typ":  TOKEN_TYPE_ACCESS,
        "exp":  expire,
        "iat":  datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(user_id: int, username: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub":  str(user_id),
        "usr":  username,
        "typ":  TOKEN_TYPE_REFRESH,
        "exp":  expire,
        "iat":  datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_biometric_token(user_id: int, username: str, device_id: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(
        days=settings.biometric_token_expire_days
    )
    payload = {
        "sub":  str(user_id),
        "usr":  username,
        "did":  device_id,
        "typ":  TOKEN_TYPE_BIOMETRIC,
        "exp":  expire,
        "iat":  datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    """
    Decode and validate a JWT.  Raises HTTPException on any failure.
    Returns the decoded payload dict.
    """
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("typ") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token type mismatch: expected {expected_type}",
        )
    return payload


def hash_token(token: str) -> str:
    """
    Store only the SHA-256 hash of a refresh/biometric token in the DB.
    This means a stolen DB row cannot be replayed without the original token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def token_expires_at(token_type: str) -> datetime:
    """Return the expiry datetime for a given token type."""
    now = datetime.now(tz=timezone.utc)
    if token_type == TOKEN_TYPE_REFRESH:
        return now + timedelta(days=settings.refresh_token_expire_days)
    if token_type == TOKEN_TYPE_BIOMETRIC:
        return now + timedelta(days=settings.biometric_token_expire_days)
    return now + timedelta(minutes=settings.access_token_expire_minutes)


# ── TOTP / 2FA ────────────────────────────────────────────────────────────────

def generate_totp_secret() -> str:
    """Generate a random base32 TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """Return the otpauth:// URI for QR code provisioning."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name="XAUBot")


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code.  Allows ±1 window (30 s drift tolerance)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ── Brute-force lockout tracker ───────────────────────────────────────────────

class BruteForceTracker:
    """
    Sliding-window in-memory brute-force tracker.

    Falls back to Redis if settings.redis_url is configured, which
    allows multiple API workers to share lockout state.

    Data structure (in-memory):
      _attempts: {key: [(timestamp, ...), ...]}
      _lockouts:  {key: locked_until_timestamp}
    """

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lockouts: dict[str, float] = {}
        self._redis = None
        self._try_redis()

    def _try_redis(self) -> None:
        if not settings.redis_url:
            return
        try:
            import redis as _redis
            client = _redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            logger.info("BruteForceTracker: using Redis backend at %s", settings.redis_url)
        except Exception as exc:
            logger.warning("BruteForceTracker: Redis unavailable (%s), using in-memory", exc)

    def record_failure(self, key: str) -> None:
        """Record a failed auth attempt.  Locks the key after max_attempts."""
        now = time.time()
        window = settings.rate_limit_window_seconds

        if self._redis:
            redis_key = f"bf:attempts:{key}"
            pipe = self._redis.pipeline()
            pipe.rpush(redis_key, now)
            pipe.expire(redis_key, window)
            pipe.execute()
            count = self._redis.llen(redis_key)
            if count >= settings.max_login_attempts:
                lock_key = f"bf:lockout:{key}"
                self._redis.setex(lock_key, settings.lockout_duration_seconds, "1")
        else:
            attempts = self._attempts[key]
            attempts.append(now)
            # Prune attempts outside the current window
            self._attempts[key] = [t for t in attempts if now - t < window]
            if len(self._attempts[key]) >= settings.max_login_attempts:
                self._lockouts[key] = now + settings.lockout_duration_seconds

    def is_locked(self, key: str) -> bool:
        """Return True if the key is currently locked out."""
        now = time.time()
        if self._redis:
            return bool(self._redis.exists(f"bf:lockout:{key}"))
        locked_until = self._lockouts.get(key, 0)
        if locked_until > now:
            return True
        if key in self._lockouts:
            del self._lockouts[key]
        return False

    def reset(self, key: str) -> None:
        """Clear lockout and attempt history on successful authentication."""
        if self._redis:
            self._redis.delete(f"bf:attempts:{key}", f"bf:lockout:{key}")
        else:
            self._attempts.pop(key, None)
            self._lockouts.pop(key, None)

    def seconds_until_unlock(self, key: str) -> int:
        """Remaining lockout seconds, or 0 if not locked."""
        if self._redis:
            ttl = self._redis.ttl(f"bf:lockout:{key}")
            return max(0, ttl)
        now = time.time()
        locked_until = self._lockouts.get(key, 0)
        return max(0, int(locked_until - now))


# Single shared instance used by the auth router
brute_force_tracker = BruteForceTracker()


# ── FastAPI security dependency ───────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency: validates the Bearer access token and returns the User ORM object.
    Raises 401 if missing, expired, or the user account is inactive.
    """
    from app.models.models import User  # local import to avoid circular deps

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    user_id = int(payload["sub"])

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    return user


async def require_admin(user=Depends(get_current_user)):
    """Dependency: current user must have role 'admin'."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


async def require_operator(user=Depends(get_current_user)):
    """Dependency: current user must have role 'admin' or 'operator'."""
    if user.role not in ("admin", "operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator role required",
        )
    return user
