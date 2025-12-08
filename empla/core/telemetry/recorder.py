"""
empla.core.telemetry.recorder - BDI Trajectory Telemetry Recorder

Core recorder for logging complete BDI cycles during autonomous agent execution.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from uuid import UUID

from empla.core.telemetry.models import (
    BDITrajectory,
    BeliefSource,
    GoalStatus,
    GoalType,
    IntentionStatus,
    IntentionType,
    ObservationType,
    OutcomeStatus,
    TrajectoryAction,
    TrajectoryBelief,
    TrajectoryGoal,
    TrajectoryIntention,
    TrajectoryObservation,
    TrajectoryOutcome,
    TrajectorySession,
    TrajectoryStep,
)


class TelemetryRecorder:
    """
    Record complete BDI trajectories for autonomous agents.

    Usage:
        recorder = TelemetryRecorder(employee_id, tenant_id)

        # Start a session
        session = recorder.start_session()

        # Start a trajectory (triggered by loop or event)
        trajectory = recorder.start_trajectory(trigger="scheduled_loop")

        # Begin step
        step = recorder.start_step()

        # Log observations
        recorder.log_observation(
            observation_type="perception",
            source="EmailCapability",
            priority=8,
            data={"type": "urgent_email", ...}
        )

        # Log belief updates
        recorder.log_belief(
            subject="pipeline_coverage",
            predicate="is_below_target",
            object="2.0x",
            confidence=0.95,
            source="observation",
            reasoning="Pipeline metric shows..."
        )

        # Log goals
        recorder.log_goal(
            goal_type="achievement",
            description="Build pipeline to 3x",
            priority=9,
            target={...},
            triggered_by_beliefs=[belief_id, ...]
        )

        # Log intentions
        recorder.log_intention(
            intention_type="tactic",
            description="Research and outreach",
            plan={...},
            goal_id=goal_id,
            selection_rationale="..."
        )

        # Log actions
        action_id = recorder.log_action(
            intention_id=intention_id,
            action_type="send_email",
            capability_used="EmailCapability",
            parameters={...}
        )

        # Log outcomes
        recorder.log_outcome(
            action_id=action_id,
            status="success",
            result={...},
            impact={...},
            learning="..."
        )

        # End step
        recorder.end_step(llm_calls=2, llm_tokens=1500)

        # End trajectory
        recorder.end_trajectory(success=True, learnings=["..."])

        # End session
        recorder.end_session()

        # Get trajectory for analysis
        trajectory = recorder.get_current_trajectory()
    """

    def __init__(self, employee_id: UUID, tenant_id: UUID):
        """
        Initialize trajectory recorder.

        Args:
            employee_id: Employee being tracked
            tenant_id: Tenant ID for multi-tenancy
        """
        self.employee_id = employee_id
        self.tenant_id = tenant_id

        # Current tracking state
        self.current_session: TrajectorySession | None = None
        self.current_trajectory: BDITrajectory | None = None
        self.current_step: TrajectoryStep | None = None
        self.current_step_start_time: float | None = None

        # All completed trajectories in this session
        self.completed_trajectories: list[BDITrajectory] = []

    # ==========================================
    # Session Management
    # ==========================================

    def start_session(
        self, session_type: str = "autonomous_loop", config: dict[str, Any] | None = None
    ) -> TrajectorySession:
        """
        Start a new tracking session.

        Args:
            session_type: Type of session (autonomous_loop, task_execution, etc.)
            config: Session configuration

        Returns:
            TrajectorySession instance
        """
        self.current_session = TrajectorySession(
            employee_id=self.employee_id,
            tenant_id=self.tenant_id,
            session_type=session_type,
            session_config=config or {},
        )
        return self.current_session

    def end_session(self) -> TrajectorySession | None:
        """
        End current session.

        Returns:
            Ended session or None if no active session
        """
        if not self.current_session:
            return None

        # Finalize any active trajectory
        if self.current_trajectory:
            self.end_trajectory()

        # Update session metrics
        self.current_session.total_steps = sum(
            len(t.steps) for t in self.completed_trajectories
        )
        self.current_session.total_observations = sum(
            sum(len(step.observations) for step in t.steps) for t in self.completed_trajectories
        )
        self.current_session.total_beliefs = sum(
            sum(len(step.beliefs_updated) for step in t.steps)
            for t in self.completed_trajectories
        )
        self.current_session.total_goals = sum(
            sum(len(step.goals_formed) + len(step.goals_updated) for step in t.steps)
            for t in self.completed_trajectories
        )
        self.current_session.total_intentions = sum(
            sum(len(step.intentions_planned) for step in t.steps)
            for t in self.completed_trajectories
        )
        self.current_session.total_actions = sum(
            sum(len(step.actions_executed) for step in t.steps)
            for t in self.completed_trajectories
        )
        self.current_session.successful_actions = sum(
            sum(
                len([o for o in step.outcomes if o.status == OutcomeStatus.SUCCESS])
                for step in t.steps
            )
            for t in self.completed_trajectories
        )
        self.current_session.failed_actions = sum(
            sum(
                len([o for o in step.outcomes if o.status == OutcomeStatus.FAILURE])
                for step in t.steps
            )
            for t in self.completed_trajectories
        )
        self.current_session.total_llm_calls = sum(
            sum(step.llm_calls for step in t.steps) for t in self.completed_trajectories
        )
        self.current_session.total_llm_tokens = sum(
            sum(step.llm_tokens_used for step in t.steps) for t in self.completed_trajectories
        )

        self.current_session.end_session()

        session = self.current_session
        self.current_session = None
        return session

    # ==========================================
    # Trajectory Management
    # ==========================================

    def start_trajectory(
        self, trigger: str, trigger_data: dict[str, Any] | None = None
    ) -> BDITrajectory:
        """
        Start a new trajectory.

        Args:
            trigger: What triggered this trajectory (scheduled_loop, event, etc.)
            trigger_data: Additional trigger context

        Returns:
            BDITrajectory instance
        """
        if not self.current_session:
            raise ValueError("Cannot start trajectory without active session")

        # Finalize previous trajectory if exists
        if self.current_trajectory:
            self.end_trajectory()

        self.current_trajectory = BDITrajectory(
            session_id=self.current_session.session_id,
            employee_id=self.employee_id,
            tenant_id=self.tenant_id,
            trigger=trigger,
            trigger_data=trigger_data or {},
        )

        return self.current_trajectory

    def end_trajectory(
        self, success: bool = False, learnings: list[str] | None = None
    ) -> BDITrajectory | None:
        """
        End current trajectory.

        Args:
            success: Whether trajectory was overall successful
            learnings: Key learnings from this trajectory

        Returns:
            Ended trajectory or None if no active trajectory
        """
        if not self.current_trajectory:
            return None

        # Finalize any active step
        if self.current_step:
            self.end_step()

        # Count goal outcomes
        all_goals = []
        for step in self.current_trajectory.steps:
            all_goals.extend(step.goals_formed)
            all_goals.extend(step.goals_updated)

        self.current_trajectory.goals_achieved = len(
            [g for g in all_goals if g.status == GoalStatus.COMPLETED]
        )
        self.current_trajectory.goals_blocked = len(
            [g for g in all_goals if g.status == GoalStatus.BLOCKED]
        )

        self.current_trajectory.end_trajectory(success=success, learnings=learnings)

        # Store completed trajectory
        self.completed_trajectories.append(self.current_trajectory)

        trajectory = self.current_trajectory
        self.current_trajectory = None
        return trajectory

    # ==========================================
    # Step Management
    # ==========================================

    def start_step(self) -> TrajectoryStep:
        """
        Start a new trajectory step.

        Returns:
            TrajectoryStep instance
        """
        if not self.current_trajectory:
            raise ValueError("Cannot start step without active trajectory")

        # Finalize previous step if exists
        if self.current_step:
            self.end_step()

        self.current_step = TrajectoryStep(
            step_number=len(self.current_trajectory.steps) + 1,
            cycle_duration_ms=0,  # Will be set in end_step
        )
        self.current_step_start_time = time.perf_counter()

        return self.current_step

    def end_step(self, llm_calls: int = 0, llm_tokens: int = 0) -> TrajectoryStep | None:
        """
        End current step.

        Args:
            llm_calls: Number of LLM calls made during this step
            llm_tokens: Total tokens used in LLM calls

        Returns:
            Ended step or None if no active step
        """
        if not self.current_step or not self.current_trajectory:
            return None

        # Calculate duration
        if self.current_step_start_time:
            duration_seconds = time.perf_counter() - self.current_step_start_time
            self.current_step.cycle_duration_ms = duration_seconds * 1000

        # Set LLM metrics
        self.current_step.llm_calls = llm_calls
        self.current_step.llm_tokens_used = llm_tokens

        # Add to trajectory
        self.current_trajectory.add_step(self.current_step)

        step = self.current_step
        self.current_step = None
        self.current_step_start_time = None
        return step

    # ==========================================
    # Component Logging
    # ==========================================

    def log_observation(
        self,
        observation_type: str | ObservationType,
        source: str,
        priority: int,
        data: dict[str, Any],
        requires_immediate_action: bool = False,
    ) -> TrajectoryObservation:
        """
        Log an observation.

        Args:
            observation_type: Type of observation
            source: Source capability/system
            priority: Priority 1-10
            data: Observation data
            requires_immediate_action: Whether this requires immediate response

        Returns:
            TrajectoryObservation instance
        """
        if not self.current_step:
            raise ValueError("Cannot log observation without active step")

        if isinstance(observation_type, str):
            observation_type = ObservationType(observation_type)

        obs = TrajectoryObservation(
            observation_type=observation_type,
            source=source,
            priority=priority,
            data=data,
            requires_immediate_action=requires_immediate_action,
        )

        self.current_step.observations.append(obs)
        return obs

    def log_belief(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float,
        source: str | BeliefSource,
        reasoning: str,
        source_observation_id: UUID | None = None,
        previous_value: str | None = None,
    ) -> TrajectoryBelief:
        """
        Log a belief update.

        Args:
            subject: What the belief is about
            predicate: The relationship or property
            object: The value or target
            confidence: Confidence 0.0-1.0
            source: How belief was formed
            reasoning: LLM reasoning
            source_observation_id: Triggering observation
            previous_value: Previous value if updating

        Returns:
            TrajectoryBelief instance
        """
        if not self.current_step:
            raise ValueError("Cannot log belief without active step")

        if isinstance(source, str):
            source = BeliefSource(source)

        belief = TrajectoryBelief(
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
            source=source,
            source_observation_id=source_observation_id,
            previous_value=previous_value,
            reasoning=reasoning,
        )

        self.current_step.beliefs_updated.append(belief)
        return belief

    def log_goal(
        self,
        goal_type: str | GoalType,
        description: str,
        priority: int,
        target: dict[str, Any],
        status: str | GoalStatus = GoalStatus.ACTIVE,
        triggered_by_beliefs: list[UUID] | None = None,
        parent_goal_id: UUID | None = None,
        reasoning: str = "",
        is_update: bool = False,
    ) -> TrajectoryGoal:
        """
        Log a goal formation or update.

        Args:
            goal_type: Type of goal
            description: Goal description
            priority: Priority 1-10
            target: Goal target metrics
            status: Goal status
            triggered_by_beliefs: Belief IDs that triggered this
            parent_goal_id: Parent goal if this is sub-goal
            reasoning: Why this goal was formed
            is_update: Whether this is updating existing goal

        Returns:
            TrajectoryGoal instance
        """
        if not self.current_step:
            raise ValueError("Cannot log goal without active step")

        if isinstance(goal_type, str):
            goal_type = GoalType(goal_type)
        if isinstance(status, str):
            status = GoalStatus(status)

        goal = TrajectoryGoal(
            goal_type=goal_type,
            description=description,
            priority=priority,
            target=target,
            status=status,
            triggered_by_beliefs=triggered_by_beliefs or [],
            parent_goal_id=parent_goal_id,
            reasoning=reasoning,
        )

        if is_update:
            self.current_step.goals_updated.append(goal)
        else:
            self.current_step.goals_formed.append(goal)

        return goal

    def log_intention(
        self,
        intention_type: str | IntentionType,
        description: str,
        plan: dict[str, Any],
        goal_id: UUID,
        priority: int = 5,
        status: str | IntentionStatus = IntentionStatus.PLANNED,
        depends_on: list[UUID] | None = None,
        alternatives_considered: list[dict[str, Any]] | None = None,
        selection_rationale: str = "",
    ) -> TrajectoryIntention:
        """
        Log an intention/plan.

        Args:
            intention_type: Type of intention
            description: What will be done
            plan: Structured plan
            goal_id: Goal this serves
            priority: Priority 1-10
            status: Intention status
            depends_on: Dependency intention IDs
            alternatives_considered: Other plans considered
            selection_rationale: Why this plan chosen

        Returns:
            TrajectoryIntention instance
        """
        if not self.current_step:
            raise ValueError("Cannot log intention without active step")

        if isinstance(intention_type, str):
            intention_type = IntentionType(intention_type)
        if isinstance(status, str):
            status = IntentionStatus(status)

        intention = TrajectoryIntention(
            intention_type=intention_type,
            description=description,
            plan=plan,
            status=status,
            priority=priority,
            goal_id=goal_id,
            depends_on=depends_on or [],
            alternatives_considered=alternatives_considered or [],
            selection_rationale=selection_rationale,
        )

        self.current_step.intentions_planned.append(intention)
        return intention

    def log_action(
        self,
        intention_id: UUID,
        action_type: str,
        capability_used: str,
        parameters: dict[str, Any],
        execution_started_at: datetime | None = None,
        execution_completed_at: datetime | None = None,
        execution_duration_ms: float | None = None,
        retries: int = 0,
    ) -> TrajectoryAction:
        """
        Log an action execution.

        Args:
            intention_id: Intention this belongs to
            action_type: Type of action
            capability_used: Capability that executed this
            parameters: Action parameters (PII-safe)
            execution_started_at: When execution started
            execution_completed_at: When execution completed
            execution_duration_ms: Duration in milliseconds
            retries: Number of retries

        Returns:
            TrajectoryAction instance
        """
        if not self.current_step:
            raise ValueError("Cannot log action without active step")

        action = TrajectoryAction(
            intention_id=intention_id,
            action_type=action_type,
            capability_used=capability_used,
            parameters=parameters,
            execution_started_at=execution_started_at,
            execution_completed_at=execution_completed_at,
            execution_duration_ms=execution_duration_ms,
            retries=retries,
        )

        self.current_step.actions_executed.append(action)
        return action

    def log_outcome(
        self,
        action_id: UUID,
        status: str | OutcomeStatus,
        result: dict[str, Any],
        impact: dict[str, Any] | None = None,
        error: str | None = None,
        learning: str | None = None,
    ) -> TrajectoryOutcome:
        """
        Log an action outcome.

        Args:
            action_id: Action this is outcome of
            status: Outcome status
            result: Actual results
            impact: Impact on world state
            error: Error message if failed
            learning: What was learned

        Returns:
            TrajectoryOutcome instance
        """
        if not self.current_step:
            raise ValueError("Cannot log outcome without active step")

        if isinstance(status, str):
            status = OutcomeStatus(status)

        outcome = TrajectoryOutcome(
            action_id=action_id,
            status=status,
            result=result,
            impact=impact or {},
            error=error,
            learning=learning,
        )

        self.current_step.outcomes.append(outcome)
        return outcome

    # ==========================================
    # Access Methods
    # ==========================================

    def get_current_session(self) -> TrajectorySession | None:
        """Get current active session."""
        return self.current_session

    def get_current_trajectory(self) -> BDITrajectory | None:
        """Get current active trajectory."""
        return self.current_trajectory

    def get_current_step(self) -> TrajectoryStep | None:
        """Get current active step."""
        return self.current_step

    def get_completed_trajectories(self) -> list[BDITrajectory]:
        """Get all completed trajectories in this session."""
        return self.completed_trajectories

    def get_session_summary(self) -> dict[str, Any] | None:
        """Get summary of current session."""
        if not self.current_session:
            return None

        return {
            "session_id": str(self.current_session.session_id),
            "employee_id": str(self.employee_id),
            "started_at": self.current_session.started_at.isoformat(),
            "session_type": self.current_session.session_type,
            "completed_trajectories": len(self.completed_trajectories),
            "total_steps": sum(len(t.steps) for t in self.completed_trajectories),
        }
