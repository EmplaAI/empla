"""
empla.employees.config - Employee Configuration

Configuration for digital employees including goals, capabilities, and loop settings.

Example:
    >>> from empla.employees.config import EmployeeConfig, GoalConfig
    >>>
    >>> config = EmployeeConfig(
    ...     name="Jordan Chen",
    ...     role="sales_ae",
    ...     email="jordan@company.com",
    ...     goals=[
    ...         GoalConfig(
    ...             description="Maintain 3x pipeline coverage",
    ...             goal_type="maintenance",
    ...             priority=9,
    ...             target={"metric": "pipeline_coverage", "value": 3.0}
    ...         )
    ...     ],
    ...     capabilities=["email", "calendar", "crm"]
    ... )
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from empla.employees.personality import Personality


class GoalConfig(BaseModel):
    """Configuration for an employee goal."""

    description: str = Field(..., description="Human-readable goal description")
    goal_type: str = Field(
        default="achievement",
        description="Type: achievement, maintenance, or prevention"
    )
    priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10")
    target: dict[str, Any] = Field(
        default_factory=dict,
        description="Target metrics for the goal"
    )


class LoopSettings(BaseModel):
    """Settings for the proactive execution loop."""

    cycle_interval_seconds: int = Field(
        default=300,
        ge=60,
        description="Seconds between loop cycles (min 60)"
    )
    strategic_planning_interval_hours: int = Field(
        default=24,
        description="Hours between strategic planning sessions"
    )
    reflection_interval_hours: int = Field(
        default=24,
        description="Hours between deep reflection sessions"
    )
    max_concurrent_intentions: int = Field(
        default=3,
        ge=1,
        description="Max intentions to execute in parallel"
    )
    error_backoff_seconds: int = Field(
        default=60,
        description="Backoff time after errors"
    )


class LLMSettings(BaseModel):
    """LLM configuration for the employee."""

    primary_model: str = Field(
        default="claude-sonnet-4",
        description="Primary LLM model to use"
    )
    fallback_model: str | None = Field(
        default="gpt-4o",
        description="Fallback model if primary fails"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature"
    )
    max_tokens: int = Field(
        default=4096,
        description="Max tokens per request"
    )


class EmployeeConfig(BaseModel):
    """
    Complete configuration for a digital employee.

    This is the configuration object used to create and configure employees.

    Example:
        >>> config = EmployeeConfig(
        ...     name="Jordan Chen",
        ...     role="sales_ae",
        ...     email="jordan@company.com",
        ... )
        >>> employee = SalesAE(config)
        >>> await employee.start()
    """

    # Identity
    name: str = Field(..., min_length=1, description="Employee display name")
    role: str = Field(..., description="Role: sales_ae, csm, pm, sdr, recruiter, custom")
    email: str = Field(..., description="Employee email address")

    # Tenant context
    tenant_id: UUID | None = Field(default=None, description="Tenant ID for multi-tenancy")

    # Personality
    personality: Personality | None = Field(
        default=None,
        description="Personality profile (uses role default if not set)"
    )

    # Goals
    goals: list[GoalConfig] = Field(
        default_factory=list,
        description="Initial goals for the employee"
    )

    # Capabilities
    capabilities: list[str] = Field(
        default_factory=lambda: ["email"],
        description="Enabled capabilities: email, calendar, crm, messaging, browser"
    )

    # Loop settings
    loop: LoopSettings = Field(default_factory=LoopSettings)

    # LLM settings
    llm: LLMSettings = Field(default_factory=LLMSettings)

    # Additional config
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    def to_db_config(self) -> dict[str, Any]:
        """Convert to database-storable config dict."""
        return {
            "loop": self.loop.model_dump(),
            "llm": self.llm.model_dump(),
            "metadata": self.metadata,
        }

    def to_db_personality(self) -> dict[str, Any]:
        """Convert personality to database-storable dict."""
        if self.personality:
            return self.personality.model_dump()
        return {}


# Role-specific default configurations
SALES_AE_DEFAULT_GOALS = [
    GoalConfig(
        description="Maintain 3x pipeline coverage",
        goal_type="maintenance",
        priority=9,
        target={"metric": "pipeline_coverage", "value": 3.0},
    ),
    GoalConfig(
        description="Respond to leads within 4 hours",
        goal_type="maintenance",
        priority=8,
        target={"metric": "lead_response_time_hours", "value": 4},
    ),
    GoalConfig(
        description="Achieve 25% win rate",
        goal_type="achievement",
        priority=7,
        target={"metric": "win_rate", "value": 0.25},
    ),
]

CSM_DEFAULT_GOALS = [
    GoalConfig(
        description="Maintain 95% customer retention",
        goal_type="maintenance",
        priority=10,
        target={"metric": "retention_rate", "value": 0.95},
    ),
    GoalConfig(
        description="Achieve NPS score above 50",
        goal_type="achievement",
        priority=8,
        target={"metric": "nps", "value": 50},
    ),
    GoalConfig(
        description="Complete onboarding within 5 days",
        goal_type="achievement",
        priority=7,
        target={"metric": "onboarding_days", "value": 5},
    ),
]

PM_DEFAULT_GOALS = [
    GoalConfig(
        description="Ship 3 high-impact features per quarter",
        goal_type="achievement",
        priority=8,
        target={"metric": "features_shipped", "value": 3, "period": "quarter"},
    ),
    GoalConfig(
        description="Improve user satisfaction by 10%",
        goal_type="achievement",
        priority=7,
        target={"metric": "satisfaction_improvement", "value": 0.10},
    ),
]


__all__ = [
    "EmployeeConfig",
    "GoalConfig",
    "LLMSettings",
    "LoopSettings",
    # Default goals
    "CSM_DEFAULT_GOALS",
    "PM_DEFAULT_GOALS",
    "SALES_AE_DEFAULT_GOALS",
]
