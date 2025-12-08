"""
empla.core.telemetry.models - Trajectory Data Models

Complete data models for tracking BDI trajectories.
Captures the full reasoning cycle: Observation → Belief → Goal → Intention → Action → Outcome
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ObservationType(str, Enum):
    """Type of observation."""

    PERCEPTION = "perception"  # From capability perception
    EVENT = "event"  # Scheduled or triggered event
    METRIC = "metric"  # Data-driven metric threshold
    EXTERNAL = "external"  # External stimulus (email, mention, etc.)


class BeliefSource(str, Enum):
    """How the belief was formed."""

    OBSERVATION = "observation"  # Extracted from observation
    INFERENCE = "inference"  # Inferred from existing beliefs
    TOLD_BY_HUMAN = "told_by_human"  # Human feedback
    PRIOR = "prior"  # Pre-existing knowledge


class GoalType(str, Enum):
    """Type of goal."""

    ACHIEVEMENT = "achievement"  # Achieve something new
    MAINTENANCE = "maintenance"  # Maintain current state
    PREVENTION = "prevention"  # Prevent something bad


class GoalStatus(str, Enum):
    """Goal lifecycle status."""

    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


class IntentionType(str, Enum):
    """Level of intention."""

    ACTION = "action"  # Single atomic action
    TACTIC = "tactic"  # Short-term plan (multiple actions)
    STRATEGY = "strategy"  # Long-term strategic plan


class IntentionStatus(str, Enum):
    """Intention execution status."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class OutcomeStatus(str, Enum):
    """Outcome of action execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"  # Partial success
    BLOCKED = "blocked"  # Could not execute


# ==========================================
# Trajectory Components
# ==========================================


class TrajectoryObservation(BaseModel):
    """Single observation captured during perception."""

    observation_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    observation_type: ObservationType
    source: str  # Which capability or system generated this
    priority: int = Field(ge=1, le=10)  # 1=low, 10=critical
    data: dict[str, Any]  # Observation content
    requires_immediate_action: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "observation_type": "perception",
                "source": "EmailCapability",
                "priority": 8,
                "data": {
                    "type": "high_priority_email",
                    "from": "customer@acme.com",
                    "subject": "Urgent: System down",
                },
                "requires_immediate_action": True,
            }
        }


class TrajectoryBelief(BaseModel):
    """Belief formed or updated from observation."""

    belief_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    subject: str  # What the belief is about
    predicate: str  # The relationship or property
    object: str  # The value or target
    confidence: float = Field(ge=0.0, le=1.0)
    source: BeliefSource
    source_observation_id: UUID | None = None  # Which observation triggered this
    previous_value: str | None = None  # If updating existing belief
    reasoning: str  # LLM reasoning for this belief

    class Config:
        json_schema_extra = {
            "example": {
                "subject": "pipeline_coverage",
                "predicate": "is_below_target",
                "object": "2.0x vs 3.0x target",
                "confidence": 0.95,
                "source": "observation",
                "reasoning": "Pipeline coverage metric shows 2.0x, significantly below our 3.0x target. This requires immediate attention.",
            }
        }


class TrajectoryGoal(BaseModel):
    """Goal formed or updated during reasoning."""

    goal_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    goal_type: GoalType
    description: str  # Human-readable goal description
    priority: int = Field(ge=1, le=10)  # 1=lowest, 10=highest
    target: dict[str, Any]  # Goal target metrics
    status: GoalStatus
    triggered_by_beliefs: list[UUID] = Field(default_factory=list)  # Which beliefs triggered this
    parent_goal_id: UUID | None = None  # If this is a sub-goal
    reasoning: str  # Why this goal was formed

    class Config:
        json_schema_extra = {
            "example": {
                "goal_type": "achievement",
                "description": "Build pipeline to 3x coverage",
                "priority": 9,
                "target": {"metric": "pipeline_coverage", "value": 3.0, "timeframe": "this_week"},
                "status": "active",
                "reasoning": "Pipeline is critically low (2.0x vs 3.0x target). Must build pipeline urgently to hit quarterly targets.",
            }
        }


class TrajectoryIntention(BaseModel):
    """Intention/plan formed to achieve goal."""

    intention_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    intention_type: IntentionType
    description: str  # What will be done
    plan: dict[str, Any]  # Structured plan (steps, resources, timeline)
    status: IntentionStatus
    priority: int = Field(ge=1, le=10)
    goal_id: UUID  # Which goal this serves
    depends_on: list[UUID] = Field(default_factory=list)  # Dependency on other intentions
    alternatives_considered: list[dict[str, Any]] = Field(
        default_factory=list
    )  # Other plans considered
    selection_rationale: str  # Why this plan was chosen

    class Config:
        json_schema_extra = {
            "example": {
                "intention_type": "tactic",
                "description": "Research and outreach to 10 target accounts",
                "plan": {
                    "steps": [
                        {"action": "research_accounts", "count": 10},
                        {"action": "send_personalized_outreach", "count": 10},
                    ],
                    "estimated_duration": "2 hours",
                },
                "status": "planned",
                "priority": 9,
                "selection_rationale": "Multi-touch outreach has 3x success rate vs cold calls based on procedural memory.",
            }
        }


class TrajectoryAction(BaseModel):
    """Single action executed as part of intention."""

    action_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    intention_id: UUID  # Which intention this belongs to
    action_type: str  # Type of action (send_email, create_meeting, etc.)
    capability_used: str  # Which capability executed this
    parameters: dict[str, Any]  # Action parameters (PII-safe - no credentials)
    execution_started_at: datetime | None = None
    execution_completed_at: datetime | None = None
    execution_duration_ms: float | None = None
    retries: int = 0

    class Config:
        json_schema_extra = {
            "example": {
                "action_type": "send_email",
                "capability_used": "EmailCapability",
                "parameters": {
                    "recipient_count": 10,
                    "email_type": "outreach",
                    "personalization": "account_research",
                },
                "execution_duration_ms": 1250,
                "retries": 0,
            }
        }


class TrajectoryOutcome(BaseModel):
    """Outcome of action execution."""

    outcome_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    action_id: UUID  # Which action this is the outcome of
    status: OutcomeStatus
    result: dict[str, Any]  # Actual results
    impact: dict[str, Any] = Field(default_factory=dict)  # Impact on world state
    error: str | None = None  # Error message if failed
    learning: str | None = None  # What was learned from this outcome

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "result": {
                    "emails_sent": 10,
                    "delivery_success": 10,
                    "deals_created": 5,
                    "pipeline_added": "$250K",
                },
                "impact": {"pipeline_coverage": "improved from 2.0x to 2.5x"},
                "learning": "Personalized outreach based on account research has 50% conversion to deal creation.",
            }
        }


# ==========================================
# Trajectory Structure
# ==========================================


class TrajectoryStep(BaseModel):
    """Single step in BDI trajectory: Obs → Belief → Goal → Intention → Action → Outcome."""

    step_id: UUID = Field(default_factory=uuid4)
    step_number: int  # Sequential step number in trajectory
    timestamp: datetime = Field(default_factory=lambda: datetime.now())

    # BDI cycle components
    observations: list[TrajectoryObservation] = Field(default_factory=list)
    beliefs_updated: list[TrajectoryBelief] = Field(default_factory=list)
    goals_formed: list[TrajectoryGoal] = Field(default_factory=list)
    goals_updated: list[TrajectoryGoal] = Field(default_factory=list)
    intentions_planned: list[TrajectoryIntention] = Field(default_factory=list)
    actions_executed: list[TrajectoryAction] = Field(default_factory=list)
    outcomes: list[TrajectoryOutcome] = Field(default_factory=list)

    # Metadata
    cycle_duration_ms: float  # How long this cycle took
    llm_calls: int = 0  # Number of LLM calls in this step
    llm_tokens_used: int = 0  # Total tokens used

    def summary(self) -> str:
        """Generate human-readable summary of this step."""
        return (
            f"Step {self.step_number}: "
            f"{len(self.observations)} obs → "
            f"{len(self.beliefs_updated)} beliefs → "
            f"{len(self.goals_formed)} goals → "
            f"{len(self.intentions_planned)} plans → "
            f"{len(self.actions_executed)} actions → "
            f"{len(self.outcomes)} outcomes"
        )


class TrajectorySession(BaseModel):
    """Complete session of trajectory tracking (multiple steps)."""

    session_id: UUID = Field(default_factory=uuid4)
    employee_id: UUID
    tenant_id: UUID
    started_at: datetime = Field(default_factory=lambda: datetime.now())
    ended_at: datetime | None = None

    # Session metadata
    session_type: str = "autonomous_loop"  # autonomous_loop, task_execution, etc.
    session_config: dict[str, Any] = Field(default_factory=dict)

    # Performance metrics
    total_steps: int = 0
    total_observations: int = 0
    total_beliefs: int = 0
    total_goals: int = 0
    total_intentions: int = 0
    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    total_llm_calls: int = 0
    total_llm_tokens: int = 0
    total_duration_ms: float = 0

    def end_session(self) -> None:
        """Mark session as ended."""
        self.ended_at = datetime.now()
        if self.started_at:
            delta = self.ended_at - self.started_at
            self.total_duration_ms = delta.total_seconds() * 1000


class BDITrajectory(BaseModel):
    """Complete BDI trajectory - collection of steps forming a reasoning episode."""

    trajectory_id: UUID = Field(default_factory=uuid4)
    session_id: UUID  # Which session this trajectory belongs to
    employee_id: UUID
    tenant_id: UUID

    # Trajectory metadata
    started_at: datetime = Field(default_factory=lambda: datetime.now())
    ended_at: datetime | None = None
    trigger: str  # What triggered this trajectory (scheduled_loop, event, human_request)
    trigger_data: dict[str, Any] = Field(default_factory=dict)

    # Trajectory steps (chronological)
    steps: list[TrajectoryStep] = Field(default_factory=list)

    # Outcome summary
    goals_achieved: int = 0
    goals_blocked: int = 0
    overall_success: bool = False
    key_learnings: list[str] = Field(default_factory=list)

    def add_step(self, step: TrajectoryStep) -> None:
        """Add step to trajectory."""
        step.step_number = len(self.steps) + 1
        self.steps.append(step)

    def end_trajectory(self, success: bool = False, learnings: list[str] | None = None) -> None:
        """Mark trajectory as ended."""
        self.ended_at = datetime.now()
        self.overall_success = success
        if learnings:
            self.key_learnings.extend(learnings)

    def summary(self) -> dict[str, Any]:
        """Generate trajectory summary for analysis."""
        return {
            "trajectory_id": str(self.trajectory_id),
            "employee_id": str(self.employee_id),
            "duration_ms": (
                (self.ended_at - self.started_at).total_seconds() * 1000
                if self.ended_at
                else None
            ),
            "trigger": self.trigger,
            "total_steps": len(self.steps),
            "total_observations": sum(len(step.observations) for step in self.steps),
            "total_beliefs": sum(len(step.beliefs_updated) for step in self.steps),
            "total_goals": sum(
                len(step.goals_formed) + len(step.goals_updated) for step in self.steps
            ),
            "total_intentions": sum(len(step.intentions_planned) for step in self.steps),
            "total_actions": sum(len(step.actions_executed) for step in self.steps),
            "total_outcomes": sum(len(step.outcomes) for step in self.steps),
            "goals_achieved": self.goals_achieved,
            "goals_blocked": self.goals_blocked,
            "overall_success": self.overall_success,
            "key_learnings": self.key_learnings,
        }
