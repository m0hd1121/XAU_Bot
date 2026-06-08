"""
routers/auth.py
────────────────
Authentication endpoints:

  POST /auth/login                — username + password (+ optional TOTP code)
  POST /auth/refresh              — exchange refresh token for new access token
  POST /auth/logout               — revoke refresh token
  POST /auth/logout-all           — revoke all refresh tokens for this user
  POST /auth/change-password      — change own password
  GET  /auth/2fa/setup            — generate TOTP secret + provisioning URI
  POST /auth/2fa/enable           — confirm TOTP code, activate 2FA
  POST /auth/2fa/disable          — deactivate 2FA (requires password + TOTP)
  POST /auth/biometric/register   — issue long-lived device-bound token
  POST /auth/biometric/login      — exchange biometric token for access+refresh pair
  POST /auth/biometric/revoke     — revoke biometric token for a device
  GET  /auth/me                   — current user profile
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import (
    TOKEN_TYPE_BIOMETRIC,
    TOKEN_TYPE_REFRESH,
    brute_force_tracker,
    create_access_token,
    create_biometric_token,
    create_refresh_token,
    decode_token,
    generate_totp_secret,
    get_current_user,
    get_totp_uri,
    hash_password,
    hash_token,
    token_expires_at,
    verify_password,
    verify_totp,
)
from app.config import settings
from app.database import get_db
from app.models.models import BiometricToken, RefreshToken, User

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)
    totp_code: Optional[str] = Field(None, min_length=6, max_length=8)
    device_name: Optional[str] = Field(None, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = settings.access_token_expire_minutes * 60
    user_id: int
    username: str
    role: str
    two_fa_enabled: bool


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12, max_length=256)


class Enable2FARequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=8)


class Disable2FARequest(BaseModel):
    password: str
    totp_code: str = Field(..., min_length=6, max_length=8)


class BiometricRegisterRequest(BaseModel):
    device_id: str = Field(..., max_length=256)
    device_name: Optional[str] = Field(None, max_length=128)


class BiometricLoginRequest(BaseModel):
    biometric_token: str
    device_id: str


class BiometricRevokeRequest(BaseModel):
    device_id: str


class UserProfile(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    two_fa_enabled: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    last_password_change: Optional[datetime] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _issue_token_pair(
    user: User,
    db: AsyncSession,
    request: Request,
    device_name: Optional[str] = None,
) -> TokenResponse:
    """Create access + refresh tokens, persist the refresh token hash, update last_login."""
    access = create_access_token(user.id, user.username, user.role)
    refresh = create_refresh_token(user.id, user.username)

    token_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh),
        device_name=device_name,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        expires_at=token_expires_at(TOKEN_TYPE_REFRESH),
    )
    db.add(token_row)
    await db.execute(
        update(User).where(User.id == user.id).values(
            last_login=datetime.now(tz=timezone.utc)
        )
    )
    await db.commit()

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        username=user.username,
        role=user.role,
        two_fa_enabled=user.two_fa_enabled,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse, summary="Authenticate and receive tokens")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    ip = _client_ip(request)
    lockout_key = f"login:{ip}:{body.username}"

    if brute_force_tracker.is_locked(lockout_key):
        remaining = brute_force_tracker.seconds_until_unlock(lockout_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Retry after {remaining}s.",
            headers={"Retry-After": str(remaining)},
        )

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        brute_force_tracker.record_failure(lockout_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    if user.two_fa_enabled:
        if not body.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP code required for this account",
                headers={"X-2FA-Required": "true"},
            )
        if not user.totp_secret or not verify_totp(user.totp_secret, body.totp_code):
            brute_force_tracker.record_failure(lockout_key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code",
            )

    brute_force_tracker.reset(lockout_key)
    logger.info("Login successful user=%s ip=%s", user.username, ip)
    return await _issue_token_pair(user, db, request, device_name=body.device_name)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access+refresh pair (token rotation)."""
    payload = decode_token(body.refresh_token, TOKEN_TYPE_REFRESH)
    user_id = int(payload["sub"])
    token_hash = hash_token(body.refresh_token)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,  # noqa: E712
        )
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or already revoked",
        )

    now = datetime.now(tz=timezone.utc)
    exp = stored.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has expired"
        )

    # Rotate: revoke the used token immediately
    stored.revoked = True
    stored.revoked_at = now
    await db.flush()

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled"
        )

    return await _issue_token_pair(user, db, request)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke refresh token")
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        decode_token(body.refresh_token, TOKEN_TYPE_REFRESH)
    except HTTPException:
        return  # Already invalid — idempotent success

    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored and not stored.revoked:
        stored.revoked = True
        stored.revoked_at = datetime.now(tz=timezone.utc)
        await db.commit()


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke all refresh tokens for this user",
)
async def logout_all(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked == False,  # noqa: E712
        )
    )
    tokens = result.scalars().all()
    now = datetime.now(tz=timezone.utc)
    for t in tokens:
        t.revoked = True
        t.revoked_at = now
    await db.commit()
    logger.info("All refresh tokens revoked user=%s count=%d", current_user.username, len(tokens))


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password",
)
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    await db.execute(
        update(User).where(User.id == current_user.id).values(
            hashed_password=hash_password(body.new_password),
            last_password_change=datetime.now(tz=timezone.utc),
        )
    )
    await db.commit()
    logger.info("Password changed user=%s", current_user.username)


