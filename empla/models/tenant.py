"""
empla.models.tenant - Tenant and User Models

Multi-tenancy models:
- Tenant: Customer organization
- User: Human user within a tenant
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empla.models.base import Base, SoftDeletableModel

if TYPE_CHECKING:
    from empla.models.employee import Employee


class Tenant(SoftDeletableModel, Base):
    """
    Customer organization.

    Each tenant is isolated via row-level security (RLS).

    Example:
        >>> tenant = Tenant(
        ...     name="Acme Corporation",
        ...     slug="acme-corp",
        ...     status="active"
        ... )
    """

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Unique identifier",
    )

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Organization display name"
    )

    slug: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="URL-safe identifier (e.g., 'acme-corp')",
    )

    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Tenant-specific configuration (LLM preferences, branding, etc.)",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
        comment="Account status (active, suspended, deleted)",
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tenant", cascade="all, delete-orphan"
    )
    employees: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="tenant", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z0-9-]+$'",
            name="ck_tenants_slug_format",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="ck_tenants_status",
        ),
        Index("idx_tenants_slug", "slug", postgresql_where=text("deleted_at IS NULL")),
        Index(
            "idx_tenants_status", "status", postgresql_where=text("deleted_at IS NULL")
        ),
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, slug={self.slug})>"


class User(SoftDeletableModel, Base):
    """
    Human user within a tenant.

    Users are scoped to a tenant - user@acme.com is different from user@competitor.com.

    Example:
        >>> user = User(
        ...     tenant_id=tenant.id,
        ...     email="jane@acme.com",
        ...     name="Jane Smith",
        ...     role="admin"
        ... )
    """

    __tablename__ = "users"

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
        comment="Tenant this user belongs to",
    )

    email: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="User email address"
    )

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="User display name"
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Authorization role (admin, manager, user)",
    )

    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="User preferences (notifications, UI settings, etc.)",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}$'",
            name="ck_users_email_format",
        ),
        CheckConstraint(
            "role IN ('admin', 'manager', 'user')",
            name="ck_users_role",
        ),
        Index(
            "idx_users_tenant", "tenant_id", postgresql_where=text("deleted_at IS NULL")
        ),
        Index(
            "idx_users_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
