"""
empla.employees.config - Employee Configuration

Configuration for digital employees including goals, capabilities, and loop settings.

Roles and goal types are strings to support extensibility - custom roles can be
defined at runtime without code changes.

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

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from empla.employees.personality import Personality


class GoalConfig(BaseModel):
    """
    Configuration for an employee goal.

    Goals define what the employee is trying to achieve. They are used by
    the BDI engine to drive autonomous behavior.

    Goal Types:
    - "achievement": One-time target to reach (e.g., "close 10 deals")
    - "maintenance": Ongoing target to maintain (e.g., "keep 3x pipeline")
    - "prevention": Something to avoid (e.g., "prevent churn")
    - Custom types are also supported for extensibility
    """

    model_config = ConfigDict(frozen=True)

    description: str = Field(..., min_length=1, description="Human-readable goal description")
    goal_type: str = Field(
        default="achievement",
        min_length=1,
        description="Type: achievement, maintenance, prevention, or custom",
    )
    priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10 (10 is highest)")
    target: dict[str, Any] = Field(
        default_factory=dict,
        description="Target metrics for the goal (e.g., {'metric': 'pipeline_coverage', 'value': 3.0})",
    )


class LoopSettings(BaseModel):
    """
    Settings for the proactive execution loop.

    Controls timing of the autonomous operation cycle.
    """

    model_config = ConfigDict(frozen=True)

    cycle_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Seconds between loop cycles (60-3600)",
    )
    strategic_planning_interval_hours: int = Field(
        default=24,
        ge=1,
        le=168,  # Max 1 week
        description="Hours between strategic planning sessions (1-168)",
    )
    reflection_interval_hours: int = Field(
        default=24,
        ge=1,
        le=168,  # Max 1 week
        description="Hours between deep reflection sessions (1-168)",
    )
    max_concurrent_intentions: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max intentions to execute in parallel (1-10)",
    )
    error_backoff_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
        description="Backoff time after errors (10-600 seconds)",
    )


class LLMSettings(BaseModel):
    """LLM configuration for the employee."""

    model_config = ConfigDict(frozen=True)

    primary_model: str = Field(
        default="claude-sonnet-4",
        min_length=1,
        description="Primary LLM model to use",
    )
    fallback_model: str | None = Field(
        default="gpt-4o",
        description="Fallback model if primary fails (None to disable)",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0-2.0)",
    )
    max_tokens: int = Field(
        default=4096,
        ge=100,
        le=128000,
        description="Max tokens per request",
    )


class EmployeeConfig(BaseModel):
    """
    Complete configuration for a digital employee.

    This is the configuration object used to create and configure employees.
    Config is validated at construction and immutable after creation.

    Role is a string to support extensibility - custom roles can be defined
    at runtime without requiring code changes. Built-in roles include:
    - "sales_ae": Sales Account Executive
    - "csm": Customer Success Manager
    - "pm": Product Manager
    - "sdr": Sales Development Rep
    - "recruiter": Recruiter
    - Custom roles are also supported

    Example:
        >>> config = EmployeeConfig(
        ...     name="Jordan Chen",
        ...     role="sales_ae",
        ...     email="jordan@company.com",
        ... )
        >>> employee = SalesAE(config)
        >>> await employee.start()
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    name: str = Field(..., min_length=1, max_length=100, description="Employee display name")
    role: str = Field(..., min_length=1, description="Employee role (e.g., sales_ae, csm, pm, or custom)")
    email: EmailStr = Field(..., description="Employee email address")

    # Tenant context
    tenant_id: UUID | None = Field(default=None, description="Tenant ID for multi-tenancy")

    # Personality
    personality: Personality | None = Field(
        default=None,
        description="Personality profile (uses role default if not set)",
    )

    # Goals
    goals: list[GoalConfig] = Field(
        default_factory=list,
        description="Initial goals for the employee",
    )

    # Capabilities
    capabilities: list[str] = Field(
        default_factory=lambda: ["email"],
        description="Enabled capabilities: email, calendar, crm, messaging, browser",
    )

    # Loop settings
    loop: LoopSettings = Field(default_factory=LoopSettings)

    # LLM settings
    llm: LLMSettings = Field(default_factory=LLMSettings)

    # Additional config
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate and normalize employee name."""
        stripped = v.strip()
        if len(stripped) < 1:
            raise ValueError("Employee name cannot be empty or whitespace only")
        return stripped

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate and normalize employee role."""
        stripped = v.strip().lower()
        if len(stripped) < 1:
            raise ValueError("Employee role cannot be empty or whitespace only")
        return stripped

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: list[str]) -> list[str]:
        """Validate capability list."""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate capabilities are not allowed")
        return v

    def to_db_config(self) -> dict[str, Any]:
        """
        Convert to database-storable config dict.

        Note: This only includes runtime configuration settings.
        Other fields are stored in separate columns:
        - goals: Stored in goals table
        - capabilities: Stored in employee.capabilities column
        - personality: Stored in employee.personality column
        """
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
    # Config classes
    "EmployeeConfig",
    "GoalConfig",
    "LLMSettings",
    "LoopSettings",
    # Default goals
    "CSM_DEFAULT_GOALS",
    "PM_DEFAULT_GOALS",
    "SALES_AE_DEFAULT_GOALS",
]
