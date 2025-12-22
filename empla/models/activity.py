"""
empla.models.activity - Employee Activity Model

Tracks actions, events, and progress for digital employees.
Used for the activity feed in the dashboard.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID as UUIDType
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from empla.models.base import Base, TimestampedModel


class ActivityEventType(StrEnum):
    """
    Standard event types for activities.

    Using StrEnum provides type safety and string representation.
    """

    # Email events
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    EMAIL_DRAFTED = "email_drafted"

    # Calendar events
    MEETING_SCHEDULED = "meeting_scheduled"
    MEETING_JOINED = "meeting_joined"
    MEETING_COMPLETED = "meeting_completed"

    # CRM events
    DEAL_CREATED = "deal_created"
    DEAL_UPDATED = "deal_updated"
    DEAL_WON = "deal_won"
    DEAL_LOST = "deal_lost"

    # Goal/Intention events
    GOAL_CREATED = "goal_created"
    GOAL_PROGRESS = "goal_progress"
    GOAL_ACHIEVED = "goal_achieved"
    INTENTION_STARTED = "intention_started"
    INTENTION_COMPLETED = "intention_completed"
    INTENTION_FAILED = "intention_failed"

    # Lifecycle events
    EMPLOYEE_STARTED = "employee_started"
    EMPLOYEE_STOPPED = "employee_stopped"
    EMPLOYEE_PAUSED = "employee_paused"
    EMPLOYEE_RESUMED = "employee_resumed"

    # Decision events
    DECISION_MADE = "decision_made"
    STRATEGY_SELECTED = "strategy_selected"

    # Error events
    ERROR_OCCURRED = "error_occurred"
    RETRY_ATTEMPTED = "retry_attempted"


class EmployeeActivity(TimestampedModel, Base):
    """
    Activity log entry for a digital employee.

    Records significant events like:
    - Emails sent/received
    - Goals achieved/updated
    - Intentions completed/failed
    - Meetings scheduled
    - Decisions made

    Example:
        >>> activity = EmployeeActivity(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     event_type="email_sent",
        ...     description="Sent follow-up email to John Smith",
        ...     data={"recipient": "john@example.com", "subject": "Re: Demo"},
        ...     importance=0.7
        ... )
    """

    __tablename__ = "employee_activities"

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Unique identifier",
    )

    tenant_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant this activity belongs to",
    )

    employee_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee who performed this activity",
    )

    # Activity details
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of event (email_sent, goal_progress, intention_completed, etc.)",
    )

    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Human-readable description of the activity",
    )

    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Additional structured data about the activity",
    )

    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.5"),
        comment="Importance score (0.0-1.0), used for filtering/ranking",
    )

    # Timing
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="When the activity occurred (UTC)",
    )

    # Indexes for efficient querying
    __table_args__ = (
        # Query activities by employee, most recent first
        Index(
            "idx_activities_employee_time",
            "employee_id",
            "occurred_at",
        ),
        # Query activities by tenant, most recent first
        Index(
            "idx_activities_tenant_time",
            "tenant_id",
            "occurred_at",
        ),
        # Filter by event type
        Index(
            "idx_activities_type",
            "employee_id",
            "event_type",
        ),
        # Filter by importance (for showing only important events)
        Index(
            "idx_activities_importance",
            "employee_id",
            "importance",
        ),
    )

    def __repr__(self) -> str:
        return f"<EmployeeActivity(id={self.id}, type={self.event_type})>"


__all__ = ["ActivityEventType", "EmployeeActivity"]
