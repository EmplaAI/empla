"""
empla.core.loop.execution - Proactive Execution Loop Implementation

The main continuous autonomous operation loop.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, Field

from empla.core.hooks import (
    HOOK_AFTER_BELIEF_UPDATE,
    HOOK_AFTER_INTENTION_EXECUTION,
    HOOK_AFTER_PERCEPTION,
    HOOK_AFTER_REFLECTION,
    HOOK_AFTER_STRATEGIC_PLANNING,
    HOOK_BEFORE_BELIEF_UPDATE,
    HOOK_BEFORE_INTENTION_EXECUTION,
    HOOK_BEFORE_PERCEPTION,
    HOOK_BEFORE_STRATEGIC_PLANNING,
    HOOK_CYCLE_END,
    HOOK_CYCLE_START,
    HookRegistry,
)
from empla.core.loop.models import (
    IntentionResult,
    LoopConfig,
    Observation,
    PerceptionResult,
)
from empla.models.employee import Employee

if TYPE_CHECKING:
    from empla.employees.identity import EmployeeIdentity
    from empla.llm import LLMService

logger = logging.getLogger(__name__)


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
    """LLM recommendation for goal changes."""

    new_goals: list[dict[str, Any]] = Field(default_factory=list, description="New goals to create")
    goals_to_abandon: list[str] = Field(
        default_factory=list, description="Goal IDs to abandon with reasons"
    )
    priority_adjustments: list[dict[str, Any]] = Field(
        default_factory=list, description="Goals needing priority changes"
    )
    reasoning: str = Field(..., description="Reasoning for recommendations")


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

    async def start_intention(self, intention: Any) -> None:
        """Mark intention as in progress"""
        ...

    async def complete_intention(self, intention: Any, result: IntentionResult) -> None:
        """Mark intention as completed"""
        ...

    async def fail_intention(self, intention: Any, error: str) -> None:
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


class ToolSourceProtocol(Protocol):
    """Protocol for tool sources (ToolRouter).

    Defines the interface the agentic loop uses for tool discovery and execution.
    """

    def get_all_tool_schemas(self, employee_id: UUID) -> list[dict[str, Any]]:
        """Get all available tool schemas for the employee."""
        ...

    async def execute_tool_call(
        self, employee_id: UUID, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Execute a tool call and return an ActionResult."""
        ...

    def get_enabled_capabilities(self, employee_id: UUID) -> list[str]:
        """List enabled capabilities for the employee."""
        ...


# ============================================================================
# Proactive Execution Loop
# ============================================================================


