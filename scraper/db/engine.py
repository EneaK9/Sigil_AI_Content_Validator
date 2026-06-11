"""Async SQLAlchemy engine / session factory for Supabase Postgres.

Bulk writes go straight to Postgres via asyncpg (never PostREST/supabase-py).
The connection string should be the Supabase *session pooler* URL in the
SQLAlchemy asyncpg form::

    postgresql+asyncpg://postgres.<ref>:<password>@<host>:5432/postgres

Pooler note: Supabase's pooler (pgbouncer) does not support server-side
prepared statements reliably across pooled connections, so we disable asyncpg's
prepared-statement cache. Without this you get "prepared statement does not
exist" / duplicate-name errors under load.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from scraper.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.supabase_db_url,
            pool_pre_ping=True,
            pool_size=settings.max_concurrent_runs + 2,
            max_overflow=4,
            connect_args={
                # pgbouncer / pooler compatibility: no named prepared statements.
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional session context: commits on success, rolls back on error."""
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine (call on graceful shutdown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
