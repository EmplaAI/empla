"""
empla.core.loop.models - Loop-specific Models

Data models for the proactive execution loop.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """
    Single observation from environment.

    Observations are raw events/data gathered during the perception phase.
    They are processed into belief updates by the BeliefSystem.

    Example:
        >>> obs = Observation(
        ...     employee_id=employee.id,
        ...     tenant_id=tenant.id,
        ...     observation_type="email_received",
        ...     source="email",
        ...     content={
        ...         "from": "customer@example.com",
        ...         "subject": "Feature request",
        ...         "body": "Can you add X feature?"
        ...     },
        ...     priority=7
        ... )
    """

    # Identity
    observation_id: UUID = Field(default_factory=uuid4)
    employee_id: UUID
    tenant_id: UUID

    # Content
    observation_type: str = Field(
        ...,
        description="Type of observation (email_received, calendar_event, metric_threshold, etc.)",
    )
    source: str = Field(..., description="Source of observation (email, calendar, metrics, etc.)")
    content: dict[str, Any] = Field(..., description="Structured observation data")

    # Context
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = Field(default=5, ge=1, le=10, description="Priority (1=lowest, 10=highest)")

    # Processing
    processed: bool = Field(default=False, description="Whether observation has been processed")
    belief_changes: list[UUID] = Field(
        default_factory=list, description="Beliefs updated from this observation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "observation_id": "550e8400-e29b-41d4-a716-446655440000",
                "employee_id": "123e4567-e89b-12d3-a456-426614174000",
                "tenant_id": "987e6543-e21b-43d2-a987-654321098000",
                "observation_type": "email_received",
                "source": "email",
                "content": {
                    "from": "customer@example.com",
                    "subject": "Feature request",
                    "importance": "high",
                },
                "priority": 7,
                "processed": False,
            }
        }


class PerceptionResult(BaseModel):
    """
    Result of perception cycle.

    Summary of what was observed during a perception phase.

    Example:
        >>> result = PerceptionResult(
        ...     observations=[obs1, obs2, obs3],
        ...     opportunities_detected=1,
        ...     problems_detected=0,
        ...     risks_detected=0,
        ...     perception_duration_ms=1250.5,
        ...     sources_checked=["email", "calendar", "metrics"]
        ... )
    """

    observations: list[Observation] = Field(default_factory=list)
    opportunities_detected: int = Field(default=0, ge=0)
    problems_detected: int = Field(default=0, ge=0)
    risks_detected: int = Field(default=0, ge=0)

    # Performance
    perception_duration_ms: float = Field(..., ge=0, description="Duration in milliseconds (>= 0)")
    sources_checked: list[str] = Field(default_factory=list)


class IntentionResult(BaseModel):
    """
    Result of intention execution.

    Captures outcome of executing an intention.

    Example:
        >>> result = IntentionResult(
        ...     intention_id=intention.id,
        ...     success=True,
        ...     outcome={"emails_sent": 5, "responses": 2},
        ...     duration_ms=3500.0
        ... )
    """

    intention_id: UUID
    success: bool
    outcome: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None)
    duration_ms: float | None = Field(default=None, gt=0)


class LoopConfig(BaseModel):
    """
    Configuration for proactive execution loop.

    Controls timing, perception sources, and execution limits.

    Example:
        >>> config = LoopConfig(
        ...     cycle_interval_seconds=300,  # 5 minutes
        ...     strategic_planning_interval_hours=24,  # Daily
        ...     perception_sources=["email", "calendar", "metrics"]
        ... )
    """

    # Timing
    cycle_interval_seconds: int = Field(
        default=300, gt=0, description="How often to run loop cycle (default: 5 minutes)"
    )
    error_backoff_seconds: int = Field(
        default=60, gt=0, description="How long to wait after error (default: 1 minute)"
    )

    # Strategic planning frequency
    strategic_planning_interval_hours: int = Field(
        default=24, gt=0, description="How often to run strategic planning (default: daily)"
    )
    force_strategic_planning_on_significant_change: bool = Field(
        default=True, description="Trigger strategic planning on significant belief changes"
    )

    # Perception configuration
    perception_sources: list[str] = Field(
        default_factory=lambda: ["email", "calendar", "chat", "crm", "metrics"],
        description="Which sources to check during perception",
    )

    # Execution limits
    max_intentions_per_cycle: int = Field(
        default=1, ge=1, description="How many intentions to execute per cycle"
    )
    max_cycle_duration_seconds: int = Field(
        default=600, gt=0, description="Maximum time per cycle (default: 10 minutes)"
    )

    # Learning
    deep_reflection_interval_hours: int = Field(
        default=24, gt=0, description="How often to run deep reflection (default: daily)"
    )
    enable_cross_employee_learning: bool = Field(
        default=True, description="Enable learning from other employees"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "cycle_interval_seconds": 300,
                "strategic_planning_interval_hours": 24,
                "perception_sources": ["email", "calendar", "metrics"],
                "max_intentions_per_cycle": 1,
            }
        }


# Role-specific configurations
ROLE_CONFIGS: dict[str, LoopConfig] = {
    "sales_ae": LoopConfig(
        cycle_interval_seconds=300,  # 5 minutes (highly reactive)
        strategic_planning_interval_hours=168,  # Weekly
    ),
    "csm": LoopConfig(
        cycle_interval_seconds=600,  # 10 minutes (less urgent than sales)
        strategic_planning_interval_hours=168,  # Weekly
    ),
    "pm": LoopConfig(
        cycle_interval_seconds=900,  # 15 minutes (strategic work, less reactive)
        strategic_planning_interval_hours=24,  # Daily
    ),
    "sdr": LoopConfig(
        cycle_interval_seconds=300,  # 5 minutes (highly reactive)
        strategic_planning_interval_hours=168,  # Weekly
    ),
    "recruiter": LoopConfig(
        cycle_interval_seconds=600,  # 10 minutes
        strategic_planning_interval_hours=168,  # Weekly
    ),
}