class ProactiveExecutionLoop:
    """
    The continuous autonomous operation loop.

    This is the "heartbeat" of empla - what makes employees truly autonomous.

    The loop continuously:
    1. PERCEIVE: Gather observations from environment
    2. UPDATE BELIEFS: Process observations into world model updates
    3. STRATEGIC REASONING: Form/abandon goals, generate strategies (when needed)
    4. GOAL MANAGEMENT: Update goal progress
    5. INTENTION EXECUTION: Execute highest priority work
    6. LEARNING: Reflect on outcomes and learn

    Example:
        >>> loop = ProactiveExecutionLoop(
        ...     employee=employee,
        ...     beliefs=belief_system,
        ...     goals=goal_system,
        ...     intentions=intention_stack,
        ...     memory=memory_system,
        ...     config=LoopConfig()
        ... )
        >>> await loop.start()
    """

    def __init__(
        self,
        employee: Employee,
        beliefs: BeliefSystemProtocol,
        goals: GoalSystemProtocol,
        intentions: IntentionStackProtocol,
        memory: MemorySystemProtocol,
        llm_service: "LLMService | None" = None,
        config: LoopConfig | None = None,
        status_checker: Callable[[Employee], Awaitable[None]] | None = None,
        hooks: HookRegistry | None = None,
        tool_router: ToolSourceProtocol | None = None,
        identity: "EmployeeIdentity | None" = None,
    ) -> None:
        """
        Create and initialize a ProactiveExecutionLoop.

        Parameters:
            employee: The digital employee instance this loop will run for.
            beliefs: Belief system used to update and query the agent's world model.
            goals: Goal system responsible for providing and updating active goals.
            intentions: Intention stack managing selection, start, completion, and failure of intentions.
            memory: Memory system used for recording and retrieving episodic/semantic/procedural data.
            llm_service: Optional LLM service for strategic reasoning and plan generation.
            config: Optional loop configuration object; when omitted defaults are applied.
            status_checker: Optional async callback that refreshes employee.status
                from the database. When provided, called at the start of each cycle
                so the loop can react to external status changes (e.g. pause-via-DB).
            hooks: Optional hook registry for lifecycle event callbacks.
            tool_router: Optional unified tool source for tool discovery and execution.
            identity: Optional EmployeeIdentity providing name, role, personality,
                and goals context for LLM prompts.
        """
        self.employee = employee
        self.beliefs = beliefs
        self.goals = goals
        self.intentions = intentions
        self.memory = memory
        self.tool_router = tool_router
        self.llm_service = llm_service
        self._status_checker = status_checker
        self._hooks = hooks or HookRegistry()
        self._identity = identity
        if identity is not None:
            self._identity_prompt: str | None = identity.to_system_prompt()
            logger.debug(
                "Identity context loaded for LLM prompts",
                extra={"employee_id": str(employee.id), "identity_role": identity.role},
            )
        else:
            self._identity_prompt = None
            logger.warning(
                "No identity context provided; LLM calls will use generic prompts",
                extra={"employee_id": str(employee.id)},
            )

        # Configuration
        self.config = config or LoopConfig()
        self.cycle_interval = self.config.cycle_interval_seconds
        self.error_backoff_interval = self.config.error_backoff_seconds

        # State
        self.is_running = False
        self.cycle_count = 0
        self.last_strategic_planning: datetime | None = None
        self.last_deep_reflection: datetime | None = None

        logger.info(
            f"Proactive loop initialized for {employee.name}",
            extra={
                "employee_id": str(employee.id),
                "cycle_interval": self.cycle_interval,
                "has_tool_router": tool_router is not None,
                "has_llm_service": llm_service is not None,
                "config": self.config.model_dump(),
            },
        )

    async def _refresh_identity_prompt(self) -> None:
        """Recompute _identity_prompt with current goals from the GoalSystem."""
        if self._identity is None:
            return
        try:
            active_goals = await self.goals.get_active_goals()
            goals_data = [
                {
                    "description": getattr(g, "description", "Unknown goal"),
                    "priority": getattr(g, "priority", "?"),
                }
                for g in active_goals
            ]
            self._identity.goals_summary = self._identity._format_goals(goals_data)
            self._identity_prompt = self._identity.to_system_prompt()
        except Exception:
            logger.warning(
                "Failed to refresh identity goals; using cached prompt",
                extra={"employee_id": str(self.employee.id)},
                exc_info=True,
            )

    async def start(self) -> None:
        """
        Start the proactive execution loop.

        This begins the continuous autonomous operation. The loop runs until
        either stop() is called or the employee is deactivated.
        """
        if self.is_running:
            logger.warning(f"Loop already running for employee {self.employee.id}")
            return

        self.is_running = True

        logger.info(
            f"Starting proactive loop for {self.employee.name}",
            extra={
                "employee_id": str(self.employee.id),
                "cycle_interval": self.cycle_interval,
            },
        )

        await self.run_continuous_loop()

    async def stop(self) -> None:
        """
        Stop the proactive execution loop.

        Gracefully stops the loop after the current cycle completes.
        """
        self.is_running = False

        logger.info(
            f"Stopping proactive loop for {self.employee.name}",
            extra={"employee_id": str(self.employee.id), "total_cycles": self.cycle_count},
        )

    async def run_continuous_loop(self) -> None:
        """
        Main continuous execution loop.

        This runs until employee is deactivated or loop is stopped.
        Implements the full BDI reasoning cycle in each iteration.

        Status handling:
        - "active": run a normal BDI cycle
        - "paused": sleep 5s and recheck (pause-via-DB pattern)
        - anything else ("stopped", "terminated"): exit the loop
        """
        while self.is_running:
            # Refresh employee status from DB if checker provided
            if self._status_checker:
                try:
                    await self._status_checker(self.employee)
                except Exception:
                    logger.warning(
                        "Status checker failed, continuing with current status",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )

            # Handle paused status: sleep and recheck
            if self.employee.status == "paused":
                await self._sleep_interruptible(5.0)
                continue

            # Exit on any non-active status (stopped, terminated, etc.)
            if self.employee.status != "active":
                break

            try:
                cycle_start = time.time()
                self.cycle_count += 1
                await self._refresh_identity_prompt()

                logger.debug(
                    f"Loop cycle {self.cycle_count} starting",
                    extra={"employee_id": str(self.employee.id)},
                )

                await self._hooks.emit(
                    HOOK_CYCLE_START,
                    employee_id=self.employee.id,
                    cycle_count=self.cycle_count,
                )

                await self._execute_bdi_phases()

                # ============ DEEP REFLECTION ============
                # Periodic deep reflection (less frequent)
                if self.should_run_deep_reflection():
                    await self.deep_reflection_cycle()
                    self.last_deep_reflection = datetime.now(UTC)

                # ============ METRICS ============
                cycle_duration = time.time() - cycle_start

                # TODO: Add actual metrics collection (Prometheus, etc.)
                # metrics.histogram("proactive_loop.cycle_duration", cycle_duration)
                # metrics.gauge("proactive_loop.cycle_count", self.cycle_count)

                logger.debug(
                    f"Loop cycle {self.cycle_count} complete",
                    extra={
                        "employee_id": str(self.employee.id),
                        "duration_seconds": cycle_duration,
                    },
                )

                await self._hooks.emit(
                    HOOK_CYCLE_END,
                    employee_id=self.employee.id,
                    cycle_count=self.cycle_count,
                    duration_seconds=cycle_duration,
                    success=True,
                )

                # ============ SLEEP ============
                # Wait before next cycle (check is_running flag during sleep for prompt shutdown)
                if not self.is_running:
                    break

                await self._sleep_interruptible(float(self.cycle_interval))

            except Exception as e:
                # NEVER let loop crash - log error and continue
                logger.error(
                    f"Error in proactive loop cycle {self.cycle_count}",
                    exc_info=True,
                    extra={
                        "employee_id": str(self.employee.id),
                        "cycle_count": self.cycle_count,
                        "error": str(e),
                    },
                )

                try:
                    cycle_duration = time.time() - cycle_start
                    await self._hooks.emit(
                        HOOK_CYCLE_END,
                        employee_id=self.employee.id,
                        cycle_count=self.cycle_count,
                        duration_seconds=cycle_duration,
                        success=False,
                    )
                except Exception:
                    logger.error(
                        "Failed to emit cycle_end hook in error handler",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )

                # TODO: Add metrics for errors
                # metrics.increment("proactive_loop.errors")

                # Back off on errors (check is_running flag during sleep for prompt shutdown)
                if not self.is_running:
                    break

                await self._sleep_interruptible(float(self.error_backoff_interval))

        # Determine exit reason before clearing flag
        if not self.is_running:
            exit_reason = "stopped"
        elif self.employee.status == "paused":
            exit_reason = "paused"  # shouldn't normally reach here
        else:
            exit_reason = f"employee_{self.employee.status}"

        # Clear running flag on natural exit (employee deactivated, etc.)
        # This ensures the loop can be restarted after natural shutdown
        self.is_running = False

        logger.info(
            f"Proactive loop ended for {self.employee.name}",
            extra={
                "employee_id": str(self.employee.id),
                "total_cycles": self.cycle_count,
                "reason": exit_reason,
            },
        )

    async def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep in small increments so stop() takes effect promptly."""
        remaining = seconds
        while remaining > 0 and self.is_running:
            chunk = min(0.1, remaining)
            await asyncio.sleep(chunk)
            remaining -= chunk

    async def _execute_bdi_phases(self) -> IntentionResult | None:
        """Execute the core BDI phases with hook emissions.

        Performs perception, belief updates, strategic planning,
        goal management, intention execution, and reflection.
        Emits hooks at each phase boundary.

        Does not emit HOOK_CYCLE_START or HOOK_CYCLE_END — callers
        are responsible for those.

        Returns:
            IntentionResult if work was done, None otherwise.

        Raises:
            Exception: Propagated from any phase failure.
        """
        employee_id = self.employee.id

        # ============ PERCEIVE ============
        await self._hooks.emit(
            HOOK_BEFORE_PERCEPTION,
            employee_id=employee_id,
            cycle_count=self.cycle_count,
        )

        perception_result = await self.perceive_environment()

        await self._hooks.emit(
            HOOK_AFTER_PERCEPTION,
            employee_id=employee_id,
            cycle_count=self.cycle_count,
            perception_result=perception_result,
        )

        logger.info(
            f"Perception complete: {len(perception_result.observations)} observations",
            extra={
                "employee_id": str(employee_id),
                "observations": len(perception_result.observations),
                "opportunities": perception_result.opportunities_detected,
                "problems": perception_result.problems_detected,
            },
        )

        # ============ UPDATE BELIEFS ============
        await self._hooks.emit(
            HOOK_BEFORE_BELIEF_UPDATE,
            employee_id=employee_id,
            observations=perception_result.observations,
        )

        changed_beliefs = await self.beliefs.update_beliefs(
            perception_result.observations, identity_context=self._identity_prompt
        )

        await self._hooks.emit(
            HOOK_AFTER_BELIEF_UPDATE,
            employee_id=employee_id,
            changed_beliefs=changed_beliefs,
        )

        logger.info(
            f"Beliefs updated: {len(changed_beliefs)} changes",
            extra={
                "employee_id": str(employee_id),
                "changed_beliefs": len(changed_beliefs),
            },
        )

        # ============ STRATEGIC REASONING ============
        if self.should_run_strategic_planning(changed_beliefs):
            await self._hooks.emit(
                HOOK_BEFORE_STRATEGIC_PLANNING,
                employee_id=employee_id,
            )

            await self.strategic_planning_cycle()
            self.last_strategic_planning = datetime.now(UTC)

            await self._hooks.emit(
                HOOK_AFTER_STRATEGIC_PLANNING,
                employee_id=employee_id,
            )

        # ============ GOAL MANAGEMENT ============
        pursuing_goals = await self.goals.get_pursuing_goals()
        for goal in pursuing_goals:
            progress = self._evaluate_goal_progress_from_beliefs(
                goal=goal,
                changed_beliefs=changed_beliefs,
            )
            if progress:
                await self.goals.update_goal_progress(goal.id, progress)
                await self._check_goal_achievement(goal, progress)

        logger.debug(
            f"Goal progress evaluated for {len(pursuing_goals)} pursuing goals",
            extra={"employee_id": str(employee_id)},
        )

        # ============ INTENTION EXECUTION ============
        await self._hooks.emit(
            HOOK_BEFORE_INTENTION_EXECUTION,
            employee_id=employee_id,
        )

        result = await self.execute_intentions()

        await self._hooks.emit(
            HOOK_AFTER_INTENTION_EXECUTION,
            employee_id=employee_id,
            result=result,
        )

        # ============ LEARNING ============
        if result:
            await self.reflection_cycle(result)

            await self._hooks.emit(
                HOOK_AFTER_REFLECTION,
                employee_id=employee_id,
                result=result,
            )

        return result

    async def _run_cycle(self) -> IntentionResult | None:
        """
        Execute a single BDI reasoning cycle.

        This is the core of the proactive loop, extracted for use by
        DigitalEmployee.run_once() for testing and manual control.
        Lifecycle hooks are emitted at each phase boundary.

        Returns:
            IntentionResult if work was done, None if no work to do or cycle
            completed without intention execution.

        Raises:
            Exception: If any phase fails critically (logged but not suppressed
                      to allow caller to handle). HOOK_CYCLE_END with
                      success=False is emitted before re-raising.
        """
        cycle_start = time.time()
        self.cycle_count += 1
        await self._refresh_identity_prompt()

        logger.debug(
            f"Single cycle {self.cycle_count} starting",
            extra={"employee_id": str(self.employee.id)},
        )

        try:
            await self._hooks.emit(
                HOOK_CYCLE_START,
                employee_id=self.employee.id,
                cycle_count=self.cycle_count,
            )

            result = await self._execute_bdi_phases()

            cycle_duration = time.time() - cycle_start
            logger.debug(
                f"Single cycle {self.cycle_count} complete",
                extra={
                    "employee_id": str(self.employee.id),
                    "duration_seconds": cycle_duration,
                    "had_work": result is not None,
                },
            )

            await self._hooks.emit(
                HOOK_CYCLE_END,
                employee_id=self.employee.id,
                cycle_count=self.cycle_count,
                duration_seconds=cycle_duration,
                success=True,
            )

        except Exception:
            try:
                await self._hooks.emit(
                    HOOK_CYCLE_END,
                    employee_id=self.employee.id,
                    cycle_count=self.cycle_count,
                    duration_seconds=time.time() - cycle_start,
                    success=False,
                )
            except Exception:
                logger.error(
                    "Failed to emit cycle_end hook during error handling",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )
            raise
        else:
            return result

    # ========================================================================
    # Phase 1: Perception
    # ========================================================================

    async def perceive_environment(self) -> PerceptionResult:
        """
        Collects observations from the environment via agentic perception.

        Uses LLM-driven perception when LLM and tools are available.
        Returns empty result otherwise.

        Returns:
            PerceptionResult with observations, opportunity/problem/risk counts,
            duration, and sources checked.
        """
        start_time = time.time()

        if self.llm_service is not None and self.tool_router is not None:
            tool_schemas = self.tool_router.get_all_tool_schemas(self.employee.id)
            if tool_schemas:
                try:
                    result = await self._perceive_agentic(tool_schemas)
                    duration_ms = max(0.01, (time.time() - start_time) * 1000)
                    result.perception_duration_ms = duration_ms
                    return result
                except Exception:
                    logger.warning(
                        "Agentic perception failed",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )

        # No LLM or no tools — return empty result
        duration_ms = max(0.01, (time.time() - start_time) * 1000)
        return PerceptionResult(
            observations=[],
            perception_duration_ms=duration_ms,
        )

    async def _perceive_agentic(self, tool_schemas: list[dict[str, Any]]) -> PerceptionResult:
        """LLM-driven perception: check environment based on goals.

        The LLM receives current goals and available tools, then decides
        what to check. This replaces hardcoded perceive() methods with
        goal-aware, adaptive environment scanning.

        Args:
            tool_schemas: Available tool schemas for the LLM.

        Returns:
            PerceptionResult with observations from tool calls.
        """
        from empla.llm.models import Message

        # Build context for perception
        goals_context = await self._format_goals_for_perception()
        beliefs_context = await self._format_recent_beliefs_for_perception()

        system_prompt = self._build_perception_system_prompt()
        user_prompt = (
            f"Check your environment for changes relevant to your goals.\n\n"
            f"Current goals:\n{goals_context}\n\n"
            f"Recent beliefs:\n{beliefs_context}\n\n"
            f"Use the available tools to check for new information. "
            f"Focus on what's most relevant to your highest-priority goals. "
            f"Be efficient — don't check everything every time."
        )

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        observations: list[Observation] = []
        sources_checked: set[str] = set()
        max_perception_iterations = self.config.max_perception_iterations

        for iteration in range(max_perception_iterations):
            try:
                response = await self.llm_service.generate_with_tools(
                    messages=messages,
                    tools=tool_schemas,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except Exception:
                logger.exception(
                    "LLM call failed during agentic perception",
                    extra={
                        "employee_id": str(self.employee.id),
                        "iteration": iteration,
                    },
                )
                break

            if not response.tool_calls:
                break

            # Add assistant message to conversation
            assistant_msg = Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_msg)

            # Execute each tool call
            if self.tool_router is None:
                break

            for tc in response.tool_calls:
                source = tc.name.split(".")[0] if "." in tc.name else tc.name
                sources_checked.add(source)

                try:
                    result = await self.tool_router.execute_tool_call(
                        self.employee.id, tc.name, tc.arguments
                    )
                    result_output = result.output if hasattr(result, "output") else result
                    result_error = getattr(result, "error", None)
                    result_success = getattr(result, "success", True)

                    obs_content: dict[str, Any] = {
                        "tool_result": result_output,
                        "arguments": tc.arguments,
                    }
                    if result_error:
                        obs_content["error"] = result_error

                    observations.append(
                        Observation(
                            employee_id=self.employee.id,
                            tenant_id=self.employee.tenant_id,
                            observation_type=tc.name,
                            source=source,
                            content=obs_content,
                            priority=5,
                            requires_action=False,
                        )
                    )

                    result_payload: dict[str, Any] = {
                        "success": result_success,
                        "output": result_output,
                    }
                    if result_error:
                        result_payload["error"] = result_error
                    result_content = json.dumps(result_payload, default=str)
                except Exception as e:
                    logger.exception(
                        "Tool call %s failed during perception",
                        tc.name,
                        extra={"employee_id": str(self.employee.id), "tool_name": tc.name},
                    )
                    result_content = json.dumps({"success": False, "error": str(e)})

                messages.append(Message(role="tool", content=result_content, tool_call_id=tc.id))

        # Classify observations
        opportunities = sum(
            1 for obs in observations if "opportunity" in obs.observation_type.lower()
        )
        problems = sum(
            1
            for obs in observations
            if "problem" in obs.observation_type.lower() or "error" in obs.observation_type.lower()
        )
        risks = sum(
            1 for obs in observations if "risk" in obs.observation_type.lower() or obs.priority >= 9
        )

        logger.info(
            f"Agentic perception: {len(observations)} observations from {len(sources_checked)} sources",
            extra={
                "employee_id": str(self.employee.id),
                "observations": len(observations),
                "sources": list(sources_checked),
            },
        )

        return PerceptionResult(
            observations=observations,
            opportunities_detected=opportunities,
            problems_detected=problems,
            risks_detected=risks,
            perception_duration_ms=0.01,  # Updated by caller
            sources_checked=list(sources_checked),
        )

    def _build_perception_system_prompt(self) -> str:
        """Build system prompt for agentic perception."""
        perception_instructions = (
            "You are the perception system for a digital employee. "
            "Your job is to check the environment for changes relevant to current goals. "
            "Use the available tools to gather information. "
            "Be efficient — focus on the most important sources first."
        )
        if self._identity_prompt:
            return f"{self._identity_prompt}\n\n{perception_instructions}"
        return perception_instructions

    async def _format_goals_for_perception(self) -> str:
        """Format current goals for the perception prompt."""
        try:
            active_goals = await self.goals.get_active_goals()
            if not active_goals:
                return "No active goals."
            lines = []
            for g in active_goals:
                desc = getattr(g, "description", "Unknown")
                priority = getattr(g, "priority", "?")
                lines.append(f"- [{priority}] {desc}")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to format goals for perception: %s", e)
            return "Unable to load goals."

    async def _format_recent_beliefs_for_perception(self) -> str:
        """Format recent beliefs for context in perception prompt."""
        try:
            beliefs = await self.beliefs.get_all_beliefs(min_confidence=0.5)
            if not beliefs:
                return "No current beliefs."
            lines = []
            for b in beliefs[:10]:
                subject = getattr(b, "subject", "?")
                predicate = getattr(b, "predicate", "?")
                confidence = getattr(b, "confidence", "?")
                lines.append(f"- {subject}.{predicate} (confidence: {confidence})")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to format beliefs for perception: %s", e)
            return "Unable to load beliefs."

    # ========================================================================
    # Phase 2: Strategic Reasoning
    # ========================================================================

    def should_run_strategic_planning(self, changed_beliefs: list[BeliefChange]) -> bool:
        """
        Decide if belief changes warrant strategic replanning.

        Strategic planning is expensive (multiple LLM calls), so only run when:
        1. High-importance belief changed significantly
        2. Belief related to current intentions changed
        3. Belief about goal achievability changed
        4. Scheduled time for strategic planning

        Args:
            changed_beliefs: List of belief changes from this cycle

        Returns:
            True if strategic planning should run, False otherwise
        """
        # 1. Check if scheduled time for strategic planning
        if self.last_strategic_planning is None:
            # Never run strategic planning - do it now
            return True

        hours_since_last_planning = (
            datetime.now(UTC) - self.last_strategic_planning
        ).total_seconds() / 3600

        if hours_since_last_planning >= self.config.strategic_planning_interval_hours:
            logger.info(
                "Triggering strategic planning: scheduled interval reached",
                extra={
                    "employee_id": str(self.employee.id),
                    "hours_since_last": hours_since_last_planning,
                },
            )
            return True

        # 2. Check if significant belief changes
        if self.config.force_strategic_planning_on_significant_change:
            # High-importance belief changed significantly
            important_changed = any(
                b.importance > 0.7 and abs(b.new_confidence - b.old_confidence) > 0.3
                for b in changed_beliefs
            )

            if important_changed:
                logger.info(
                    "Triggering strategic planning: significant belief change",
                    extra={"employee_id": str(self.employee.id)},
                )
                return True

            # Belief about goal achievability changed
            goal_beliefs_changed = any(
                b.predicate in ["achievable", "blocked", "deadline", "priority"]
                for b in changed_beliefs
            )

            if goal_beliefs_changed:
                logger.info(
                    "Triggering strategic planning: goal-related belief changed",
                    extra={"employee_id": str(self.employee.id)},
                )
                return True

        return False

    def _evaluate_goal_progress_from_beliefs(
        self,
        goal: Any,
        changed_beliefs: list[BeliefChange],
    ) -> dict[str, Any]:
        """
        Evaluate goal progress based on recently changed beliefs.

        Matches goal target metrics to belief subject/predicate patterns:
        - "pipeline_coverage" matches beliefs with subject containing "pipeline"
          and predicate containing "coverage"
        - "deals_closed" matches subject containing "deals" and predicate "closed"

        Args:
            goal: The goal to evaluate progress for
            changed_beliefs: List of belief changes from this cycle

        Returns:
            Progress dict to update the goal with, empty if no matching beliefs
        """
        target = getattr(goal, "target", {}) or {}
        metric = target.get("metric", "")

        if not metric:
            return {}

        # Parse metric into subject/predicate patterns
        # Convention: underscore-separated metric maps to subject_predicate
        parts = metric.lower().split("_", 1)
        if len(parts) < 2:
            # Single word metric - match as subject or predicate
            subject_pattern = parts[0]
            predicate_pattern = parts[0]
        else:
            subject_pattern = parts[0]
            predicate_pattern = parts[1]

        progress: dict[str, Any] = {}

        for belief_change in changed_beliefs:
            # Check if belief matches goal metric
            subject_match = subject_pattern in belief_change.subject.lower()
            predicate_match = predicate_pattern in belief_change.predicate.lower()

            if subject_match and predicate_match:
                # Extract value from belief
                # BeliefChangeResult has a .belief attribute with the actual Belief
                belief = getattr(belief_change, "belief", None)
                if belief is not None:
                    belief_object = getattr(belief, "object", {}) or {}
                    value = belief_object.get("value")

                    if value is not None:
                        # Update progress with the metric value
                        progress[metric] = value
                        progress["last_belief_update"] = belief_change.subject
                        progress["belief_confidence"] = belief_change.new_confidence

                        logger.debug(
                            f"Goal progress updated from belief: {metric}={value}",
                            extra={
                                "employee_id": str(self.employee.id),
                                "goal_id": str(goal.id),
                                "belief_subject": belief_change.subject,
                                "belief_predicate": belief_change.predicate,
                            },
                        )
                        break  # Use first matching belief

        return progress

    async def _check_goal_achievement(
        self,
        goal: Any,
        progress: dict[str, Any],
    ) -> None:
        """
        Check if a goal's target has been met and complete it if so.

        For "maintain" goals (ongoing targets), completion triggers a new
        goal cycle rather than permanent completion — the goal is re-activated
        so it continues to be monitored.

        Args:
            goal: The goal to check
            progress: The newly updated progress data
        """
        target = getattr(goal, "target", {}) or {}
        metric = target.get("metric", "")
        target_value = target.get("value")

        if not metric or target_value is None:
            return

        current_value = progress.get(metric)
        if current_value is None:
            return

        try:
            achieved = float(current_value) >= float(target_value)
        except (ValueError, TypeError):
            logger.warning(
                "Non-numeric goal target or progress: metric=%s current=%r target=%r",
                metric,
                current_value,
                target_value,
                extra={"employee_id": str(self.employee.id), "goal_id": str(goal.id)},
            )
            return

        if not achieved:
            return

        goal_type = getattr(goal, "goal_type", "")

        try:
            if goal_type == "maintain":
                # "maintain" goals stay active — log that target is met
                logger.info(
                    "Maintain goal target met: %s=%s (target=%s)",
                    metric,
                    current_value,
                    target_value,
                    extra={
                        "employee_id": str(self.employee.id),
                        "goal_id": str(goal.id),
                        "goal_type": "maintain",
                    },
                )
            else:
                # Achievement/one-time goals — mark completed
                await self.goals.complete_goal(goal.id, progress)
                logger.info(
                    "Goal completed: %s (metric %s=%s reached target %s)",
                    goal.description,
                    metric,
                    current_value,
                    target_value,
                    extra={
                        "employee_id": str(self.employee.id),
                        "goal_id": str(goal.id),
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to complete goal %s: %s",
                goal.id,
                e,
                exc_info=True,
                extra={"employee_id": str(self.employee.id), "goal_id": str(goal.id)},
            )

    async def strategic_planning_cycle(self) -> None:
        """
        Deep strategic reasoning cycle.

        This is computationally expensive (multiple LLM calls) and runs less
        frequently than tactical execution.

        Performs:
        1. Comprehensive situation analysis
        2. Gap analysis (current vs desired state)
        3. Root cause analysis
        4. Opportunity detection
        5. Strategy generation and evaluation
        6. Goal formation/abandonment
        7. Strategy documentation
        """
        logger.info(
            "Strategic planning cycle starting",
            extra={"employee_id": str(self.employee.id)},
        )

        start_time = time.time()

        try:
            # ============ STEP 1: Gather Situation ============
            # Get current beliefs, goals, and capabilities
            beliefs = await self.beliefs.get_all_beliefs(min_confidence=0.5)
            active_goals = await self.goals.get_active_goals()
            available_capabilities = self._get_available_capabilities()

            logger.debug(
                "Strategic planning: gathered situation",
                extra={
                    "employee_id": str(self.employee.id),
                    "beliefs_count": len(beliefs),
                    "active_goals_count": len(active_goals),
                    "capabilities_count": len(available_capabilities),
                },
            )

            # ============ STEP 2: LLM Situation Analysis ============
            if self.llm_service:
                situation_analysis = await self._analyze_situation_with_llm(
                    beliefs=beliefs,
                    goals=active_goals,
                    capabilities=available_capabilities,
                )

                logger.info(
                    "Strategic planning: situation analyzed",
                    extra={
                        "employee_id": str(self.employee.id),
                        "gaps_identified": len(situation_analysis.gaps),
                        "opportunities_identified": len(situation_analysis.opportunities),
                        "problems_identified": len(situation_analysis.problems),
                        "recommended_focus": situation_analysis.recommended_focus,
                    },
                )

                # ============ STEP 3: Goal Management ============
                await self._manage_goals_from_analysis(
                    situation_analysis=situation_analysis,
                    active_goals=active_goals,
                )
                # Goals changed — refresh identity prompt so subsequent LLM calls
                # reflect the current goal set.
                await self._refresh_identity_prompt()

            # ============ STEP 4: Generate Plans for Goals Without Intentions ============
            await self._generate_plans_for_unplanned_goals(
                goals=active_goals,
                beliefs=beliefs,
                capabilities=available_capabilities,
            )

            # ============ STEP 5: Document in Episodic Memory ============
            await self._record_strategic_planning_episode(
                beliefs_count=len(beliefs),
                goals_count=len(active_goals),
            )

        except Exception as e:
            logger.error(
                "Strategic planning cycle failed",
                exc_info=True,
                extra={"employee_id": str(self.employee.id), "error": str(e)},
            )

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Strategic planning cycle complete",
            extra={"employee_id": str(self.employee.id), "duration_ms": duration_ms},
        )

        # Update last strategic planning time
        self.last_strategic_planning = datetime.now(UTC)

    def _get_available_capabilities(self) -> list[str]:
        """Get list of available capability/integration names."""
        if not self.tool_router:
            return []

        try:
            return self.tool_router.get_enabled_capabilities(self.employee.id)
        except Exception as e:
            logger.warning(
                f"Failed to get capabilities: {e}", extra={"employee_id": str(self.employee.id)}
            )
            return []

    async def _analyze_situation_with_llm(
        self,
        beliefs: list[Any],
        goals: list[Any],
        capabilities: list[str],
    ) -> SituationAnalysis:
        """Use LLM to analyze current situation."""
        if not self.llm_service:
            return SituationAnalysis(
                current_state_summary="No LLM service available",
                gaps=[],
                opportunities=[],
                problems=[],
                recommended_focus="Continue with current goals",
            )

        # Format beliefs for prompt
        beliefs_text = self._format_beliefs_for_llm(beliefs)
        goals_text = self._format_goals_for_llm(goals)

        base_prompt = """Analyze your current beliefs (world model) and goals to identify:
