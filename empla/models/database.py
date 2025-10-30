"""
empla.models.database - Database Configuration

Provides database connection and session management:
- get_engine: Create SQLAlchemy async engine
- get_sessionmaker: Create async session factory
- get_db: Async context manager for database sessions
- init_db: Initialize database (create tables)
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from empla.models.base import Base


def get_database_url() -> str:
    """
    Get database URL from environment.

    Defaults to local PostgreSQL if not set.
    """
    return os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/empla_dev")


def get_engine(database_url: str | None = None, echo: bool = False) -> AsyncEngine:
    """
    Create SQLAlchemy async engine.

    Args:
        database_url: Database connection string (uses env var if not provided)
        echo: Whether to echo SQL queries (useful for debugging)

    Returns:
        AsyncEngine configured for PostgreSQL with asyncpg
    """
    url = database_url or get_database_url()

    # Create async engine
    engine = create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=10,  # Connection pool size
        max_overflow=20,  # Max overflow connections
    )

    return engine


def get_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create async session factory.

    Args:
        engine: SQLAlchemy async engine

    Returns:
        async_sessionmaker for creating database sessions
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Don't expire objects after commit
    )


@asynccontextmanager
async def get_db(
    database_url: str | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session (async context manager).

    Usage:
        >>> async with get_db() as db:
        ...     employees = await db.execute(select(Employee))
        ...     await db.commit()

    Args:
        database_url: Database connection string (uses env var if not provided)

    Yields:
        AsyncSession for database operations
    """
    engine = get_engine(database_url)
    sessionmaker = get_sessionmaker(engine)

    async with sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()
            # Dispose engine to prevent connection pool leaks
            await engine.dispose()


async def init_db(database_url: str | None = None) -> None:
    """
    Initialize database (create all tables).

    This should only be used in development/testing.
    In production, use Alembic migrations.

    Args:
        database_url: Database connection string (uses env var if not provided)
    """
    engine = get_engine(database_url)

    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()


async def drop_db(database_url: str | None = None) -> None:
    """
    Drop all tables.

    **WARNING:** This will delete all data!
    Only use in development/testing.

    Args:
        database_url: Database connection string (uses env var if not provided)
    """
    engine = get_engine(database_url)

    async with engine.begin() as conn:
        # Drop all tables
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
