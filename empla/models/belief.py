"""
empla.models.belief - Belief Models

BDI belief models:
- Belief: Current belief (world model)
- BeliefHistory: Historical belief changes (for learning)
"""

from datetime import datetime
from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empla.models.base import TenantScopedModel

if TYPE_CHECKING:
    from empla.models.employee import Employee


class Belief(TenantScopedModel):
    """
    Employee belief (world model).

    Uses Subject-Predicate-Object triple structure.

    Example:
        >>> belief = Belief(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     belief_type="state",
        ...     subject="pipeline",
        ...     predicate="coverage",
        ...     object={"value": 2.1},
        ...     confidence=0.9,
        ...     source="observation"
        ... )
    """

    __tablename__ = "beliefs"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this belief belongs to",
    )

    # Belief content (SPO triple)
    belief_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of belief (state, event, causal, evaluative)",
    )

    subject: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="What the belief is about"
    )

    predicate: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Property or relation"
    )

    object: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Value (can be text, number, boolean, or complex object)",
    )

    # Confidence & source
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.5"),
        comment="Confidence level (0-1)",
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="How this belief was formed (observation, inference, told_by_human, prior)",
    )

    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="Supporting observations (episodic memory UUIDs)",
    )

    # Temporal decay
    formed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When belief was formed (UTC)",
    )

    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When belief was last updated (UTC)",
    )

    decay_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.1"),
        comment="Linear decay per day (0-1)",
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee")
    history: Mapped[list["BeliefHistory"]] = relationship(
        "BeliefHistory", back_populates="belief", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_beliefs_confidence",
        ),
        CheckConstraint(
            "decay_rate BETWEEN 0 AND 1",
            name="ck_beliefs_decay_rate",
        ),
        CheckConstraint(
            "belief_type IN ('state', 'event', 'causal', 'evaluative')",
            name="ck_beliefs_belief_type",
        ),
        CheckConstraint(
            "source IN ('observation', 'inference', 'told_by_human', 'prior')",
            name="ck_beliefs_source",
        ),
        Index(
            "idx_beliefs_employee",
            "employee_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_beliefs_subject",
            "employee_id",
            "subject",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_beliefs_confidence",
            "employee_id",
            "confidence",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_beliefs_updated",
            "last_updated_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_beliefs_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Unique constraint: one belief per (employee, subject, predicate)
        Index(
            "idx_beliefs_unique_subject_predicate",
            "employee_id",
            "subject",
            "predicate",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Belief(id={self.id}, subject={self.subject}, predicate={self.predicate})>"


class BeliefHistory(TenantScopedModel):
    """
    Belief change history.

    Immutable audit log of belief changes for learning and debugging.

    Example:
        >>> history = BeliefHistory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     belief_id=belief.id,
        ...     change_type="updated",
        ...     old_confidence=0.7,
        ...     new_confidence=0.9,
        ...     reason="New observation confirmed belief"
        ... )
    """

    __tablename__ = "belief_history"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this belief change relates to",
    )

    belief_id: Mapped[UUID] = mapped_column(
        ForeignKey("beliefs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Belief that changed",
    )

    # Change tracking
    change_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of change (created, updated, deleted, decayed)",
    )

    old_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Previous value"
    )

    new_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="New value"
    )

    old_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Previous confidence"
    )

    new_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="New confidence"
    )

    # Context
    reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Why belief changed"
    )

    # Temporal
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When change occurred (UTC)",
    )

    # Relationships
    belief: Mapped["Belief"] = relationship("Belief", back_populates="history")
    employee: Mapped["Employee"] = relationship("Employee")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "change_type IN ('created', 'updated', 'deleted', 'decayed')",
            name="ck_belief_history_change_type",
        ),
        Index("idx_belief_history_belief", "belief_id", "changed_at"),
        Index("idx_belief_history_employee", "employee_id", "changed_at"),
        Index("idx_belief_history_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<BeliefHistory(id={self.id}, change_type={self.change_type})>"
