"""
empla.models.employee - Employee Models

Digital employee models:
- Employee: Digital employee profile
- EmployeeGoal: BDI goal/desire
- EmployeeIntention: BDI intention/plan
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empla.models.base import TenantScopedModel

if TYPE_CHECKING:
    from empla.models.tenant import Tenant, User


class Employee(TenantScopedModel):
    """
    Digital employee.

    Example:
        >>> employee = Employee(
        ...     tenant_id=tenant.id,
        ...     name="Jordan Chen",
        ...     role="sales_ae",
        ...     email="jordan.chen@acme-corp.com",
        ...     status="active",
        ...     lifecycle_stage="autonomous"
        ... )
    """

    __tablename__ = "employees"

    # Identity
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Employee display name"
    )

    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Employee role (sales_ae, csm, pm, sdr, recruiter, custom)",
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Employee email address (must be unique within tenant)",
    )

    personality: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Personality traits (tone, communication style, risk tolerance)",
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'onboarding'"),
        comment="Operational status (onboarding, active, paused, terminated)",
    )

    lifecycle_stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'shadow'"),
        comment="Learning progression stage (shadow, supervised, autonomous)",
    )

    onboarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When onboarding completed (UTC)",
    )

    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When employee was activated (UTC)",
    )

    # Configuration
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Employee configuration (loop interval, LLM model, etc.)",
    )

    capabilities: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("'{}'::text[]"),
        comment="Enabled capabilities (email, calendar, research, etc.)",
    )

    # Performance
    performance_metrics: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Performance metrics (goals achieved, tasks completed, etc.)",
    )

    # Audit
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        comment="User who created this employee",
    )

    # Relationships
    # Note: tenant relationship omitted - use tenant_id directly
    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])
    goals: Mapped[list["EmployeeGoal"]] = relationship(
        "EmployeeGoal", back_populates="employee", cascade="all, delete-orphan"
    )
    intentions: Mapped[list["EmployeeIntention"]] = relationship(
        "EmployeeIntention", back_populates="employee", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('onboarding', 'active', 'paused', 'terminated')",
            name="ck_employees_status",
        ),
        CheckConstraint(
            "lifecycle_stage IN ('shadow', 'supervised', 'autonomous')",
            name="ck_employees_lifecycle_stage",
        ),
        CheckConstraint(
            "role IN ('sales_ae', 'csm', 'pm', 'sdr', 'recruiter', 'custom')",
            name="ck_employees_role",
        ),
        Index(
            "idx_employees_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_employees_status",
            "tenant_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_employees_role",
            "tenant_id",
            "role",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_employees_lifecycle",
            "lifecycle_stage",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_employees_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Employee(id={self.id}, name={self.name}, role={self.role})>"


class EmployeeGoal(TenantScopedModel):
    """
    Employee goal (BDI Desire).

    Example:
        >>> goal = EmployeeGoal(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     goal_type="achievement",
        ...     description="Close 10 deals this quarter",
        ...     priority=8,
        ...     target={"metric": "deals_closed", "value": 10}
        ... )
    """

    __tablename__ = "employee_goals"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this goal belongs to",
    )

    # Goal definition
    goal_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of goal (achievement, maintenance, prevention)",
    )

    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Human-readable goal description"
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
        comment="Priority (1=lowest, 10=highest)",
    )

    # Target & measurement
    target: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Goal-specific target metrics (metric, value, timeframe, etc.)",
    )

    current_progress: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Real-time progress tracking",
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
        comment="Goal status (active, in_progress, completed, abandoned, blocked)",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When goal was completed (UTC)",
    )

    abandoned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When goal was abandoned (UTC)",
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="goals")
    intentions: Mapped[list["EmployeeIntention"]] = relationship(
        "EmployeeIntention", back_populates="goal", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="ck_employee_goals_priority",
        ),
        CheckConstraint(
            "status IN ('active', 'in_progress', 'completed', 'abandoned', 'blocked')",
            name="ck_employee_goals_status",
        ),
        CheckConstraint(
            "goal_type IN ('achievement', 'maintenance', 'prevention')",
            name="ck_employee_goals_goal_type",
        ),
        Index(
            "idx_goals_employee",
            "employee_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_goals_priority",
            "employee_id",
            "priority",
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "idx_goals_tenant", "tenant_id", postgresql_where=text("deleted_at IS NULL")
        ),
    )

    def __repr__(self) -> str:
        return f"<EmployeeGoal(id={self.id}, description={self.description[:50]})>"


class EmployeeIntention(TenantScopedModel):
    """
    Employee intention (BDI Intention).

    Example:
        >>> intention = EmployeeIntention(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     goal_id=goal.id,
        ...     intention_type="action",
        ...     description="Send follow-up email",
        ...     plan={"type": "send_email", "params": {...}},
        ...     priority=7
        ... )
    """

    __tablename__ = "employee_intentions"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this intention belongs to",
    )

    goal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("employee_goals.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Goal this intention serves (None for opportunistic intentions)",
    )

    # Plan definition
    intention_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of intention (action, tactic, strategy)",
    )

    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Human-readable intention description"
    )

    plan: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Structured plan (steps, resources, expected outcomes)",
    )

    # Execution
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'planned'"),
        comment="Execution status (planned, in_progress, completed, failed, abandoned)",
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
        comment="Priority (1=lowest, 10=highest)",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When execution started (UTC)",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When execution completed (UTC)",
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When execution failed (UTC)",
    )

    # Context
    context: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Why this plan was chosen (rationale, alternatives considered)",
    )

    dependencies: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
        comment="Other intention UUIDs this depends on",
    )

    # Relationships
    employee: Mapped["Employee"] = relationship(
        "Employee", back_populates="intentions"
    )
    goal: Mapped["EmployeeGoal"] = relationship(
        "EmployeeGoal", back_populates="intentions"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'in_progress', 'completed', 'failed', 'abandoned')",
            name="ck_employee_intentions_status",
        ),
        CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="ck_employee_intentions_priority",
        ),
        CheckConstraint(
            "intention_type IN ('action', 'tactic', 'strategy')",
            name="ck_employee_intentions_intention_type",
        ),
        Index(
            "idx_intentions_employee",
            "employee_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_intentions_goal",
            "goal_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_intentions_status", "status", postgresql_where=text("deleted_at IS NULL")
        ),
        Index(
            "idx_intentions_priority",
            "employee_id",
            "priority",
            postgresql_where=text("status = 'planned'"),
        ),
        Index(
            "idx_intentions_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<EmployeeIntention(id={self.id}, type={self.intention_type})>"
