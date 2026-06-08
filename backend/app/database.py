"""
database.py
───────────
Async SQLAlchemy engine and session factory for the API's own SQLite database.
(Separate from the bot's learning.db — this stores users, tokens, audit logs, etc.)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text

from app.config import settings

logger = logging.getLogger(__name__)


# ── Base class for all models ─────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Engine ────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={
        "check_same_thread": False,   # Required for SQLite
        "timeout": 15,
    },
    pool_pre_ping=True,
)


# Enable WAL mode and foreign keys for every new connection
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA cache_size=-32000")   # 32 MB page cache
    cursor.close()


# ── Session factory ───────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── Dependency for FastAPI routes ─────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session and closes it afterward."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Database initialisation ───────────────────────────────────────────────────

async def init_db() -> None:
    """
    Create all tables (idempotent).  Called once at application startup.
    Also creates the initial admin user if the users table is empty.
    """
    from app.models.models import Base as ModelBase  # noqa: F401 — registers metadata

    async with engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)

    logger.info("Database tables verified/created: %s", settings.database_url)

    await _bootstrap_admin()


async def _bootstrap_admin() -> None:
    """Create the initial admin user if no users exist yet."""
    from app.models.models import User
    from app.auth.security import hash_password
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # Users already exist

        admin = User(
            username=settings.initial_admin_username,
            hashed_password=hash_password(settings.initial_admin_password),
            role="admin",
            is_active=True,
            two_fa_enabled=False,
        )
        session.add(admin)
        await session.commit()
        logger.warning(
            "Bootstrap: created initial admin user '%s'. "
            "Change the password immediately via /auth/change-password.",
            settings.initial_admin_username,
        )


@asynccontextmanager
async def db_session():
    """Context manager version of get_db for non-request code paths."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
