"""
models.py
─────────
SQLAlchemy ORM models for the API's own database.

Tables:
  • User          — API user accounts (admin + readonly roles)
  • RefreshToken  — persistent refresh token store
  • BiometricToken — long-lived device-bound tokens for iOS biometric auth
  • AuditLog      — immutable log of every mutating API action
  • Notification  — push notification records
  • BotState      — bot runtime state snapshots (latest wins)
  • BackupRecord  — metadata for created backups
  • APNSDevice    — registered iOS device tokens
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── User ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="readonly")
    # "admin" | "operator" | "readonly"

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    two_fa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_password_change: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    biometric_tokens: Mapped[list["BiometricToken"]] = relationship(
        "BiometricToken", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


# ── RefreshToken ──────────────────────────────────────────────────────────────

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_rt_user_revoked", "user_id", "revoked"),
    )


# ── BiometricToken ────────────────────────────────────────────────────────────

class BiometricToken(Base):
    """Long-lived device-bound token used by iOS biometric auth (Face ID / Touch ID)."""
    __tablename__ = "biometric_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(256), nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship("User", back_populates="biometric_tokens")


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable append-only log of every state-changing API call.
    Rows are never updated or deleted (only insert).
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_al_user_ts", "user_id", "timestamp"),
        Index("ix_al_action_ts", "action", "timestamp"),
    )


# ── Notification ──────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    # "trade_opened" | "trade_closed" | "bot_stopped" | "drawdown_alert" |
    # "daily_summary" | "error" | "general"
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    # "high" | "normal" | "low"
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    apns_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


# ── BotState ──────────────────────────────────────────────────────────────────

class BotState(Base):
    """Latest known state of the trading bot (upserted by the background worker)."""
    __tablename__ = "bot_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # There is always exactly one row (id=1); we upsert it.
    running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_stopped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    learning_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="backtest")
    # "backtest" | "paper" | "live"
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_trade_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    open_trades_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ── BackupRecord ──────────────────────────────────────────────────────────────

class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    includes_db: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    includes_config: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    includes_logs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


# ── APNSDevice ────────────────────────────────────────────────────────────────

class APNSDevice(Base):
    """Registered iOS device push tokens."""
    __tablename__ = "apns_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_token: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Notification preferences stored as JSON
    preferences_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