@router.get("/2fa/setup", summary="Generate TOTP secret for 2FA provisioning")
async def setup_2fa(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.two_fa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled"
        )
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)
    await db.execute(
        update(User).where(User.id == current_user.id).values(totp_secret=secret)
    )
    await db.commit()
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "instructions": "Scan the URI with an authenticator app, then confirm via POST /auth/2fa/enable",
    }


@router.post(
    "/2fa/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Activate 2FA after verifying TOTP code",
)
async def enable_2fa(
    body: Enable2FARequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if current_user.two_fa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled"
        )
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call GET /auth/2fa/setup first to generate a secret",
        )
    if not verify_totp(current_user.totp_secret, body.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code"
        )
    await db.execute(
        update(User).where(User.id == current_user.id).values(two_fa_enabled=True)
    )
    await db.commit()
    logger.info("2FA enabled user=%s", current_user.username)


@router.post(
    "/2fa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable 2FA",
)
async def disable_2fa(
    body: Disable2FARequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not current_user.two_fa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not currently enabled"
        )
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password"
        )
    if not current_user.totp_secret or not verify_totp(current_user.totp_secret, body.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code"
        )
    await db.execute(
        update(User).where(User.id == current_user.id).values(
            two_fa_enabled=False, totp_secret=None
        )
    )
    await db.commit()
    logger.info("2FA disabled user=%s", current_user.username)


@router.post("/biometric/register", summary="Register device for biometric authentication")
async def biometric_register(
    body: BiometricRegisterRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Issues a long-lived device-bound token for Face ID / Touch ID login."""
    token = create_biometric_token(current_user.id, current_user.username, body.device_id)
    token_row = BiometricToken(
        user_id=current_user.id,
        token_hash=hash_token(token),
        device_id=body.device_id,
        device_name=body.device_name,
        expires_at=token_expires_at(TOKEN_TYPE_BIOMETRIC),
    )
    db.add(token_row)
    await db.commit()
    logger.info(
        "Biometric token issued user=%s device_id=%s", current_user.username, body.device_id
    )
    return {
        "biometric_token": token,
        "expires_in_days": settings.biometric_token_expire_days,
        "device_id": body.device_id,
    }


@router.post(
    "/biometric/login",
    response_model=TokenResponse,
    summary="Authenticate with biometric token",
)
async def biometric_login(
    body: BiometricLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        payload = decode_token(body.biometric_token, TOKEN_TYPE_BIOMETRIC)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired biometric token",
        )

    if payload.get("did") != body.device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Device ID mismatch"
        )

    token_hash = hash_token(body.biometric_token)
    result = await db.execute(
        select(BiometricToken).where(
            BiometricToken.token_hash == token_hash,
            BiometricToken.revoked == False,  # noqa: E712
        )
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Biometric token revoked or not found"
        )

    now = datetime.now(tz=timezone.utc)
    exp = stored.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Biometric token has expired"
        )

    user_result = await db.execute(select(User).where(User.id == stored.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled"
        )

    return await _issue_token_pair(user, db, request)


@router.post(
    "/biometric/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke biometric token for a specific device",
)
async def biometric_revoke(
    body: BiometricRevokeRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(BiometricToken).where(
            BiometricToken.user_id == current_user.id,
            BiometricToken.device_id == body.device_id,
            BiometricToken.revoked == False,  # noqa: E712
        )
    )
    tokens = result.scalars().all()
    for t in tokens:
        t.revoked = True
    await db.commit()


@router.get("/me", response_model=UserProfile, summary="Current user profile")
async def get_me(current_user=Depends(get_current_user)) -> UserProfile:
    return UserProfile(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
        two_fa_enabled=current_user.two_fa_enabled,
        created_at=current_user.created_at,
        last_login=current_user.last_login,
        last_password_change=current_user.last_password_change,
    )
