"""
empla.models.base - Base SQLAlchemy Models

Provides base classes with common functionality:
- Base: SQLAlchemy declarative base
- TimestampedModel: Automatic created_at/updated_at timestamps
- SoftDeletableModel: Soft delete support (deleted_at)
- TenantScopedModel: Multi-tenant isolation (tenant_id)
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base.

    All models inherit from this class.
    """

    pass


class TimestampedModel:
    """
    Mixin for models with automatic timestamps.

    Provides:
    - created_at: Set on insert
    - updated_at: Set on insert, updated on every update
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When this record was created (UTC)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=datetime.utcnow,
        comment="When this record was last updated (UTC)",
    )


class SoftDeletableModel(TimestampedModel):
    """
    Mixin for models with soft delete support.

    Provides:
    - deleted_at: Timestamp when record was soft-deleted (NULL if active)
    - is_deleted property: Check if record is deleted
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="When this record was soft-deleted (UTC), None if active",
    )

    @property
    def is_deleted(self) -> bool:
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None


class TenantScopedModel(SoftDeletableModel, Base):
    """
    Base class for tenant-scoped models.

    Provides:
    - id: UUID primary key
    - tenant_id: Foreign key to tenants table
    - Timestamps (created_at, updated_at)
    - Soft delete (deleted_at)

    All tenant-scoped models should inherit from this.
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Unique identifier",
    )

    tenant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Tenant this record belongs to",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}(id={self.id})>"
