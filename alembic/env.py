"""
Alembic environment configuration for empla.

Supports async SQLAlchemy with asyncpg driver.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import models to ensure they're registered with Base.metadata
from empla.models import Base
from empla.models.activity import EmployeeActivity  # noqa: F401
from empla.models.audit import AuditLog, Metric  # noqa: F401
from empla.models.belief import Belief, BeliefHistory  # noqa: F401
from empla.models.employee import Employee, EmployeeGoal, EmployeeIntention  # noqa: F401
from empla.models.memory import (  # noqa: F401
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    WorkingMemory,
)
from empla.models.tenant import Tenant, User  # noqa: F401

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target_metadata for 'autogenerate' support
target_metadata = Base.metadata

# Override sqlalchemy.url from environment variable if set
if database_url := os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit SQL to script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detect column type changes
        compare_server_default=True,  # Detect default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with the given connection.

    Called by run_migrations_online.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # Detect column type changes
        compare_server_default=True,  # Detect default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in async mode.

    Creates an async engine and runs migrations.
    """
    # Get configuration section
    configuration = config.get_section(config.config_ini_section, {})

    # Ensure we're using asyncpg driver
    if "sqlalchemy.url" in configuration:
        url = configuration["sqlalchemy.url"]
        if not url.startswith("postgresql+asyncpg://"):
            # Convert postgresql:// to postgresql+asyncpg://
            configuration["sqlalchemy.url"] = url.replace("postgresql://", "postgresql+asyncpg://")

    # Create async engine
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates an async engine and runs migrations.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