1. Gaps between current state and desired outcomes
2. Opportunities that could be pursued
3. Problems requiring immediate attention
4. What you should focus on next

Be specific and actionable in your analysis."""

        system_prompt = (
            f"{self._identity_prompt}\n\n{base_prompt}"
            if self._identity_prompt
            else f"You are a digital employee.\n\n{base_prompt}"
        )

        user_prompt = f"""Current Beliefs (World Model):
{beliefs_text}

Active Goals:
{goals_text}

Available Capabilities: {", ".join(capabilities) if capabilities else "None specified"}

Analyze this situation and provide recommendations."""

        try:
            _, analysis = await self.llm_service.generate_structured(
                prompt=user_prompt,
                system=system_prompt,
                response_format=SituationAnalysis,
                temperature=0.3,
            )
            return cast(SituationAnalysis, analysis)
        except Exception as e:
            logger.warning(
                f"LLM situation analysis failed: {e}",
                extra={"employee_id": str(self.employee.id)},
            )
            return SituationAnalysis(
                current_state_summary="Analysis failed",
                gaps=[],
                opportunities=[],
                problems=[],
                recommended_focus="Continue with current priorities",
            )

    def _format_beliefs_for_llm(self, beliefs: list[Any]) -> str:
        """Format beliefs for LLM prompt."""
        if not beliefs:
            return "No current beliefs"

        lines = []
        for belief in beliefs[:20]:  # Limit to top 20
            subject = getattr(belief, "subject", "unknown")
            predicate = getattr(belief, "predicate", "unknown")
            obj = getattr(belief, "object", {})
            confidence = getattr(belief, "confidence", 0.0)
            lines.append(f"- {subject} → {predicate}: {obj} (confidence: {confidence:.2f})")

        if len(beliefs) > 20:
            lines.append(f"... and {len(beliefs) - 20} more beliefs")

        return "\n".join(lines)

    def _format_goals_for_llm(self, goals: list[Any]) -> str:
        """Format goals for LLM prompt."""
        if not goals:
            return "No active goals"

        lines = []
        for goal in goals:
            description = getattr(goal, "description", "unknown")
            priority = getattr(goal, "priority", 5)
            target = getattr(goal, "target", {})
            progress = getattr(goal, "current_progress", {})
            lines.append(
                f"- [{priority}/10] {description}\n  Target: {target}\n  Progress: {progress}"
            )

        return "\n".join(lines)

    async def _safe_rollback_goals(self) -> None:
        """Attempt to rollback the goals session after a failed flush."""
        try:
            await self.goals.rollback()
        except Exception:
            logger.error(
                "Goals session rollback also failed",
                extra={"employee_id": str(self.employee.id)},
                exc_info=True,
            )

    async def _manage_goals_from_analysis(
        self,
        situation_analysis: SituationAnalysis,
        active_goals: list[Any],
    ) -> None:
        """Create/abandon goals based on situation analysis."""
        # Create new goals for identified opportunities
        for opportunity in situation_analysis.opportunities[:3]:  # Limit to top 3
            # Check if similar goal already exists
            exists = any(
                opportunity.lower() in getattr(g, "description", "").lower() for g in active_goals
            )
            if not exists:
                try:
                    await self.goals.add_goal(
                        goal_type="opportunity",
                        description=f"Pursue opportunity: {opportunity}",
                        priority=6,  # Medium priority for opportunities
                        target={"type": "opportunity", "description": opportunity},
                    )
                    logger.info(
                        f"Created goal for opportunity: {opportunity[:50]}...",
                        extra={"employee_id": str(self.employee.id)},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to create goal for opportunity: {e}",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )
                    # A failed flush invalidates the session — rollback
                    # and stop trying to create more goals this cycle.
                    await self._safe_rollback_goals()
                    return

        # Create goals for critical problems
        for problem in situation_analysis.problems[:2]:  # Limit to top 2
            exists = any(
                problem.lower() in getattr(g, "description", "").lower() for g in active_goals
            )
            if not exists:
                try:
                    await self.goals.add_goal(
                        goal_type="problem",
                        description=f"Address problem: {problem}",
                        priority=8,  # High priority for problems
                        target={"type": "problem", "description": problem},
                    )
                    logger.info(
                        f"Created goal for problem: {problem[:50]}...",
                        extra={"employee_id": str(self.employee.id)},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to create goal for problem: {e}",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )
                    await self._safe_rollback_goals()
                    return

    async def _generate_plans_for_unplanned_goals(
        self,
        goals: list[Any],
        beliefs: list[Any],
        capabilities: list[str],
    ) -> None:
        """Generate plans for goals that don't have intentions."""
        if not self.llm_service:
            logger.warning("No LLM service, skipping plan generation")
            return

        for goal in goals[:5]:  # Limit to top 5 goals
            goal_id = getattr(goal, "id", None)
            if not goal_id:
                continue

            # Check if goal already has intentions
            try:
                existing_intentions = await self.intentions.get_intentions_for_goal(goal_id)
                if existing_intentions:
                    continue  # Already has a plan
            except Exception as e:
                logger.warning(
                    f"Failed to check existing intentions for goal {goal_id}: {e}",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )
                continue

            # Query procedural memory for relevant past experience
            past_procedures: list[Any] = []
            if hasattr(self.memory, "procedural"):
                try:
                    past_procedures = await self.memory.procedural.find_procedures_for_situation(
                        situation={
                            "goal_type": getattr(goal, "goal_type", ""),
                            "goal_description": getattr(goal, "description", ""),
                        },
                        procedure_type="intention_execution",
                        min_success_rate=0.5,
                        limit=3,
                    )
                except Exception as e:
                    logger.warning(
                        "Procedural memory query failed for goal %s: %s",
                        goal_id,
                        e,
                        extra={"employee_id": str(self.employee.id)},
                    )

            # Build procedural context for plan generation
            procedural_context = ""
            if past_procedures:
                lines = ["Past experience (successful procedures):"]
                for proc in past_procedures:
                    steps_desc = ", ".join(
                        s.get("action", "?") for s in (getattr(proc, "steps", []) or [])
                    )
                    rate = getattr(proc, "success_rate", 0) or 0
                    lines.append(f"  - {proc.name}: [{steps_desc}] (success_rate={rate:.0%})")
                procedural_context = "\n".join(lines)

            # Generate plan for this goal
            try:
                enriched_identity = self._identity_prompt
                if procedural_context and enriched_identity:
                    enriched_identity = f"{enriched_identity}\n\n{procedural_context}"
                elif procedural_context:
                    enriched_identity = procedural_context

                new_intentions = await self.intentions.generate_plan_for_goal(
                    goal=goal,
                    beliefs=beliefs,
                    llm_service=self.llm_service,
                    capabilities=capabilities,
                    identity_context=enriched_identity,
                )
                if new_intentions:
                    logger.info(
                        f"Generated {len(new_intentions)} intentions for goal",
                        extra={
                            "employee_id": str(self.employee.id),
                            "goal_id": str(goal_id),
                            "intentions_count": len(new_intentions),
                        },
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to generate plan for goal: {e}",
                    extra={"employee_id": str(self.employee.id), "goal_id": str(goal_id)},
                )

    async def _record_strategic_planning_episode(
        self,
        beliefs_count: int,
        goals_count: int,
    ) -> None:
        """Record strategic planning in episodic memory."""
        try:
            if hasattr(self.memory, "episodic"):
                await self.memory.episodic.record_episode(
                    episode_type="strategic_planning",
                    description="Completed strategic planning cycle",
                    content={
                        "beliefs_analyzed": beliefs_count,
                        "goals_analyzed": goals_count,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    importance=0.6,
                )
        except Exception as e:
            logger.warning(
                f"Failed to record strategic planning episode: {e}",
                extra={"employee_id": str(self.employee.id)},
            )

    # ========================================================================
    # Phase 3: Intention Execution
    # ========================================================================

    async def execute_intentions(self) -> IntentionResult | None:
        """
        Execute highest priority intention from intention stack.

        Executes intention plan steps via the capability registry.
        Each step in the intention's plan is converted to an Action and
        executed by the appropriate capability.

        Returns:
            IntentionResult if work was done, None if no work to do
        """
        # Get next intention
        intention = await self.intentions.get_next_intention()

        if not intention:
            logger.debug("No intentions to execute", extra={"employee_id": str(self.employee.id)})
            return None

        # Check dependencies
        if not await self.intentions.dependencies_satisfied(intention):
            logger.debug(
                "Intention waiting on dependencies",
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                },
            )
            return None

        # Mark as in progress
        await self.intentions.start_intention(intention)

        logger.info(
            f"Executing intention: {intention.description}",
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(intention.id),
                "intention_type": intention.intention_type,
                "priority": intention.priority,
            },
        )

        start_time = time.time()

        try:
            # Execute the intention's plan via capabilities
            execution_result = await self._execute_intention_plan(intention)

            duration_ms = max(0.01, (time.time() - start_time) * 1000)

            result = IntentionResult(
                intention_id=intention.id,
                success=execution_result["success"],
                outcome=execution_result,
                duration_ms=duration_ms,
            )

            if result.success:
                await self.intentions.complete_intention(intention, result)
                logger.info(
                    f"Intention completed: {intention.description}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "intention_id": str(intention.id),
                        "success": True,
                        "duration_ms": duration_ms,
                        "steps_executed": execution_result.get("steps_completed", 0),
                    },
                )
            else:
                error_msg = execution_result.get("error", "Unknown error")
                await self.intentions.fail_intention(intention, error=error_msg)
                logger.warning(
                    f"Intention failed: {intention.description}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "intention_id": str(intention.id),
                        "error": error_msg,
                        "duration_ms": duration_ms,
                    },
                )

            return result

        except Exception as e:
            logger.error(
                f"Intention execution error: {intention.description}",
                exc_info=True,
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                    "error": str(e),
                },
            )

            await self.intentions.fail_intention(intention, error=str(e))

            return IntentionResult(
                intention_id=intention.id,
                success=False,
                outcome={"error": str(e)},
                duration_ms=max(0.01, (time.time() - start_time) * 1000),
            )

    async def _execute_intention_plan(self, intention: Any) -> dict[str, Any]:
        """
        Execute an intention's plan via agentic LLM-driven tool calling.

        Requires both an LLM service and tools to be available. Returns a
        clear error if either is missing.

        Args:
            intention: The intention to execute

        Returns:
            Execution result with success status and outputs
        """
        if not self.llm_service or not self.tool_router:
            return {
                "success": False,
                "error": "Agentic execution requires LLM service and tool router",
                "agentic": True,
            }

        try:
            tool_schemas = self.tool_router.get_all_tool_schemas(self.employee.id)
        except Exception:
            logger.error(
                "Failed to collect tool schemas",
                exc_info=True,
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                },
            )
            return {
                "success": False,
                "error": "Failed to collect tool schemas",
                "agentic": True,
            }

        if not tool_schemas:
            return {
                "success": False,
                "error": "No tools available for execution",
                "agentic": True,
            }

        logger.info(
            "Using agentic execution with %d tool schemas",
            len(tool_schemas),
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(intention.id),
                "tool_count": len(tool_schemas),
            },
        )
        return await self._execute_intention_with_tools(intention, tool_schemas)

    # ========================================================================
    # Phase 3b: Agentic Execution (LLM-driven tool calling)
    # ========================================================================

    async def _execute_intention_with_tools(
        self, intention: Any, tool_schemas: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute intention using LLM function calling.

        The LLM receives the intention description and available tools,
        then drives execution by making tool calls. It can adapt based
        on results, chain multiple calls, and decide when it's done.

        Args:
            intention: The intention to execute
            tool_schemas: Tool schemas from capabilities

        Returns:
            Execution result dict
        """
        from empla.llm.models import Message

        messages = [
            Message(role="system", content=self._build_execution_system_prompt()),
            Message(role="user", content=self._build_intention_prompt(intention)),
        ]

        max_iterations = 10
        tool_calls_made: list[dict[str, Any]] = []

        for iteration in range(max_iterations):
            try:
                response = await self.llm_service.generate_with_tools(
                    messages=messages,
                    tools=tool_schemas,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except Exception as e:
                logger.error(
                    f"LLM generate_with_tools failed during agentic execution: {e}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "intention_id": str(intention.id),
                        "iteration": iteration,
                    },
                )
                return {
                    "success": False,
                    "error": f"LLM call failed: {e}",
                    "tool_calls_made": len(tool_calls_made),
                    "tools_used": [tc["tool"] for tc in tool_calls_made],
                    "agentic": True,
                }

            # If no tool calls, LLM is done
            if not response.tool_calls:
                if not response.content or not response.content.strip():
                    return {
                        "success": False,
                        "error": "Empty assistant response",
                        "tool_calls_made": len(tool_calls_made),
                        "tools_used": [tc["tool"] for tc in tool_calls_made],
                        "agentic": True,
                    }
                return {
                    "success": True,
                    "message": response.content,
                    "tool_calls_made": len(tool_calls_made),
                    "tools_used": [tc["tool"] for tc in tool_calls_made],
                    "agentic": True,
                }

            # Add assistant message with tool calls to conversation
            assistant_msg = Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_msg)

            # Execute each tool call via tool_router
            if self.tool_router is None:
                logger.error(
                    "No tool executor available — cannot execute tool calls",
                    extra={"employee_id": str(self.employee.id)},
                )
                return {
                    "success": False,
                    "error": "No tool executor configured",
                    "tool_calls_made": 0,
                    "tools_used": [],
                    "agentic": True,
                }
            for tool_call in response.tool_calls:
                try:
                    result = await self.tool_router.execute_tool_call(
                        self.employee.id,
                        tool_call.name,
                        tool_call.arguments,
                    )
                except Exception as e:
                    logger.error(
                        f"Tool call {tool_call.name} raised exception: {e}",
                        extra={
                            "employee_id": str(self.employee.id),
                            "tool_name": tool_call.name,
                        },
                    )
                    result_content = json.dumps(
                        {"success": False, "error": f"{type(e).__name__}: {e}"}
                    )
                    tool_calls_made.append({"tool": tool_call.name, "success": False})
                    messages.append(
                        Message(role="tool", content=result_content, tool_call_id=tool_call.id)
                    )
                    continue

                tool_calls_made.append({"tool": tool_call.name, "success": result.success})

                result_content = json.dumps(
                    {
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                    },
                    default=str,
                )
                messages.append(
                    Message(role="tool", content=result_content, tool_call_id=tool_call.id)
                )

                logger.debug(
                    f"Tool call {tool_call.name}: {'success' if result.success else 'failed'}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "tool_name": tool_call.name,
                        "success": result.success,
                        "iteration": iteration,
                    },
                )

        # Max iterations reached — incomplete execution
        logger.warning(
            "Agentic execution reached max iterations without completing",
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(intention.id),
                "max_iterations": max_iterations,
                "tool_calls_made": len(tool_calls_made),
            },
        )
        return {
            "success": False,
            "error": f"Agentic execution exhausted iteration budget (max_iterations={max_iterations})",
            "tool_calls_made": len(tool_calls_made),
            "tools_used": [tc["tool"] for tc in tool_calls_made],
            "agentic": True,
        }

    def _build_execution_system_prompt(self) -> str:
        """Build system prompt for agentic execution."""
        execution_instructions = (
            "Use the available tools to accomplish the intention. "
            "Call tools as needed, adapt based on results, and stop when done. "
            "Be efficient — don't make unnecessary tool calls."
        )
        if self._identity_prompt:
            return f"{self._identity_prompt}\n\n{execution_instructions}"
        return f"You are a digital employee. {execution_instructions}"

    def _build_intention_prompt(self, intention: Any) -> str:
        """Build user prompt from intention context."""
        parts = [f"Execute this intention: {intention.description}"]
        context = getattr(intention, "context", None)
        if context and isinstance(context, dict):
            if "reasoning" in context:
                parts.append(f"Reasoning: {context['reasoning']}")
            if "success_criteria" in context:
                parts.append(f"Success criteria: {context['success_criteria']}")
        return "\n".join(parts)

    # ========================================================================
    # Phase 4: Learning & Reflection
    # ========================================================================

    async def reflection_cycle(self, result: IntentionResult) -> None:
        """
        Learn from execution result.

        Updates procedural memory and beliefs based on what worked/failed.
        This is called after every intention execution.

        Args:
            result: Result of intention execution
        """
        logger.debug(
            "Reflection cycle starting",
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(result.intention_id),
                "success": result.success,
            },
        )

        try:
            # ============ STEP 1: Record in Episodic Memory ============
            await self._record_execution_episode(result)

            # ============ STEP 2: Update Procedural Memory ============
            await self._update_procedural_memory(result)

            # ============ STEP 3: Update Effectiveness Beliefs ============
            await self._update_effectiveness_beliefs(result)

            logger.debug(
                "Reflection cycle complete",
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(result.intention_id),
                },
            )

        except Exception as e:
            logger.warning(
                f"Reflection cycle error: {e}",
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(result.intention_id),
                },
            )

    async def _record_execution_episode(self, result: IntentionResult) -> None:
        """Record execution outcome in episodic memory."""
        try:
            if hasattr(self.memory, "episodic"):
                await self.memory.episodic.record_episode(
                    episode_type="intention_execution",
                    description=f"Executed intention {result.intention_id}",
                    content={
                        "intention_id": str(result.intention_id),
                        "success": result.success,
                        "outcome": result.outcome,
                        "duration_ms": result.duration_ms,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    importance=0.7
                    if result.success
                    else 0.8,  # Failures more important to remember
                )
        except Exception as e:
            logger.warning(
                f"Failed to record execution episode: {e}",
                extra={"employee_id": str(self.employee.id)},
            )

    async def _update_procedural_memory(self, result: IntentionResult) -> None:
        """Update procedural memory based on execution outcome."""
        try:
            if not hasattr(self.memory, "procedural"):
                return

            outcome = result.outcome or {}
            tools_used = outcome.get("tools_used", [])

            # Record procedure for successful executions
            if result.success and tools_used:
                steps = [{"action": tool, "success": True} for tool in tools_used]

                await self.memory.procedural.record_procedure(
                    procedure_type="intention_execution",
                    name=f"intention_{result.intention_id}",
                    steps=steps,
                    outcome=f"success:{len(tools_used)}_tools",
                    success=True,
                    execution_time=result.duration_ms / 1000.0,
                    context={
                        "intention_id": str(result.intention_id),
                        "tool_count": len(tools_used),
                    },
                )

            # For failures, record the failure pattern to avoid
            elif not result.success:
                error = outcome.get("error", "Unknown error")

                await self.memory.procedural.record_procedure(
                    procedure_type="intention_failure",
                    name=f"failed_intention_{result.intention_id}",
                    steps=[{"action": "failed", "error": error}],
                    outcome=f"failure:{error[:100]}",
                    success=False,
                    execution_time=result.duration_ms / 1000.0,
                    context={
                        "intention_id": str(result.intention_id),
                        "error": error,
                    },
                )

        except Exception as e:
            logger.warning(
                f"Failed to update procedural memory: {e}",
                extra={"employee_id": str(self.employee.id)},
            )

    async def _update_effectiveness_beliefs(self, result: IntentionResult) -> None:
        """Update beliefs about what actions are effective."""
        try:
            outcome = result.outcome or {}
            tools_used = outcome.get("tools_used", [])

            if not tools_used:
                return

            overall_success = result.success
            for tool_name in tools_used:
                if tool_name:
                    confidence = 0.8 if overall_success else 0.3
                    await self.beliefs.update_belief(
                        subject=tool_name,
                        predicate="effectiveness",
                        belief_object={
                            "value": 1.0 if overall_success else 0.0,
                            "last_result": overall_success,
                        },
                        confidence=confidence,
                        source="execution_outcome",
                    )

        except Exception as e:
            logger.warning(
                "Failed to update effectiveness beliefs: %s",
                e,
                extra={"employee_id": str(self.employee.id)},
            )

    def should_run_deep_reflection(self) -> bool:
        """
        Decide if it's time for deep reflection.

        Deep reflection analyzes recent outcomes to identify meta-patterns
        and skill gaps. It runs less frequently (e.g., daily).

        Returns:
            True if deep reflection should run, False otherwise
        """
        if self.last_deep_reflection is None:
            # Never run deep reflection - do it now
            return True

        hours_since_last = (datetime.now(UTC) - self.last_deep_reflection).total_seconds() / 3600

        return hours_since_last >= self.config.deep_reflection_interval_hours

    async def deep_reflection_cycle(self) -> None:
        """
        Periodic deep reflection on patterns and learnings.

        Runs less frequently (e.g., daily) to identify meta-patterns across
        recent outcomes, identify skill gaps, and form learning goals.
        """
        logger.info(
            "Deep reflection cycle starting",
            extra={"employee_id": str(self.employee.id)},
        )

        start_time = time.time()

        try:
            # ============ STEP 1: Gather Recent Episodes ============
            recent_episodes = await self._get_recent_episodes(days=1)

            if not recent_episodes:
                logger.debug("No recent episodes to reflect on")
                self.last_deep_reflection = datetime.now(UTC)
                return

            # ============ STEP 2: Analyze Patterns ============
            success_count = sum(
                1 for ep in recent_episodes if ep.get("content", {}).get("success", False)
            )
            failure_count = len(recent_episodes) - success_count
            success_rate = success_count / len(recent_episodes) if recent_episodes else 0

            # ============ STEP 3: Update Beliefs About Performance ============
            await self.beliefs.update_belief(
                subject="self",
                predicate="recent_success_rate",
                belief_object={
                    "value": success_rate,
                    "successes": success_count,
                    "failures": failure_count,
                    "total_episodes": len(recent_episodes),
                },
                confidence=0.9,
                source="deep_reflection",
            )

            # ============ STEP 4: Identify Patterns with LLM ============
            if self.llm_service and len(recent_episodes) >= 3:
                await self._analyze_patterns_with_llm(recent_episodes, success_rate)

            # ============ STEP 5: Reinforce/Decay Memory ============
            await self._maintain_memory_health()

            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "Deep reflection cycle complete",
                extra={
                    "employee_id": str(self.employee.id),
                    "episodes_analyzed": len(recent_episodes),
                    "success_rate": f"{success_rate:.2%}",
                    "duration_ms": duration_ms,
                },
            )

        except Exception as e:
            logger.error(
                "Deep reflection cycle failed",
                exc_info=True,
                extra={"employee_id": str(self.employee.id), "error": str(e)},
            )

        self.last_deep_reflection = datetime.now(UTC)

    async def _get_recent_episodes(self, days: int = 1) -> list[dict[str, Any]]:
        """Get recent episodes from episodic memory."""
        try:
            if hasattr(self.memory, "episodic"):
                episodes = await self.memory.episodic.recall_recent(
                    days=days,
                    limit=100,
                    episode_type="intention_execution",
                )
                # Convert to dicts for easier processing
                return [
                    {
                        "id": str(ep.id),
                        "type": ep.episode_type,
                        "description": ep.description,
                        "content": ep.content,
                        "importance": ep.importance,
                        "occurred_at": ep.occurred_at.isoformat() if ep.occurred_at else None,
                    }
                    for ep in episodes
                ]
        except Exception as e:
            logger.warning(
                f"Failed to get recent episodes: {e}", extra={"employee_id": str(self.employee.id)}
            )
        return []

    async def _analyze_patterns_with_llm(
        self, episodes: list[dict[str, Any]], success_rate: float
    ) -> None:
        """Use LLM to identify patterns in recent execution history."""
        if not self.llm_service:
            return

        # Format episodes for prompt
        episodes_text = "\n".join(
            [
                f"- {ep.get('description', 'Unknown')}: "
                f"{'Success' if ep.get('content', {}).get('success') else 'Failed'}"
                for ep in episodes[:20]
            ]
        )

        base_prompt = """Analyze your recent execution history.
Identify patterns in what succeeded and failed. Focus on:
1. Common factors in successes
2. Common factors in failures
3. Recommended improvements"""

        system_prompt = (
            f"{self._identity_prompt}\n\n{base_prompt}"
            if self._identity_prompt
            else f"You are a digital employee.\n\n{base_prompt}"
        )

        user_prompt = f"""Recent execution history (success rate: {success_rate:.1%}):

{episodes_text}

Analyze the patterns and provide brief recommendations."""

        try:
            response = await self.llm_service.generate(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.3,
                max_tokens=500,
            )

            # Store analysis in episodic memory
            if hasattr(self.memory, "episodic"):
                await self.memory.episodic.record_episode(
                    episode_type="deep_reflection",
                    description="Pattern analysis from deep reflection",
                    content={
                        "analysis": response.content,
                        "episodes_analyzed": len(episodes),
                        "success_rate": success_rate,
                    },
                    importance=0.8,
                )

        except Exception as e:
            logger.warning(
                f"LLM pattern analysis failed: {e}", extra={"employee_id": str(self.employee.id)}
            )

    async def _maintain_memory_health(self) -> None:
        """Perform memory maintenance: reinforce and decay."""
        if hasattr(self.memory, "episodic"):
            try:
                reinforced = await self.memory.episodic.reinforce_frequently_recalled(
                    min_recall_count=3,
                    importance_boost=1.05,
                )
                decayed = await self.memory.episodic.decay_rarely_recalled(
                    min_days_old=30,
                    importance_decay=0.95,
                )
                logger.debug(
                    "Memory maintenance: reinforced %d, decayed %d",
                    reinforced,
                    decayed,
                    extra={"employee_id": str(self.employee.id)},
                )
            except Exception as e:
                logger.warning(
                    "Episodic memory maintenance failed: %s",
                    e,
                    extra={"employee_id": str(self.employee.id)},
                )

        if hasattr(self.memory, "procedural"):
            try:
                await self.memory.procedural.reinforce_successful_procedures(
                    min_success_rate=0.8,
                    min_executions=3,
                )
            except Exception as e:
                logger.warning(
                    "Procedural memory reinforcement failed: %s",
                    e,
                    extra={"employee_id": str(self.employee.id)},
                )
            try:
                await self.memory.procedural.archive_poor_procedures(
                    max_success_rate=0.2,
                    min_executions=3,
                )
            except Exception as e:
                logger.warning(
                    "Procedural memory archiving failed: %s",
                    e,
                    extra={"employee_id": str(self.employee.id)},
                )
