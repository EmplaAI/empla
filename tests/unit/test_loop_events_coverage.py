"""
Extended coverage tests for empla.core.loop.events.

Covers EventTrigger, Event, EventMonitoringSystem: trigger registration,
evaluation, external events, event processing, and edge cases.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.core.loop.events import (
    Event,
    EventMonitoringSystem,
    EventTrigger,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EMPLOYEE_ID = uuid4()
TENANT_ID = uuid4()


@pytest.fixture
def monitor() -> EventMonitoringSystem:
    return EventMonitoringSystem(employee_id=EMPLOYEE_ID, tenant_id=TENANT_ID)


# ---------------------------------------------------------------------------
# EventTrigger
# ---------------------------------------------------------------------------


class TestEventTrigger:
    def test_can_fire_enabled_never_fired(self):
        trigger = EventTrigger(
            id="t1",
            name="Test",
            trigger_type="threshold",
            condition={},
            action={},
        )
        assert trigger.can_fire() is True

    def test_can_fire_disabled(self):
        trigger = EventTrigger(
            id="t1",
            name="Test",
            trigger_type="threshold",
            condition={},
            action={},
            enabled=False,
        )
        assert trigger.can_fire() is False

    def test_can_fire_in_cooldown(self):
        trigger = EventTrigger(
            id="t1",
            name="Test",
            trigger_type="threshold",
            condition={},
            action={},
            cooldown_minutes=60,
            last_fired=datetime.now(UTC),
        )
        assert trigger.can_fire() is False

    def test_can_fire_cooldown_expired(self):
        trigger = EventTrigger(
            id="t1",
            name="Test",
            trigger_type="threshold",
            condition={},
            action={},
            cooldown_minutes=1,
            last_fired=datetime.now(UTC) - timedelta(minutes=5),
        )
        assert trigger.can_fire() is True


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class TestEvent:
    def test_defaults(self):
        e = Event(
            id="e1",
            trigger_id="t1",
            event_type="threshold",
            description="Test event",
        )
        assert e.data == {}
        assert e.priority == 5
        assert e.handled is False
        assert e.occurred_at is not None

    def test_priority_bounds(self):
        e = Event(
            id="e1",
            trigger_id="t1",
            event_type="test",
            description="High priority",
            priority=10,
        )
        assert e.priority == 10


# ---------------------------------------------------------------------------
# Trigger Registration
# ---------------------------------------------------------------------------


class TestTriggerRegistration:
    def test_register_threshold_trigger(self, monitor: EventMonitoringSystem):
        t = monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Low Pipeline",
            belief_subject="pipeline",
            belief_predicate="coverage",
            threshold=2.0,
            comparison="less_than",
            action={"type": "alert"},
            cooldown_minutes=30,
        )
        assert t.id == "t1"
        assert t.trigger_type == "threshold"
        assert t.condition["threshold"] == 2.0
        assert "t1" in monitor.triggers

    def test_register_time_trigger(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="daily",
            name="Daily Check",
            schedule="daily",
            action={"type": "planning"},
        )
        assert t.trigger_type == "time_based"
        assert t.condition["schedule"] == "daily"

    def test_register_external_trigger(self, monitor: EventMonitoringSystem):
        t = monitor.register_external_trigger(
            trigger_id="email",
            name="New Email",
            source="email",
            event_type="urgent",
            action={"type": "respond"},
        )
        assert t.trigger_type == "external"
        assert t.condition["source"] == "email"

    def test_unregister_trigger_found(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="x",
            belief_predicate="y",
            threshold=1.0,
        )
        assert monitor.unregister_trigger("t1") is True
        assert "t1" not in monitor.triggers

    def test_unregister_trigger_not_found(self, monitor: EventMonitoringSystem):
        assert monitor.unregister_trigger("nonexistent") is False

    def test_register_default_action(self, monitor: EventMonitoringSystem):
        """Triggers with no action get empty dict."""
        t = monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="x",
            belief_predicate="y",
            threshold=1.0,
        )
        assert t.action == {}


# ---------------------------------------------------------------------------
# Threshold Trigger Evaluation
# ---------------------------------------------------------------------------


class TestCheckThresholdTrigger:
    @pytest.mark.asyncio
    async def test_less_than_fires(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Low Value",
            belief_subject="metric",
            belief_predicate="value",
            threshold=5.0,
            comparison="less_than",
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": 3.0}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_greater_than_fires(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="High Value",
            belief_subject="metric",
            belief_predicate="value",
            threshold=5.0,
            comparison="greater_than",
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": 10.0}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_equals_fires(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Exact",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
            comparison="equals",
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": 5.0}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_less_than_or_equal_fires(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="LE",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
            comparison="less_than_or_equal",
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": 5.0}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_greater_than_or_equal_fires(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="GE",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
            comparison="greater_than_or_equal",
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": 5.0}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_does_not_fire_below_threshold(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Low",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
            comparison="greater_than",
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": 3.0}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_no_beliefs_does_not_fire(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
        )
        events = await monitor.check_triggers(beliefs=None)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_belief_none_does_not_fire(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
        )

        beliefs = AsyncMock()
        beliefs.get_belief.return_value = None

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_belief_value_none_does_not_fire(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": None}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_belief_no_object_attr_does_not_fire(self, monitor: EventMonitoringSystem):
        """Belief object without 'object' attribute returns None from getattr."""
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock(spec=[])  # No attributes
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_unknown_comparison_does_not_fire(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
            comparison="not_a_real_comparison",
        )

        beliefs = AsyncMock()
        belief_obj = MagicMock()
        belief_obj.object = {"value": 5.0}
        beliefs.get_belief.return_value = belief_obj

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_exception_in_belief_read_does_not_fire(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Test",
            belief_subject="m",
            belief_predicate="v",
            threshold=5.0,
        )

        beliefs = AsyncMock()
        beliefs.get_belief.side_effect = RuntimeError("db error")

        events = await monitor.check_triggers(beliefs=beliefs)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# Time Trigger Evaluation
# ---------------------------------------------------------------------------


class TestCheckTimeTrigger:
    @pytest.mark.asyncio
    async def test_never_fired_fires_immediately(self, monitor: EventMonitoringSystem):
        monitor.register_time_trigger(
            trigger_id="daily",
            name="Daily",
            schedule="daily",
        )
        events = await monitor.check_triggers()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_hourly_fires_after_interval(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="hourly",
            name="Hourly",
            schedule="hourly",
            cooldown_minutes=1,  # Low cooldown for test
        )
        t.last_fired = datetime.now(UTC) - timedelta(hours=2)

        events = await monitor.check_triggers()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_daily_does_not_fire_before_interval(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="daily",
            name="Daily",
            schedule="daily",
            cooldown_minutes=1,
        )
        t.last_fired = datetime.now(UTC) - timedelta(hours=12)

        events = await monitor.check_triggers()
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_weekly_schedule(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="weekly",
            name="Weekly",
            schedule="weekly",
            cooldown_minutes=1,
        )
        t.last_fired = datetime.now(UTC) - timedelta(weeks=2)

        events = await monitor.check_triggers()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_monthly_schedule(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="monthly",
            name="Monthly",
            schedule="monthly",
            cooldown_minutes=1,
        )
        t.last_fired = datetime.now(UTC) - timedelta(days=31)

        events = await monitor.check_triggers()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_every_5_minutes_schedule(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="freq",
            name="Frequent",
            schedule="every_5_minutes",
            cooldown_minutes=1,
        )
        t.last_fired = datetime.now(UTC) - timedelta(minutes=10)

        events = await monitor.check_triggers()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_every_15_minutes_schedule(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="freq15",
            name="15 min",
            schedule="every_15_minutes",
            cooldown_minutes=1,
        )
        t.last_fired = datetime.now(UTC) - timedelta(minutes=20)

        events = await monitor.check_triggers()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_unknown_schedule_does_not_fire(self, monitor: EventMonitoringSystem):
        t = monitor.register_time_trigger(
            trigger_id="unknown",
            name="Unknown",
            schedule="biweekly",
            cooldown_minutes=1,
        )
        t.last_fired = datetime.now(UTC) - timedelta(days=100)

        events = await monitor.check_triggers()
        assert len(events) == 0


# ---------------------------------------------------------------------------
# External Event Handling
# ---------------------------------------------------------------------------


class TestExternalEvents:
    def test_notify_matching_trigger(self, monitor: EventMonitoringSystem):
        monitor.register_external_trigger(
            trigger_id="urgent",
            name="Urgent Email",
            source="email",
            event_type="urgent",
            action={"type": "respond", "priority": 9},
        )

        events = monitor.notify_external_event("email", "urgent", {"from": "ceo@company.com"})
        assert len(events) == 1
        assert events[0].event_type == "external"
        assert events[0].data["source"] == "email"
        assert events[0].priority == 9

    def test_notify_no_matching_trigger(self, monitor: EventMonitoringSystem):
        monitor.register_external_trigger(
            trigger_id="urgent",
            name="Urgent Email",
            source="email",
            event_type="urgent",
        )

        events = monitor.notify_external_event("slack", "message")
        assert len(events) == 0

    def test_notify_skips_non_external_triggers(self, monitor: EventMonitoringSystem):
        monitor.register_threshold_trigger(
            trigger_id="t1",
            name="Threshold",
            belief_subject="x",
            belief_predicate="y",
            threshold=1.0,
        )
        events = monitor.notify_external_event("email", "urgent")
        assert len(events) == 0

    def test_notify_skips_in_cooldown(self, monitor: EventMonitoringSystem):
        t = monitor.register_external_trigger(
            trigger_id="urgent",
            name="Urgent",
            source="email",
            event_type="urgent",
            cooldown_minutes=60,
        )
        t.last_fired = datetime.now(UTC)

        events = monitor.notify_external_event("email", "urgent")
        assert len(events) == 0

    def test_notify_without_data(self, monitor: EventMonitoringSystem):
        monitor.register_external_trigger(
            trigger_id="t",
            name="T",
            source="email",
            event_type="new",
        )
        events = monitor.notify_external_event("email", "new")
        assert len(events) == 1
        assert events[0].data["event_data"] == {}

    def test_events_added_to_pending(self, monitor: EventMonitoringSystem):
        monitor.register_external_trigger(
            trigger_id="t",
            name="T",
            source="email",
            event_type="new",
        )
        monitor.notify_external_event("email", "new")
        assert len(monitor.pending_events) == 1


# ---------------------------------------------------------------------------
# check_triggers skips external triggers
# ---------------------------------------------------------------------------


class TestCheckTriggersSkipsExternal:
    @pytest.mark.asyncio
    async def test_external_triggers_not_evaluated(self, monitor: EventMonitoringSystem):
        monitor.register_external_trigger(
            trigger_id="ext",
            name="External",
            source="email",
            event_type="new",
        )
        events = await monitor.check_triggers()
        assert len(events) == 0


# ---------------------------------------------------------------------------
# Event Processing
# ---------------------------------------------------------------------------


class TestGetPendingEvents:
    def test_get_and_clear(self, monitor: EventMonitoringSystem):
        monitor.pending_events.append(
            Event(id="e1", trigger_id="t1", event_type="test", description="Test")
        )
        events = monitor.get_pending_events(clear=True)
        assert len(events) == 1
        assert len(monitor.pending_events) == 0

    def test_get_without_clear(self, monitor: EventMonitoringSystem):
        monitor.pending_events.append(
            Event(id="e1", trigger_id="t1", event_type="test", description="Test")
        )
        events = monitor.get_pending_events(clear=False)
        assert len(events) == 1
        assert len(monitor.pending_events) == 1


class TestProcessEvents:
    @pytest.mark.asyncio
    async def test_create_goal_action(self, monitor: EventMonitoringSystem):
        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="threshold",
                description="Low pipeline",
                data={
                    "action": {
                        "type": "create_goal",
                        "goal_type": "build_pipeline",
                        "description": "Build pipeline",
                        "priority": 8,
                        "target": {"metric": "coverage"},
                    }
                },
            )
        )

        goals = AsyncMock()
        processed = await monitor.process_events(goals=goals)
        assert processed == 1
        goals.add_goal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_action(self, monitor: EventMonitoringSystem):
        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="test",
                description="Log me",
                data={"action": {"type": "log"}},
            )
        )
        processed = await monitor.process_events()
        assert processed == 1

    @pytest.mark.asyncio
    async def test_custom_handler_action(self, monitor: EventMonitoringSystem):
        handler = AsyncMock()
        monitor.register_handler("custom_action", handler)

        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="test",
                description="Custom",
                data={"action": {"type": "custom_action"}},
            )
        )
        processed = await monitor.process_events()
        assert processed == 1
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_action_type(self, monitor: EventMonitoringSystem):
        """Events with unknown action types are still processed."""
        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="test",
                description="Unknown",
                data={"action": {"type": "unknown_type"}},
            )
        )
        processed = await monitor.process_events()
        assert processed == 1

    @pytest.mark.asyncio
    async def test_error_in_processing_logged(self, monitor: EventMonitoringSystem):
        """Errors during event processing are caught, event not counted."""
        handler = AsyncMock(side_effect=RuntimeError("handler failed"))
        monitor.register_handler("failing", handler)

        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="test",
                description="Fail",
                data={"action": {"type": "failing"}},
            )
        )
        processed = await monitor.process_events()
        assert processed == 0

    @pytest.mark.asyncio
    async def test_process_no_events(self, monitor: EventMonitoringSystem):
        processed = await monitor.process_events()
        assert processed == 0

    @pytest.mark.asyncio
    async def test_create_goal_defaults(self, monitor: EventMonitoringSystem):
        """create_goal uses defaults when action fields are missing."""
        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="test",
                description="Minimal goal",
                data={"action": {"type": "create_goal"}},
                priority=7,
            )
        )

        goals = AsyncMock()
        await monitor.process_events(goals=goals)
        goals.add_goal.assert_awaited_once()
        call_kwargs = goals.add_goal.call_args[1]
        assert call_kwargs["goal_type"] == "event_triggered"
        assert call_kwargs["priority"] == 7

    @pytest.mark.asyncio
    async def test_create_goal_without_goals_system(self, monitor: EventMonitoringSystem):
        """create_goal action without goals system is a no-op (no error)."""
        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="test",
                description="No goals",
                data={"action": {"type": "create_goal"}},
            )
        )
        processed = await monitor.process_events(goals=None)
        assert processed == 1

    @pytest.mark.asyncio
    async def test_event_with_no_action_key(self, monitor: EventMonitoringSystem):
        """Event data without 'action' key processes without error."""
        monitor.pending_events.append(
            Event(
                id="e1",
                trigger_id="t1",
                event_type="test",
                description="No action",
                data={},
            )
        )
        processed = await monitor.process_events()
        assert processed == 1


# ---------------------------------------------------------------------------
# Standard Triggers
# ---------------------------------------------------------------------------


class TestStandardTriggers:
    def test_register_standard_triggers(self, monitor: EventMonitoringSystem):
        monitor.register_standard_triggers()
        assert "low_pipeline_coverage" in monitor.triggers
        assert "at_risk_customer" in monitor.triggers
        assert "daily_planning" in monitor.triggers
        assert "weekly_review" in monitor.triggers
        assert "urgent_email" in monitor.triggers
        assert len(monitor.triggers) == 5


# ---------------------------------------------------------------------------
# Register Handler
# ---------------------------------------------------------------------------


class TestRegisterHandler:
    def test_register_and_overwrite(self, monitor: EventMonitoringSystem):
        h1 = AsyncMock()
        h2 = AsyncMock()
        monitor.register_handler("custom", h1)
        assert monitor.event_handlers["custom"] is h1

        monitor.register_handler("custom", h2)
        assert monitor.event_handlers["custom"] is h2


# ---------------------------------------------------------------------------
# Cooldown + multiple triggers
# ---------------------------------------------------------------------------


class TestCooldownAndMultipleTriggers:
    @pytest.mark.asyncio
    async def test_trigger_sets_last_fired(self, monitor: EventMonitoringSystem):
        """After firing, last_fired is set, preventing re-fire within cooldown."""
        monitor.register_time_trigger(
            trigger_id="t1",
            name="Quick",
            schedule="every_5_minutes",
            cooldown_minutes=120,
        )

        events1 = await monitor.check_triggers()
        assert len(events1) == 1

        # Second check should not fire (cooldown active)
        events2 = await monitor.check_triggers()
        assert len(events2) == 0

    @pytest.mark.asyncio
    async def test_multiple_triggers_fire_independently(self, monitor: EventMonitoringSystem):
        monitor.register_time_trigger(trigger_id="t1", name="A", schedule="daily")
        monitor.register_time_trigger(trigger_id="t2", name="B", schedule="hourly")

        events = await monitor.check_triggers()
        assert len(events) == 2
