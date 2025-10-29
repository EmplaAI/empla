"""
empla.models.memory - Memory System Models

Multi-layered memory models:
- EpisodicMemory: Personal experiences and events
- SemanticMemory: Facts and knowledge
- ProceduralMemory: Skills and procedures
- WorkingMemory: Current context
"""

from datetime import datetime
from typing import Any, TYPE_CHECKING
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empla.models.base import TenantScopedModel

if TYPE_CHECKING:
    from empla.models.employee import Employee


class EpisodicMemory(TenantScopedModel):
    """
    Episodic memory (events, interactions).

    Example:
        >>> memory = EpisodicMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     episode_type="interaction",
        ...     description="Email reply from prospect",
        ...     content={"from": "prospect@company.com", "body": "..."},
        ...     participants=["prospect@company.com"],
        ...     importance=0.8
        ... )
    """

    __tablename__ = "memory_episodes"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this memory belongs to",
    )

    # Episode content
    episode_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of episode (interaction, event, observation, feedback)",
    )

    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Human-readable episode summary"
    )

    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="Full episode data")

    # Context
    participants: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("'{}'::text[]"),
        comment="Email addresses or identifiers of participants",
    )

    location: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Where episode occurred (email, slack, zoom, phone, etc.)",
    )

    # Embedding for similarity search (pgvector)
    embedding: Mapped[Vector] = mapped_column(
        Vector(1024), nullable=True, comment="1024-dim embedding for semantic similarity"
    )

    # Importance & recall
    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.5"),
        comment="Importance score (0-1, affects retention)",
    )

    recall_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="How many times this memory was recalled",
    )

    last_recalled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this memory was last recalled (UTC)",
    )

    # Temporal
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When episode occurred (UTC)",
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "importance BETWEEN 0 AND 1",
            name="ck_episodes_importance",
        ),
        CheckConstraint(
            "episode_type IN ('interaction', 'event', 'observation', 'feedback')",
            name="ck_episodes_episode_type",
        ),
        Index(
            "idx_episodes_employee",
            "employee_id",
            "occurred_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_episodes_type",
            "employee_id",
            "episode_type",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_episodes_participants",
            "participants",
            postgresql_using="gin",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_episodes_occurred",
            "occurred_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_episodes_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Vector similarity index (IVFFlat)
        Index(
            "idx_episodes_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<EpisodicMemory(id={self.id}, type={self.episode_type})>"


class SemanticMemory(TenantScopedModel):
    """
    Semantic memory (facts, knowledge).

    Uses Subject-Predicate-Object (SPO) triple structure.

    Example:
        >>> memory = SemanticMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     fact_type="entity",
        ...     subject="Acme Corp",
        ...     predicate="is_a",
        ...     object="enterprise_customer",
        ...     confidence=0.9
        ... )
    """

    __tablename__ = "memory_semantic"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this memory belongs to",
    )

    # Fact content (SPO triple)
    fact_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of fact (entity, relationship, rule, definition)",
    )

    subject: Mapped[str] = mapped_column(String(200), nullable=False, comment="Subject of the fact")

    predicate: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Predicate (relation or property)"
    )

    object: Mapped[str] = mapped_column(String(500), nullable=False, comment="Object of the fact")

    # Additional context
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("1.0"),
        comment="Confidence in this fact (0-1)",
    )

    source: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Where this fact came from"
    )

    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="Whether fact was verified by human",
    )

    # Embedding
    embedding: Mapped[Vector] = mapped_column(
        Vector(1024), nullable=True, comment="1024-dim embedding for semantic similarity"
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_semantic_confidence",
        ),
        CheckConstraint(
            "fact_type IN ('entity', 'relationship', 'rule', 'definition')",
            name="ck_semantic_fact_type",
        ),
        Index(
            "idx_semantic_employee",
            "employee_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_semantic_subject",
            "employee_id",
            "subject",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_semantic_type",
            "employee_id",
            "fact_type",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_semantic_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Full-text search
        Index(
            "idx_semantic_fts",
            text("to_tsvector('english', subject || ' ' || predicate || ' ' || object)"),
            postgresql_using="gin",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Vector similarity index
        Index(
            "idx_semantic_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<SemanticMemory(id={self.id}, subject={self.subject})>"


class ProceduralMemory(TenantScopedModel):
    """
    Procedural memory (skills, workflows).

    Example:
        >>> memory = ProceduralMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     procedure_name="send_follow_up_email",
        ...     description="Send personalized follow-up after meeting",
        ...     procedure_type="skill",
        ...     steps={"steps": [...]},
        ...     learned_from="human_demonstration"
        ... )
    """

    __tablename__ = "memory_procedural"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this memory belongs to",
    )

    # Procedure definition
    procedure_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Unique procedure name"
    )

    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Human-readable procedure description"
    )

    procedure_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of procedure (skill, workflow, heuristic)",
    )

    # Procedure content
    steps: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="Structured procedure steps")

    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="When to use this procedure (context matching)",
    )

    # Learning & performance
    success_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.0"),
        comment="Success rate (0-1, learned from outcomes)",
    )

    execution_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="How many times this procedure was executed",
    )

    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this procedure was last executed (UTC)",
    )

    # Metadata
    learned_from: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="How this procedure was learned",
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "success_rate BETWEEN 0 AND 1",
            name="ck_procedural_success_rate",
        ),
        CheckConstraint(
            "procedure_type IN ('skill', 'workflow', 'heuristic')",
            name="ck_procedural_procedure_type",
        ),
        CheckConstraint(
            "learned_from IN ('human_demonstration', 'trial_and_error', 'instruction', 'pre_built')",
            name="ck_procedural_learned_from",
        ),
        Index(
            "idx_procedural_employee",
            "employee_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_procedural_type",
            "employee_id",
            "procedure_type",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_procedural_success",
            "employee_id",
            "success_rate",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_procedural_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Unique constraint: one procedure per (employee, procedure_name)
        Index(
            "idx_procedural_unique_name",
            "employee_id",
            "procedure_name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ProceduralMemory(id={self.id}, name={self.procedure_name})>"


class WorkingMemory(TenantScopedModel):
    """
    Working memory (current context).

    Short-lived memory for current execution context.

    Example:
        >>> memory = WorkingMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     context_type="current_task",
        ...     content={"task": "compose_email", "progress": "drafting"},
        ...     priority=8,
        ...     expires_at=datetime.utcnow() + timedelta(hours=1)
        ... )
    """

    __tablename__ = "memory_working"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this memory belongs to",
    )

    # Context content
    context_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of context (current_task, conversation, scratchpad, recent_observation)",
    )

    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="Context data")

    # Lifecycle
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
        comment="Priority (1=lowest, 10=highest, affects eviction)",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When to auto-evict this memory (UTC)",
    )

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="ck_working_priority",
        ),
        CheckConstraint(
            "context_type IN ('current_task', 'conversation', 'scratchpad', 'recent_observation')",
            name="ck_working_context_type",
        ),
        Index(
            "idx_working_employee",
            "employee_id",
            "priority",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_working_type",
            "employee_id",
            "context_type",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_working_expires",
            "expires_at",
            postgresql_where=text("deleted_at IS NULL AND expires_at IS NOT NULL"),
        ),
        Index(
            "idx_working_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<WorkingMemory(id={self.id}, type={self.context_type})>"
