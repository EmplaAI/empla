"""
empla.core.loop.events - Event Monitoring System

Monitors for events and triggers based on:
- Threshold conditions (e.g., belief value crosses threshold)
- Time-based events (e.g., daily check-in, weekly report)
- External events (e.g., new email, calendar reminder)

The EventMonitoringSystem runs alongside the proactive loop to detect
conditions that require immediate attention or scheduled actions.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Event Models
# ============================================================================


class EventTrigger(BaseModel):
    """
    Definition of a trigger condition.

    Triggers are evaluated against beliefs and time to determine
    if an event should fire.
    """

    id: str = Field(..., description="Unique trigger identifier")
    name: str = Field(..., description="Human-readable trigger name")
    trigger_type: str = Field(..., description="Type: threshold, time_based, external")
    condition: dict[str, Any] = Field(..., description="Condition configuration")
    action: dict[str, Any] = Field(..., description="Action to take when triggered")
    enabled: bool = Field(default=True, description="Whether trigger is active")
    cooldown_minutes: int = Field(default=60, description="Minimum time between firings")
    last_fired: datetime | None = Field(default=None, description="Last time this trigger fired")

    def can_fire(self) -> bool:
        """Check if trigger is ready to fire (not in cooldown)."""
        if not self.enabled:
            return False
        if self.last_fired is None:
            return True
        elapsed = (datetime.now(UTC) - self.last_fired).total_seconds() / 60
        return elapsed >= self.cooldown_minutes


class Event(BaseModel):
    """
    An event that has occurred.
    """

    id: str = Field(..., description="Unique event ID")
    trigger_id: str = Field(..., description="Trigger that fired")
    event_type: str = Field(..., description="Type of event")
    description: str = Field(..., description="Human-readable description")
    data: dict[str, Any] = Field(default_factory=dict, description="Event data")
    priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When event occurred",
    )
    handled: bool = Field(default=False, description="Whether event was handled")


# ============================================================================
# Protocols
# ============================================================================


class BeliefReaderProtocol(Protocol):
    """Protocol for reading beliefs."""

    async def get_belief(self, subject: str, predicate: str) -> Any | None:
        """Get a specific belief."""
        ...


class GoalCreatorProtocol(Protocol):
    """Protocol for creating goals."""

    async def add_goal(
        self,
        goal_type: str,
        description: str,
        priority: int,
        target: dict[str, Any],
    ) -> Any:
        """Add a new goal."""
        ...


# ============================================================================
# Event Monitoring System
# ============================================================================


class EventMonitoringSystem:
    """
    Monitors for events and triggers based on conditions.

    The system evaluates:
    1. Threshold triggers - Fire when belief values cross thresholds
    2. Time-based triggers - Fire at scheduled intervals
    3. External triggers - Fire on external events (emails, notifications)

    Example:
        >>> monitor = EventMonitoringSystem(employee_id, tenant_id)
        >>> monitor.register_threshold_trigger(
        ...     id="low_pipeline",
        ...     name="Low Pipeline Alert",
        ...     belief_subject="pipeline",
        ...     belief_predicate="coverage",
        ...     threshold=2.0,
        ...     comparison="less_than",
        ...     action={"type": "create_goal", "goal_type": "build_pipeline"}
        ... )
        >>> events = await monitor.check_triggers(beliefs=belief_system)
    """

    def __init__(
        self,
        employee_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """
        Initialize EventMonitoringSystem.

        Args:
            employee_id: Employee to monitor for
            tenant_id: Tenant ID for multi-tenancy
        """
        self.employee_id = employee_id
        self.tenant_id = tenant_id
        self.triggers: dict[str, EventTrigger] = {}
        self.pending_events: list[Event] = []
        self.event_handlers: dict[str, Callable[[Event], Awaitable[None]]] = {}

        logger.info(
            "Event monitoring system initialized",
            extra={
                "employee_id": str(employee_id),
                "tenant_id": str(tenant_id),
            },
        )

    # ========================================================================
    # Trigger Registration
    # ========================================================================

    def register_threshold_trigger(
        self,
        trigger_id: str,
        name: str,
        belief_subject: str,
        belief_predicate: str,
        threshold: float,
        comparison: str = "less_than",
        action: dict[str, Any] | None = None,
        cooldown_minutes: int = 60,
    ) -> EventTrigger:
        """
        Register a threshold-based trigger.

        Fires when a belief value crosses the specified threshold.

        Args:
            trigger_id: Unique trigger identifier
            name: Human-readable name
            belief_subject: Belief subject to monitor
            belief_predicate: Belief predicate to monitor
            threshold: Threshold value
            comparison: Comparison operator (less_than, greater_than, equals)
            action: Action to take when triggered
            cooldown_minutes: Minimum time between firings

        Returns:
            Registered trigger

        Example:
            >>> monitor.register_threshold_trigger(
            ...     trigger_id="low_pipeline",
            ...     name="Low Pipeline Coverage",
            ...     belief_subject="pipeline",
            ...     belief_predicate="coverage",
            ...     threshold=2.0,
            ...     comparison="less_than",
            ...     action={"type": "create_goal", "description": "Build pipeline"}
            ... )
        """
        trigger = EventTrigger(
            id=trigger_id,
            name=name,
            trigger_type="threshold",
            condition={
                "belief_subject": belief_subject,
                "belief_predicate": belief_predicate,
                "threshold": threshold,
                "comparison": comparison,
            },
            action=action or {},
            cooldown_minutes=cooldown_minutes,
        )
        self.triggers[trigger_id] = trigger

        logger.debug(
            f"Registered threshold trigger: {name}",
            extra={
                "trigger_id": trigger_id,
                "belief": f"{belief_subject}.{belief_predicate}",
                "threshold": threshold,
            },
        )

        return trigger

    def register_time_trigger(
        self,
        trigger_id: str,
        name: str,
        schedule: str,
        action: dict[str, Any] | None = None,
        cooldown_minutes: int = 60,
    ) -> EventTrigger:
        """
        Register a time-based trigger.

        Fires at specified intervals.

        Args:
            trigger_id: Unique trigger identifier
            name: Human-readable name
            schedule: Schedule type (hourly, daily, weekly, monthly)
            action: Action to take when triggered
            cooldown_minutes: Minimum time between firings

        Returns:
            Registered trigger

        Example:
            >>> monitor.register_time_trigger(
            ...     trigger_id="daily_planning",
            ...     name="Daily Planning Session",
            ...     schedule="daily",
            ...     action={"type": "strategic_planning"}
            ... )
        """
        trigger = EventTrigger(
            id=trigger_id,
            name=name,
            trigger_type="time_based",
            condition={"schedule": schedule},
            action=action or {},
            cooldown_minutes=cooldown_minutes,
        )
        self.triggers[trigger_id] = trigger

        logger.debug(
            f"Registered time trigger: {name}",
            extra={"trigger_id": trigger_id, "schedule": schedule},
        )

        return trigger

    def register_external_trigger(
        self,
        trigger_id: str,
        name: str,
        source: str,
        event_type: str,
        action: dict[str, Any] | None = None,
        cooldown_minutes: int = 5,
    ) -> EventTrigger:
        """
        Register an external event trigger.

        Fires when external events of specified type occur.

        Args:
            trigger_id: Unique trigger identifier
            name: Human-readable name
            source: Event source (email, calendar, slack, etc.)
            event_type: Type of event to listen for
            action: Action to take when triggered
            cooldown_minutes: Minimum time between firings

        Returns:
            Registered trigger

        Example:
            >>> monitor.register_external_trigger(
            ...     trigger_id="urgent_email",
            ...     name="Urgent Email Handler",
            ...     source="email",
            ...     event_type="urgent",
            ...     action={"type": "prioritize_response"}
            ... )
        """
        trigger = EventTrigger(
            id=trigger_id,
            name=name,
            trigger_type="external",
            condition={"source": source, "event_type": event_type},
            action=action or {},
            cooldown_minutes=cooldown_minutes,
        )
        self.triggers[trigger_id] = trigger

        logger.debug(
            f"Registered external trigger: {name}",
            extra={"trigger_id": trigger_id, "source": source, "event_type": event_type},
        )

        return trigger

    def unregister_trigger(self, trigger_id: str) -> bool:
        """
        Unregister a trigger.

        Args:
            trigger_id: Trigger to remove

        Returns:
            True if removed, False if not found
        """
        if trigger_id in self.triggers:
            del self.triggers[trigger_id]
            logger.debug(f"Unregistered trigger: {trigger_id}")
            return True
        return False

    # ========================================================================
    # Trigger Evaluation
    # ========================================================================

    async def check_triggers(
        self,
        beliefs: BeliefReaderProtocol | None = None,
    ) -> list[Event]:
        """
        Check all triggers and return fired events.

        Args:
            beliefs: Belief system for reading current beliefs

        Returns:
            List of events that were triggered
        """
        events: list[Event] = []
        now = datetime.now(UTC)

        for trigger_id, trigger in self.triggers.items():
            if not trigger.can_fire():
                continue

            fired = False

            if trigger.trigger_type == "threshold":
                fired = await self._check_threshold_trigger(trigger, beliefs)
            elif trigger.trigger_type == "time_based":
                fired = self._check_time_trigger(trigger, now)
            elif trigger.trigger_type == "external":
                # External triggers are handled separately via notify_external_event
                continue

            if fired:
                event = self._create_event(trigger)
                events.append(event)
                trigger.last_fired = now

                logger.info(
                    f"Trigger fired: {trigger.name}",
                    extra={
                        "trigger_id": trigger_id,
                        "event_id": event.id,
                        "employee_id": str(self.employee_id),
                    },
                )

        self.pending_events.extend(events)
        return events

    async def _check_threshold_trigger(
        self,
        trigger: EventTrigger,
        beliefs: BeliefReaderProtocol | None,
    ) -> bool:
        """Check if threshold trigger should fire."""
        if not beliefs:
            return False

        condition = trigger.condition
        subject = condition.get("belief_subject", "")
        predicate = condition.get("belief_predicate", "")
        threshold = condition.get("threshold", 0)
        comparison = condition.get("comparison", "less_than")

        try:
            belief = await beliefs.get_belief(subject, predicate)
            if belief is None:
                return False

            # Get value from belief object
            belief_obj = getattr(belief, "object", {}) or {}
            value = belief_obj.get("value")

            if value is None:
                return False

            # Evaluate comparison using operator mapping
            float_value = float(value)
            float_threshold = float(threshold)
            float_epsilon = 1e-9  # Tolerance for floating-point equality
            comparisons = {
                "less_than": float_value < float_threshold,
                "greater_than": float_value > float_threshold,
                "equals": abs(float_value - float_threshold) < float_epsilon,
                "less_than_or_equal": float_value <= float_threshold,
                "greater_than_or_equal": float_value >= float_threshold,
            }
            return comparisons.get(comparison, False)

        except Exception as e:
            logger.debug(f"Error checking threshold trigger: {e}")
            return False

    def _check_time_trigger(self, trigger: EventTrigger, now: datetime) -> bool:
        """Check if time-based trigger should fire."""
        condition = trigger.condition
        schedule = condition.get("schedule", "")

        # Calculate expected intervals
        if trigger.last_fired is None:
            # Never fired - fire now
            return True

        elapsed = now - trigger.last_fired

        # Map schedule names to their intervals
        schedule_intervals = {
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "monthly": timedelta(days=30),
            "every_5_minutes": timedelta(minutes=5),
            "every_15_minutes": timedelta(minutes=15),
        }

        interval = schedule_intervals.get(schedule)
        return elapsed >= interval if interval else False

    def _create_event(self, trigger: EventTrigger) -> Event:
        """Create event from triggered trigger."""
        import uuid

        return Event(
            id=str(uuid.uuid4()),
            trigger_id=trigger.id,
            event_type=trigger.trigger_type,
            description=f"Trigger fired: {trigger.name}",
            data={
                "trigger_name": trigger.name,
                "condition": trigger.condition,
                "action": trigger.action,
            },
            priority=trigger.action.get("priority", 5),
        )

    # ========================================================================
    # External Event Handling
    # ========================================================================

    def notify_external_event(
        self,
        source: str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> list[Event]:
        """
        Notify system of an external event.

        Checks external triggers and fires matching ones.

        Args:
            source: Event source (email, calendar, etc.)
            event_type: Type of event
            data: Event-specific data

        Returns:
            List of events triggered
        """
        events: list[Event] = []
        now = datetime.now(UTC)

        for trigger in self.triggers.values():
            if trigger.trigger_type != "external":
                continue
            if not trigger.can_fire():
                continue

            condition = trigger.condition
            if condition.get("source") == source and condition.get("event_type") == event_type:
                event = Event(
                    id=str(__import__("uuid").uuid4()),
                    trigger_id=trigger.id,
                    event_type="external",
                    description=f"External event: {trigger.name}",
                    data={
                        "source": source,
                        "event_type": event_type,
                        "event_data": data or {},
                        "action": trigger.action,
                    },
                    priority=trigger.action.get("priority", 7),
                )
                events.append(event)
                trigger.last_fired = now

                logger.info(
                    f"External trigger fired: {trigger.name}",
                    extra={
                        "trigger_id": trigger.id,
                        "source": source,
                        "event_type": event_type,
                    },
                )

        self.pending_events.extend(events)
        return events

    # ========================================================================
    # Event Processing
    # ========================================================================

    def get_pending_events(self, clear: bool = True) -> list[Event]:
        """
        Get pending events.

        Args:
            clear: Whether to clear pending events after returning

        Returns:
            List of pending events
        """
        events = list(self.pending_events)
        if clear:
            self.pending_events.clear()
        return events

    async def process_events(
        self,
        goals: GoalCreatorProtocol | None = None,
    ) -> int:
        """
        Process pending events by executing their actions.

        Args:
            goals: Goal system for creating goals

        Returns:
            Number of events processed
        """
        events = self.get_pending_events()
        processed = 0

        for event in events:
            try:
                await self._execute_event_action(event, goals)
                event.handled = True
                processed += 1
            except Exception as e:
                logger.error(
                    f"Error processing event: {e}",
                    extra={"event_id": event.id},
                )

        return processed

    async def _execute_event_action(
        self,
        event: Event,
        goals: GoalCreatorProtocol | None = None,
    ) -> None:
        """Execute the action associated with an event."""
        action = event.data.get("action", {})
        action_type = action.get("type", "")

        if action_type == "create_goal" and goals:
            await goals.add_goal(
                goal_type=action.get("goal_type", "event_triggered"),
                description=action.get("description", event.description),
                priority=action.get("priority", event.priority),
                target=action.get("target", {"event_id": event.id}),
            )
            logger.info(
                f"Created goal from event: {event.description}",
                extra={"event_id": event.id},
            )

        elif action_type == "log":
            logger.info(
                f"Event logged: {event.description}",
                extra={"event_id": event.id, "data": event.data},
            )

        # Custom handlers can be registered for other action types
        elif action_type in self.event_handlers:
            handler = self.event_handlers[action_type]
            await handler(event)

    def register_handler(
        self,
        action_type: str,
        handler: Callable[[Event], Awaitable[None]],
    ) -> None:
        """
        Register a custom event handler.

        Args:
            action_type: Action type to handle
            handler: Async callable to handle the event
        """
        self.event_handlers[action_type] = handler

    # ========================================================================
    # Standard Triggers
    # ========================================================================

    def register_standard_triggers(self) -> None:
        """
        Register standard triggers for common scenarios.

        Call this to set up default monitoring for:
        - Low pipeline coverage
        - At-risk customers
        - Daily planning
        - Weekly review
        """
        # Pipeline coverage trigger
        self.register_threshold_trigger(
            trigger_id="low_pipeline_coverage",
            name="Low Pipeline Coverage Alert",
            belief_subject="pipeline",
            belief_predicate="coverage",
            threshold=2.0,
            comparison="less_than",
            action={
                "type": "create_goal",
                "goal_type": "build_pipeline",
                "description": "Increase pipeline coverage to target",
                "priority": 8,
            },
            cooldown_minutes=60 * 4,  # 4 hours
        )

        # Customer health trigger
        self.register_threshold_trigger(
            trigger_id="at_risk_customer",
            name="At-Risk Customer Alert",
            belief_subject="customer",
            belief_predicate="health_score",
            threshold=70.0,
            comparison="less_than",
            action={
                "type": "create_goal",
                "goal_type": "customer_intervention",
                "description": "Address at-risk customer",
                "priority": 9,
            },
            cooldown_minutes=60 * 2,  # 2 hours
        )

        # Daily planning trigger
        self.register_time_trigger(
            trigger_id="daily_planning",
            name="Daily Planning Session",
            schedule="daily",
            action={
                "type": "strategic_planning",
                "priority": 6,
            },
            cooldown_minutes=60 * 20,  # 20 hours minimum
        )

        # Weekly review trigger
        self.register_time_trigger(
            trigger_id="weekly_review",
            name="Weekly Performance Review",
            schedule="weekly",
            action={
                "type": "deep_reflection",
                "priority": 5,
            },
            cooldown_minutes=60 * 24 * 5,  # 5 days minimum
        )

        # Urgent email trigger
        self.register_external_trigger(
            trigger_id="urgent_email",
            name="Urgent Email Handler",
            source="email",
            event_type="urgent",
            action={
                "type": "create_goal",
                "goal_type": "urgent_response",
                "description": "Respond to urgent email",
                "priority": 10,
            },
            cooldown_minutes=5,
        )

        logger.info(
            f"Registered {len(self.triggers)} standard triggers",
            extra={"employee_id": str(self.employee_id)},
        )
