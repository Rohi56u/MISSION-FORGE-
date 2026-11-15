"""
Mission Forge Async Database Configuration
Provides SQLAlchemy 2.0 async engine, sessionmaker, and dependency injection.
"""

from typing import Any, AsyncGenerator, Dict, Tuple
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.app.core.config import settings


def build_engine_config(
    database_url: str,
    echo: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Constructs type-safe connect_args and engine kwargs tailored for the target dialect.
    Seamlessly supports local SQLite for development/CI and Supabase PostgreSQL
    (both session port 5432 and PgBouncer/Supavisor transaction pooler port 6543).
    """
    connect_args: Dict[str, Any] = {}
    engine_kwargs: Dict[str, Any] = {"echo": echo, "future": True}

    if "sqlite" in database_url:
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30.0
    elif "postgresql" in database_url or "asyncpg" in database_url:
        # PostgreSQL / Supabase asyncpg production configuration
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 300

        # Supabase transaction pooler (port 6543) requires statement caching disabled
        if ":6543" in database_url or "pooler" in database_url.lower():
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0

        # Supabase strictly mandates TLS/SSL for remote cloud connections
        if (
            "ssl=" not in database_url.lower()
            and "localhost" not in database_url
            and "127.0.0.1" not in database_url
        ):
            connect_args["ssl"] = "require"

    return connect_args, engine_kwargs


_connect_args, _engine_kwargs = build_engine_config(
    settings.DATABASE_URL,
    settings.DATABASE_ECHO,
)

# Engine setup
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enables SQLite WAL journal mode and busy timeout for safe concurrent access."""
    if "sqlite" in settings.DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an isolated async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Verifies database connectivity on application startup.
    In all environments, schema evolution must be managed via Alembic migrations.
    Never uses startup create_all() as a substitute for migration-based schema evolution.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
