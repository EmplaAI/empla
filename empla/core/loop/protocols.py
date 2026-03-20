"""
empla.core.loop.protocols - Shared protocols and models for the loop.

Contains the Protocol definitions (interfaces) for BDI components and
Pydantic models used as LLM structured outputs. These are extracted from
execution.py so they can be shared across loop sub-modules without
circular imports.
"""

from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from empla.core.loop.models import Observation

# ============================================================================
# Pydantic Models for LLM Structured Outputs
# ============================================================================


class SituationAnalysis(BaseModel):
    """LLM analysis of current situation."""

    current_state_summary: str = Field(..., description="Summary of current situation")
    gaps: list[str] = Field(
        default_factory=list, description="Gaps between current and desired state"
    )
    opportunities: list[str] = Field(default_factory=list, description="Opportunities identified")
    problems: list[str] = Field(default_factory=list, description="Problems requiring attention")
    recommended_focus: str = Field(..., description="What to focus on next")


class GoalRecommendation(BaseModel):
    """LLM recommendation for goal changes.

    Uses goal descriptions (not UUIDs) for abandonment and priority changes.
    The loop fuzzy-matches descriptions against active goals via _words_overlap().
    """

    new_goals: list[dict[str, Any]] = Field(
        default_factory=list,
        description="New goals to create, each with 'description', 'priority' (1-10), 'goal_type'",
    )
    goals_to_abandon: list[str] = Field(
        default_factory=list,
        description="Descriptions of goals that should be abandoned (no longer relevant or achievable)",
    )
    priority_adjustments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Goals needing priority changes, each with 'description' and 'new_priority' (1-10)",
    )
    reasoning: str = Field(..., description="Brief reasoning for the recommendations")


# ============================================================================
# Protocol Definitions (Interfaces for BDI Components)
# ============================================================================
# These define the interfaces that BDI components must implement.
# This allows the loop to be implemented and tested independently.
# ============================================================================


class BeliefChange(Protocol):
    """Protocol for belief changes returned by BeliefSystem"""

    subject: str
    predicate: str
    importance: float
    old_confidence: float
    new_confidence: float


class BeliefSystemProtocol(Protocol):
    """Protocol for BeliefSystem component"""

    async def update_beliefs(
        self, observations: list[Observation], identity_context: str | None = None
    ) -> list[BeliefChange]:
        """Update beliefs based on observations"""
        ...

    async def get_all_beliefs(self, min_confidence: float = 0.0) -> list[Any]:
        """Get all beliefs above confidence threshold"""
        ...

    async def update_belief(
        self,
        subject: str,
        predicate: str,
        belief_object: dict[str, Any],
        confidence: float,
        source: str,
    ) -> Any:
        """Update or create a single belief"""
        ...


class GoalSystemProtocol(Protocol):
    """Protocol for GoalSystem component"""

    async def get_goal(self, goal_id: Any) -> Any | None:
        """Get a single goal by ID"""
        ...

    async def get_active_goals(self) -> list[Any]:
        """Get all active goals"""
        ...

    async def get_pursuing_goals(self) -> list[Any]:
        """Get all goals being pursued (active or in_progress)"""
        ...

    async def update_goal_progress(self, goal_id: Any, progress: dict[str, Any]) -> Any:
        """Update goal progress"""
        ...

    async def complete_goal(
        self, goal_id: Any, final_progress: dict[str, Any] | None = None
    ) -> Any:
        """Mark a goal as completed"""
        ...

    async def add_goal(
        self,
        goal_type: str,
        description: str,
        priority: int,
        target: dict[str, Any],
    ) -> Any:
        """Add a new goal"""
        ...

    async def abandon_goal(self, goal_id: Any, reason: str) -> Any:
        """Abandon a goal"""
        ...

    async def update_goal_priority(self, goal_id: Any, new_priority: int) -> Any:
        """Update goal priority"""
        ...

    async def rollback(self) -> None:
        """Rollback the underlying session after a failed operation."""
        ...


class IntentionStackProtocol(Protocol):
    """Protocol for IntentionStack component"""

    async def get_next_intention(self) -> Any | None:
        """Get highest priority planned intention"""
        ...

    async def dependencies_satisfied(self, intention: Any) -> bool:
        """Check if intention dependencies are satisfied"""
        ...

    async def start_intention(self, intention_id: Any) -> Any:
        """Mark intention as in progress"""
        ...

    async def complete_intention(self, intention_id: Any, outcome: Any = None) -> Any:
        """Mark intention as completed"""
        ...

    async def fail_intention(self, intention_id: Any, error: str) -> Any:
        """Mark intention as failed"""
        ...

    async def get_intentions_for_goal(self, goal_id: Any) -> list[Any]:
        """Get all intentions for a goal"""
        ...

    async def generate_plan_for_goal(
        self,
        goal: Any,
        beliefs: list[Any],
        llm_service: Any,
        capabilities: list[str] | None = None,
        identity_context: str | None = None,
    ) -> list[Any]:
        """Generate a plan for a goal using LLM"""
        ...


class MemorySystemProtocol(Protocol):
    """Protocol for MemorySystem component"""

    @property
    def episodic(self) -> Any:
        """Access episodic memory subsystem"""
        ...

    @property
    def procedural(self) -> Any:
        """Access procedural memory subsystem"""
        ...

    @property
    def semantic(self) -> Any:
        """Access semantic memory subsystem (long-term knowledge)"""
        ...

    @property
    def working(self) -> Any:
        """Access working memory subsystem (short-term attention)"""
        ...


class ToolSourceProtocol(Protocol):
    """Protocol for tool sources (ToolRouter).

    Defines the interface the agentic loop uses for tool discovery and execution.
    """

    def get_all_tool_schemas(self, employee_id: UUID) -> list[dict[str, Any]]:
        """Get all available tool schemas for the employee."""
        ...

    async def execute_tool_call(
        self,
        employee_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        employee_role: str | None = None,
        tenant_id: UUID | None = None,
    ) -> Any:
        """Execute a tool call and return an ActionResult."""
        ...

    def get_enabled_capabilities(self, employee_id: UUID) -> list[str]:
        """List enabled capabilities for the employee."""
        ...
