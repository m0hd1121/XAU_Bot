"""
config.py
─────────
Application-wide settings loaded from environment variables with sane defaults.
All secrets MUST be supplied via environment — never hard-coded here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Server ────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    debug: bool = False
    environment: str = "production"   # "development" | "production"

    # ── Security ──────────────────────────────────────────────────────────────
    # Generate with: openssl rand -hex 32
    secret_key: str = "CHANGE_ME_use_openssl_rand_hex_32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    biometric_token_expire_days: int = 90
    # Pepper applied to passwords before bcrypt (extra defence-in-depth)
    password_pepper: str = "CHANGE_ME_password_pepper"

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins
    cors_origins: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:////home/user/XAU_Bot/backend/data/api.db"

    # ── XAU Bot paths ─────────────────────────────────────────────────────────
    bot_root: Path = Path("/home/user/XAU_Bot")
    bot_config_path: Path = Path("/home/user/XAU_Bot/config.yaml")
    bot_learning_db: Path = Path("/home/user/XAU_Bot/data/learning.db")
    bot_log_file: Path = Path("/home/user/XAU_Bot/logs/xau_bot.log")
    bot_trades_csv: Path = Path("/home/user/XAU_Bot/logs/trades.csv")
    bot_pid_file: Path = Path("/home/user/XAU_Bot/bot.pid")
    bot_main_script: Path = Path("/home/user/XAU_Bot/main.py")
    bot_venv_python: Path = Path("/home/user/XAU_Bot/venv/bin/python")

    # ── Systemd service names ─────────────────────────────────────────────────
    bot_service_name: str = "xaubot"
    api_service_name: str = "xaubot-api"
    worker_service_name: str = "xaubot-worker"

    # ── Backup ────────────────────────────────────────────────────────────────
    backup_dir: Path = Path("/home/user/XAU_Bot/backend/backups")
    max_backups_to_keep: int = 20

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_general: int = 60      # requests per minute
    rate_limit_auth: int = 5          # requests per minute for /auth/*
    rate_limit_window_seconds: int = 60

    # ── Brute-force lockout ───────────────────────────────────────────────────
    max_login_attempts: int = 5
    lockout_duration_seconds: int = 900   # 15 minutes

    # ── APNs (Apple Push Notifications) ──────────────────────────────────────
    apns_key_id: Optional[str] = None
    apns_team_id: Optional[str] = None
    apns_bundle_id: str = "com.xaubot.app"
    apns_key_path: Optional[Path] = None
    apns_use_sandbox: bool = False

    # ── Redis (optional — falls back to in-memory if not configured) ──────────
    redis_url: Optional[str] = None   # e.g. "redis://localhost:6379/0"

    # ── Admin bootstrap ───────────────────────────────────────────────────────
    initial_admin_username: str = "admin"
    initial_admin_password: str = "CHANGE_ME_admin_password"

    # ── WebSocket ─────────────────────────────────────────────────────────────
    ws_dashboard_interval_seconds: float = 1.0
    ws_trades_interval_seconds: float = 5.0
    ws_max_connections: int = 10

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    api_log_file: Path = Path("/home/user/XAU_Bot/backend/logs/api.log")

    # ── Compatibility aliases ─────────────────────────────────────────────────
    # Some older code references settings.bot_dir and settings.apns_sandbox

    @property
    def bot_dir(self) -> Path:
        """Alias for bot_root — backward compatibility."""
        return self.bot_root

    @property
    def apns_sandbox(self) -> bool:
        """Alias for apns_use_sandbox — backward compatibility."""
        return self.apns_use_sandbox

    @model_validator(mode="after")
    def _create_directories(self) -> "Settings":
        """Ensure required directories exist at startup."""
        for directory in [
            self.backup_dir,
            self.api_log_file.parent,
            Path(self.database_url.replace("sqlite+aiosqlite:///", "")).parent,
        ]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass  # Best effort; may be a non-path string for non-SQLite DBs
        return self

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper


# Single shared instance — import this everywhere
settings = Settings()
