"""
empla.core.loop.execution - Proactive Execution Loop Implementation

The main continuous autonomous operation loop.

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │  ProactiveExecutionLoop (this file — orchestrator)       │
  │  Inherits from:                                          │
  │  ├── PerceptionMixin        (perception.py)              │
  │  ├── PlanningMixin          (planning.py)                │
  │  ├── GoalManagementMixin    (goal_management.py)         │
  │  ├── IntentionExecutionMixin(intention_execution.py)     │
  │  └── ReflectionMixin        (reflection.py)              │
  │                                                          │
  │  Shared types in protocols.py                            │
  │  Data models in models.py                                │
  └─────────────────────────────────────────────────────────┘

Each mixin provides a phase of the BDI cycle. The orchestrator
wires them together via _execute_bdi_phases() and manages the
continuous loop, lifecycle hooks, and shared state.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

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
from empla.core.loop.goal_management import GoalManagementMixin
from empla.core.loop.intention_execution import IntentionExecutionMixin
from empla.core.loop.models import (
    IntentionResult,
    LoopConfig,
)
from empla.core.loop.perception import PerceptionMixin
from empla.core.loop.planning import PlanningMixin
from empla.core.loop.protocols import (
    BeliefChange,
    BeliefSystemProtocol,
    GoalRecommendation,
    GoalSystemProtocol,
    IntentionStackProtocol,
    MemorySystemProtocol,
    SituationAnalysis,
    ToolSourceProtocol,
)
from empla.core.loop.reflection import ReflectionMixin
from empla.models.employee import Employee

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from empla.employees.identity import EmployeeIdentity
    from empla.llm import LLMService
    from empla.runner.health import HealthServer

logger = logging.getLogger(__name__)


# Re-export protocol types and models for backward compatibility.
# Code that imports from empla.core.loop.execution continues to work.
__all__ = [
    "BeliefChange",
    "BeliefSystemProtocol",
    "GoalRecommendation",
    "GoalSystemProtocol",
    "IntentionStackProtocol",
    "MemorySystemProtocol",
    "ProactiveExecutionLoop",
    "SituationAnalysis",
    "ToolSourceProtocol",
]


class ProactiveExecutionLoop(
    PerceptionMixin,
    PlanningMixin,
    GoalManagementMixin,
    IntentionExecutionMixin,
    ReflectionMixin,
):
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

    Phase logic lives in mixin classes (perception.py, planning.py, etc.)
    while this class manages the cycle orchestration, lifecycle hooks,
    and shared state.

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
        llm_service: LLMService | None = None,
        config: LoopConfig | None = None,
        status_checker: Callable[[Employee], Awaitable[None]] | None = None,
        hooks: HookRegistry | None = None,
        tool_router: ToolSourceProtocol | None = None,
        identity: EmployeeIdentity | None = None,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
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
            sessionmaker: Optional async sessionmaker used for short-lived metrics
                writes. Required for cycle metrics to persist. Previously read via
                ``getattr(self.employee, "_sessionmaker", None)`` which silently
                no-op'd because ``self.employee`` is the ORM row, not the
                ``DigitalEmployee`` instance that holds ``_sessionmaker``.
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
        self._sessionmaker = sessionmaker
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
        self._wake_event = asyncio.Event()
        self._health_server: HealthServer | None = None  # Set by runner after loop creation

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

    # ========================================================================
    # Identity
    # ========================================================================

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

    # ========================================================================
    # Lifecycle
    # ========================================================================

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
        self._wake_event.set()  # Interrupt sleep immediately

        logger.info(
            f"Stopping proactive loop for {self.employee.name}",
            extra={"employee_id": str(self.employee.id), "total_cycles": self.cycle_count},
        )

    # ========================================================================
    # Main Loop
    # ========================================================================

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

                # Check for due scheduled actions → inject into working memory
                await self._check_scheduled_actions()

                # Drain external events from health server → inject as observations
                await self._check_pending_events()

                await self._execute_bdi_phases()

                # ============ DEEP REFLECTION ============
                # Periodic deep reflection (less frequent)
                if self.should_run_deep_reflection():
                    await self.deep_reflection_cycle()
                    self.last_deep_reflection = datetime.now(UTC)

                # ============ METRICS ============
                cycle_duration = time.time() - cycle_start

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

                # Record success metric AFTER hooks complete — avoids writing
                # success=True then overwriting with success=False if hook raises.
                await self._record_cycle_metrics(cycle_duration, success=True)

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

                with contextlib.suppress(Exception):
                    await self._record_cycle_metrics(cycle_duration, success=False)

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

    # ========================================================================
    # Single Cycle (for testing / run_once)
    # ========================================================================

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
    # BDI Phase Orchestration
    # ========================================================================

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
        # Reset per-cycle budget tracking for the router (scoped to this employee)
        if self.llm_service:
            self.llm_service.reset_cycle_budget()

        employee_id = self.employee.id

        # ============ TRUST BOUNDARY RESET ============
        if self.tool_router is not None and hasattr(self.tool_router, "reset_trust_cycle"):
            self.tool_router.reset_trust_cycle()

        # ============ BELIEF MAINTENANCE ============
        try:
            decayed = await self.beliefs.decay_beliefs()
            if decayed:
                logger.info(
                    "Belief decay: removed %d stale beliefs",
                    len(decayed),
                    extra={"employee_id": str(employee_id)},
                )
        except Exception:
            logger.warning(
                "Belief decay failed",
                exc_info=True,
                extra={"employee_id": str(employee_id)},
            )

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

        # Promote high-confidence beliefs to semantic memory (long-term knowledge)
        if hasattr(self.memory, "semantic") and changed_beliefs:
            try:
                promoted = 0
                for change in changed_beliefs:
                    if change.new_confidence >= 0.9:
                        belief = change.belief
                        await self.memory.semantic.store_fact(
                            subject=change.subject,
                            predicate=change.predicate,
                            fact_object=getattr(belief, "object", {}),
                            confidence=change.new_confidence,
                            source="belief_promotion",
                            fact_type="entity",
                        )
                        promoted += 1
                if promoted:
                    logger.debug(
                        "Promoted %d beliefs to semantic memory",
                        promoted,
                        extra={"employee_id": str(employee_id)},
                    )
            except Exception:
                logger.warning(
                    "Semantic memory promotion failed",
                    exc_info=True,
                    extra={"employee_id": str(employee_id)},
                )

        await self._safe_commit("perception_and_beliefs")

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

        await self._safe_commit("strategic_planning")

        # ============ GOAL MANAGEMENT ============
        pursuing_goals = await self.goals.get_pursuing_goals()
        goal_progress_map = await self._evaluate_goals_progress(pursuing_goals, changed_beliefs)
        for goal in pursuing_goals:
            progress = goal_progress_map.get(str(goal.id), {})
            if progress:
                await self.goals.update_goal_progress(goal.id, progress)
                await self._check_goal_achievement(goal, progress)
            else:
                # Reattempt completion for goals flagged as completion_pending
                current_progress = getattr(goal, "current_progress", {}) or {}
                if current_progress.get("_completion_pending"):
                    await self._check_goal_achievement(goal, current_progress)

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

        await self._safe_commit("intention_execution")

        # ============ LEARNING ============
        if result:
            await self.reflection_cycle(result)

            await self._safe_commit("reflection")

            await self._hooks.emit(
                HOOK_AFTER_REFLECTION,
                employee_id=employee_id,
                result=result,
            )

        return result

    # ========================================================================
    # Utilities
    # ========================================================================

    async def _check_scheduled_actions(self) -> None:
        """Check for due scheduled actions and inject them as observations.

        Queries working memory for scheduled_action items that are due,
        adds them as high-priority working memory items so the perception
        phase sees them, and cleans up one-shot actions after processing.
        """
        if not hasattr(self.memory, "working"):
            return

        try:
            now = datetime.now(UTC)
            active_items = await self.memory.working.get_active_items()

            due_actions = []
            for item in active_items:
                content = getattr(item, "content", {}) or {}
                # Scheduled actions are stored as item_type="task" with
                # subtype="scheduled_action" (to comply with DB check constraint)
                is_scheduled = content.get("subtype") == "scheduled_action"
                if not is_scheduled:
                    continue
                scheduled_for_str = content.get("scheduled_for")
                if not scheduled_for_str:
                    continue
                try:
                    scheduled_for = datetime.fromisoformat(scheduled_for_str)
                    if scheduled_for <= now:
                        due_actions.append(item)
                except (ValueError, TypeError):
                    continue

            for action in due_actions:
                content = getattr(action, "content", {}) or {}
                desc = content.get("description", "Scheduled action")
                # Add as high-importance working memory item so perception sees it
                await self.memory.working.add_item(
                    item_type="observation",
                    content={
                        "description": f"SCHEDULED ACTION DUE: {desc}",
                        "subtype": "scheduled_action_due",
                        "original_action": content,
                    },
                    importance=0.9,
                )
                # Clean up the fired action
                recurring = content.get("recurring", False)
                await self.memory.working.remove_item(action.id)

                if recurring:
                    # Re-create with next run time (remove + add since
                    # working memory has no update_content method)
                    interval_hours = content.get("interval_hours", 24)
                    next_run = now + timedelta(hours=interval_hours)
                    content["scheduled_for"] = next_run.isoformat()
                    content["subtype"] = "scheduled_action"
                    await self.memory.working.add_item(
                        item_type="task",
                        content=content,
                        importance=0.7,
                    )

            if due_actions:
                logger.info(
                    "Injected %d due scheduled actions into perception",
                    len(due_actions),
                    extra={"employee_id": str(self.employee.id)},
                )

        except Exception:
            logger.warning(
                "Failed to check scheduled actions",
                exc_info=True,
                extra={"employee_id": str(self.employee.id)},
            )

    async def _check_pending_events(self) -> None:
        """Drain external events from HealthServer and inject as observations.

        Events arrive via POST /wake from the API server when external
        webhooks fire (HubSpot deal update, calendar change, email received,
        etc.). Each event becomes a high-priority working memory observation
        so the LLM can decide how to respond.
        """
        if self._health_server is None:
            return
        if not hasattr(self.memory, "working"):
            return

        try:
            events = self._health_server.drain_events()
        except Exception:
            logger.warning(
                "Failed to drain events from health server",
                exc_info=True,
                extra={"employee_id": str(self.employee.id)},
            )
            return

        if not events:
            return

        injected = 0
        for event in events:
            try:
                provider = event.get("provider", "unknown")
                event_type = event.get("event_type", "unknown")
                summary = event.get("summary", "")
                description = f"EVENT: {provider} {event_type}"
                if summary:
                    description += f" — {summary}"

                await self.memory.working.add_item(
                    item_type="observation",
                    content={
                        "description": description,
                        "subtype": "external_event",
                        "provider": provider,
                        "event_type": event_type,
                        "payload": event.get("payload", {}),
                        "received_at": event.get("received_at", ""),
                    },
                    importance=0.9,
                )
                injected += 1
            except Exception:
                logger.error(
                    "Failed to inject external event, event lost",
                    exc_info=True,
                    extra={
                        "employee_id": str(self.employee.id),
                        "provider": event.get("provider", "unknown"),
                        "event_type": event.get("event_type", "unknown"),
                    },
                )

        if injected == 0 and events:
            logger.error(
                "ALL %d external events failed injection — events lost",
                len(events),
                extra={"employee_id": str(self.employee.id)},
            )
        elif injected:
            logger.info(
                "Injected %d/%d external events into perception",
                injected,
                len(events),
                extra={"employee_id": str(self.employee.id)},
            )

    def wake(self) -> None:
        """Wake the loop from sleep immediately.

        Called by external triggers (webhooks, scheduled actions, events)
        to interrupt the inter-cycle sleep and start a new BDI cycle.
        Safe to call from any coroutine in the same event loop.
        For cross-thread calls, use loop.call_soon_threadsafe(employee_loop.wake).
        """
        self._wake_event.set()

    async def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep with support for stop() and external wake signals."""
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=seconds)
            # Event fired — consume it so it doesn't re-trigger next sleep
            self._wake_event.clear()
            logger.debug(
                "Sleep interrupted by wake event",
                extra={"employee_id": str(self.employee.id)},
            )
        except TimeoutError:
            pass  # Normal timeout — no wake signal, just proceed to next cycle
        if not self.is_running:
            return  # Stop was called during sleep

    async def _record_cycle_metrics(self, duration_seconds: float, *, success: bool) -> None:
        """Persist cycle metrics to DB using a short-lived independent session.

        Uses a separate session so metrics writes don't pollute the BDI
        loop's long-lived session. Cache update deferred until after commit.
        """
        sessionmaker = self._sessionmaker
        if sessionmaker is None:
            logger.debug(
                "Cycle metrics skipped: no sessionmaker configured",
                extra={"employee_id": str(self.employee.id)},
            )
            return
        try:
            # Deferred import: empla.services.metrics imports empla.models which
            # may not be available at module load time in all contexts (e.g. tests).
            from empla.services.metrics import (
                _previous_tool_stats,
                record_cycle_metrics,
            )

            # Collect tool stats — isolated so failure doesn't lose base metrics
            tool_stats = None
            try:
                if self.tool_router and hasattr(self.tool_router, "health_monitor"):
                    monitor = self.tool_router.health_monitor
                    if hasattr(monitor, "get_all_status"):
                        tool_stats = monitor.get_all_status()
            except Exception:
                logger.debug("Health monitor query failed, recording without tool stats")

            # Collect LLM cost for this cycle (before reset_cycle_budget)
            llm_cost_usd = None
            try:
                if self.llm_service:
                    cost_summary = self.llm_service.get_cost_summary()
                    routing = cost_summary.get("routing")
                    if routing and "cycle_cost_usd" in routing:
                        llm_cost_usd = routing["cycle_cost_usd"]
            except Exception:
                logger.debug("LLM cost summary query failed, recording without cost")

            async with sessionmaker() as metrics_session:
                snapshot = await record_cycle_metrics(
                    metrics_session,
                    tenant_id=self.employee.tenant_id,
                    employee_id=self.employee.id,
                    cycle_count=self.cycle_count,
                    duration_seconds=duration_seconds,
                    success=success,
                    tool_stats=tool_stats,
                    llm_cost_usd=llm_cost_usd,
                )
                await metrics_session.commit()
                # Only advance cache AFTER commit succeeds
                if snapshot is not None:
                    _previous_tool_stats[self.employee.id] = snapshot
        except Exception:
            logger.debug(
                "Failed to record cycle metrics",
                exc_info=True,
                extra={"employee_id": str(self.employee.id)},
            )

    async def _safe_commit(self, phase: str) -> None:
        """Commit the shared session after a phase, rolling back on failure."""
        try:
            if hasattr(self.beliefs, "session"):
                await self.beliefs.session.commit()
        except Exception:
            logger.warning(
                "Commit failed after %s, rolling back",
                phase,
                exc_info=True,
                extra={"employee_id": str(self.employee.id)},
            )
            try:
                await self.beliefs.session.rollback()
            except Exception:
                logger.error(
                    "Session rollback also failed after %s — session may be inconsistent",
                    phase,
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )
