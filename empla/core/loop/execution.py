"""
empla.core.loop.execution - Proactive Execution Loop Implementation

The main continuous autonomous operation loop.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from empla.core.loop.models import (
    IntentionResult,
    LoopConfig,
    Observation,
    PerceptionResult,
)
from empla.models.employee import Employee

logger = logging.getLogger(__name__)


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

    async def update_beliefs(self, observations: list[Observation]) -> list[BeliefChange]:
        """Update beliefs based on observations"""
        ...


class GoalSystemProtocol(Protocol):
    """Protocol for GoalSystem component"""

    async def get_active_goals(self) -> list[Any]:
        """Get all active goals"""
        ...

    async def update_goal_progress(self, goal: Any, beliefs: BeliefSystemProtocol) -> None:
        """Update goal progress based on current beliefs"""
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


class MemorySystemProtocol(Protocol):
    """Protocol for MemorySystem component"""

    # Placeholder for memory system methods
    # Will be expanded as memory system is implemented


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
        config: LoopConfig | None = None,
    ):
        """
        Initialize proactive execution loop.

        Args:
            employee: Digital employee this loop runs for
            beliefs: BeliefSystem component (BDI Beliefs)
            goals: GoalSystem component (BDI Desires)
            intentions: IntentionStack component (BDI Intentions)
            memory: MemorySystem component (episodic, semantic, procedural, working)
            config: Loop configuration (timing, perception sources, etc.)
        """
        self.employee = employee
        self.beliefs = beliefs
        self.goals = goals
        self.intentions = intentions
        self.memory = memory

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
                "config": self.config.model_dump(),
            },
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
        """
        while self.is_running and self.employee.status == "active":
            try:
                cycle_start = time.time()
                self.cycle_count += 1

                logger.debug(
                    f"Loop cycle {self.cycle_count} starting",
                    extra={"employee_id": str(self.employee.id)},
                )

                # ============ PERCEIVE ============
                # Gather observations from environment
                perception_result = await self.perceive_environment()

                logger.info(
                    f"Perception complete: {len(perception_result.observations)} observations",
                    extra={
                        "employee_id": str(self.employee.id),
                        "observations": len(perception_result.observations),
                        "opportunities": perception_result.opportunities_detected,
                        "problems": perception_result.problems_detected,
                    },
                )

                # ============ UPDATE BELIEFS ============
                # Process observations into world model updates
                changed_beliefs = await self.beliefs.update_beliefs(perception_result.observations)

                logger.info(
                    f"Beliefs updated: {len(changed_beliefs)} changes",
                    extra={
                        "employee_id": str(self.employee.id),
                        "changed_beliefs": len(changed_beliefs),
                    },
                )

                # ============ STRATEGIC REASONING ============
                # Deep planning when needed (expensive operation)
                if self.should_run_strategic_planning(changed_beliefs):
                    await self.strategic_planning_cycle()
                    self.last_strategic_planning = datetime.now(UTC)

                # ============ GOAL MANAGEMENT ============
                # Update goal progress based on current beliefs
                active_goals = await self.goals.get_active_goals()
                for goal in active_goals:
                    await self.goals.update_goal_progress(goal, self.beliefs)

                logger.debug(
                    f"Goal progress updated for {len(active_goals)} active goals",
                    extra={"employee_id": str(self.employee.id)},
                )

                # ============ INTENTION EXECUTION ============
                # Execute highest priority work
                result = await self.execute_intentions()

                # ============ LEARNING ============
                # Reflect on outcomes and learn
                if result:
                    await self.reflection_cycle(result)

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

                # ============ SLEEP ============
                # Wait before next cycle
                await asyncio.sleep(self.cycle_interval)

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

                # TODO: Add metrics for errors
                # metrics.increment("proactive_loop.errors")

                # Back off on errors to avoid thundering herd
                await asyncio.sleep(self.error_backoff_interval)

        logger.info(
            f"Proactive loop ended for {self.employee.name}",
            extra={
                "employee_id": str(self.employee.id),
                "total_cycles": self.cycle_count,
                "reason": "stopped" if not self.is_running else "employee_deactivated",
            },
        )

    # ========================================================================
    # Phase 1: Perception
    # ========================================================================

    async def perceive_environment(self) -> PerceptionResult:
        """
        Gather observations from all sources.

        This is the "eyes and ears" of the employee - monitoring the environment
        for changes, events, opportunities, and problems.

        Returns:
            PerceptionResult with observations and statistics

        Note:
            This is currently a placeholder implementation that returns empty
            observations. Real perception will be implemented in Phase 2 with
            actual capability integrations (email, calendar, metrics, etc.).
        """
        start_time = time.time()
        observations: list[Observation] = []

        # TODO: Implement actual perception sources in Phase 2
        # For now, return empty observations to allow loop testing

        # Future implementation will check:
        # - Email inbox (new messages, replies)
        # - Calendar (upcoming events, changes)
        # - Chat mentions (Slack, Teams)
        # - Customer events (support tickets, usage changes)
        # - CRM updates (deal stages, contact changes)
        # - Metrics (threshold crossings, anomalies)
        # - Time triggers (scheduled events)

        duration_ms = max(0.01, (time.time() - start_time) * 1000)  # Ensure > 0

        logger.debug(
            f"Perception complete: {len(observations)} observations",
            extra={
                "employee_id": str(self.employee.id),
                "duration_ms": duration_ms,
            },
        )

        return PerceptionResult(
            observations=observations,
            opportunities_detected=0,
            problems_detected=0,
            risks_detected=0,
            perception_duration_ms=duration_ms,
            sources_checked=[],
        )

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

        Note:
            This is currently a placeholder that logs the intent.
            Full implementation will be added in Phase 2 with LLM integration.
        """
        logger.info(
            "Strategic planning cycle starting",
            extra={"employee_id": str(self.employee.id)},
        )

        start_time = time.time()

        # TODO: Implement full strategic planning in Phase 2
        # This requires:
        # - Situation analysis (beliefs, goals, metrics, context)
        # - Gap analysis (where we are vs where we want to be)
        # - Strategy generation (using LLM + procedural memory)
        # - Strategy evaluation and selection
        # - Goal formation/update/abandonment
        # - Documentation in episodic memory

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Strategic planning cycle complete",
            extra={"employee_id": str(self.employee.id), "duration_ms": duration_ms},
        )

        # Update last strategic planning time
        self.last_strategic_planning = datetime.now(UTC)

        # TODO: Add metrics
        # metrics.histogram("strategic_planning.duration_ms", duration_ms)

    # ========================================================================
    # Phase 3: Intention Execution
    # ========================================================================

    async def execute_intentions(self) -> IntentionResult | None:
        """
        Execute highest priority intention from intention stack.

        Returns:
            IntentionResult if work was done, None if no work to do

        Note:
            This is currently a placeholder that delegates to IntentionStack.
            Full implementation will be in IntentionStack class.
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

        # Execute (actual execution logic is in IntentionStack/Capabilities)
        start_time = time.time()

        try:
            # TODO: Actual execution will be delegated to capability handlers
            # For now, simulate successful execution
            result = IntentionResult(
                intention_id=intention.id,
                success=True,
                outcome={"simulated": True},
                duration_ms=max(0.01, (time.time() - start_time) * 1000),  # Ensure > 0
            )

            await self.intentions.complete_intention(intention, result)

            logger.info(
                f"Intention completed: {intention.description}",
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                    "success": result.success,
                    "duration_ms": result.duration_ms,
                },
            )

            return result

        except Exception as e:
            logger.error(
                f"Intention failed: {intention.description}",
                exc_info=True,
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                    "error": str(e),
                },
            )

            await self.intentions.fail_intention(intention, error=str(e))

            return None

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

        Note:
            This is currently a placeholder that logs the intent.
            Full implementation will be added in Phase 4 with memory integration.
        """
        logger.debug(
            "Reflection cycle starting",
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(result.intention_id),
                "success": result.success,
            },
        )

        # TODO: Implement full reflection cycle in Phase 4
        # This requires:
        # - Record outcome in episodic memory
        # - Update procedural memory (strengthen/weaken patterns)
        # - Update effectiveness beliefs
        # - Update goal progress
        # - Learn from patterns (if enough data)

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

        Note:
            This is currently a placeholder that logs the intent.
            Full implementation will be added in Phase 4 with memory and LLM integration.
        """
        logger.info(
            "Deep reflection cycle starting",
            extra={"employee_id": str(self.employee.id)},
        )

        # TODO: Implement full deep reflection in Phase 4
        # This requires:
        # - Analyze recent outcomes (last 24 hours)
        # - Identify patterns using LLM
        # - Update procedural memory with meta-patterns
        # - Update beliefs based on patterns
        # - Identify skill gaps
        # - Form learning goals
