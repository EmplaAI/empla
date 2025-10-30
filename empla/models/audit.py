"""
empla.models.audit - Audit and Observability Models

Observability models:
- AuditLog: Immutable audit log of all significant actions
- Metric: Time-series performance metrics
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID as PyUUID

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empla.models.base import TenantScopedModel

if TYPE_CHECKING:
    from empla.models.employee import Employee


class AuditLog(TenantScopedModel):
    """
    Audit log entry.

    Immutable append-only log of all significant actions for compliance and debugging.

    Example:
        >>> entry = AuditLog(
        ...     tenant_id=tenant.id,
        ...     actor_type="employee",
        ...     actor_id=employee.id,
        ...     action_type="goal_created",
        ...     resource_type="employee_goal",
        ...     resource_id=goal.id,
        ...     details={"description": "Close 10 deals"}
        ... )
    """

    __tablename__ = "audit_log"

    # Actor
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of actor (employee, user, system)",
    )

    actor_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Actor UUID (employee/user/system)",
    )

    # Action
    action_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Action performed (goal_created, intention_executed, etc.)",
    )

    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of resource affected",
    )

    resource_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Resource UUID (if applicable)",
    )

    # Details
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Action-specific details",
    )

    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Additional metadata",
        name="metadata",  # Column name in database
    )

    # Temporal
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When action occurred (UTC)",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('employee', 'user', 'system')",
            name="ck_audit_log_actor_type",
        ),
        Index("idx_audit_tenant", "tenant_id", "occurred_at"),
        Index("idx_audit_actor", "actor_type", "actor_id", "occurred_at"),
        Index("idx_audit_resource", "resource_type", "resource_id", "occurred_at"),
        Index("idx_audit_action", "action_type", "occurred_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action_type})>"


class Metric(TenantScopedModel):
    """
    Time-series performance metric.

    Example:
        >>> metric = Metric(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     metric_name="bdi.strategic_planning.duration",
        ...     metric_type="histogram",
        ...     value=1.5,
        ...     tags={"goal_type": "pipeline", "outcome": "success"}
        ... )
    """

    __tablename__ = "metrics"

    employee_id: Mapped[PyUUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=True,
        comment="Employee this metric relates to (None for system-wide metrics)",
    )

    # Metric identity
    metric_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Metric name (dotted notation: bdi.strategic_planning.duration)",
    )

    metric_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of metric (counter, gauge, histogram)",
    )

    # Value
    value: Mapped[float] = mapped_column(Float, nullable=False, comment="Metric value")

    tags: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Metric dimensions (goal_type, outcome, etc.)",
    )

    # Temporal
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When metric was recorded (UTC)",
    )

    # Relationships
    employee: Mapped[Optional["Employee"]] = relationship("Employee")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "metric_type IN ('counter', 'gauge', 'histogram')",
            name="ck_metrics_metric_type",
        ),
        Index("idx_metrics_tenant", "tenant_id", "timestamp"),
        Index(
            "idx_metrics_employee",
            "employee_id",
            "metric_name",
            "timestamp",
            postgresql_where=text("employee_id IS NOT NULL"),
        ),
        Index("idx_metrics_name", "metric_name", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Metric(id={self.id}, name={self.metric_name})>"
