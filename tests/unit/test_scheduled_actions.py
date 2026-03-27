"""
Tests for event-driven wake + scheduled actions.

Covers:
- Wake event infrastructure (wake(), _sleep_interruptible with event)
- Scheduled action tools (schedule, list, cancel)
- Due action checking at cycle start
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

# ============================================================================
# Wake Event Tests
# ============================================================================


class TestWakeEvent:
    """Tests for the wake event infrastructure in ProactiveExecutionLoop."""

    def _make_loop(self):
        from empla.core.loop.execution import ProactiveExecutionLoop
        from empla.core.loop.models import LoopConfig
        from empla.models.employee import Employee

        employee = Mock(spec=Employee)
        employee.id = uuid4()
        employee.name = "Test"
        employee.status = "active"
        employee.role = "sales_ae"
        employee.tenant_id = uuid4()

        beliefs = Mock()
        goals = Mock()
        intentions = Mock()
        memory = Mock()

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=beliefs,
            goals=goals,
            intentions=intentions,
            memory=memory,
            config=LoopConfig(cycle_interval_seconds=1),
        )
        return loop  # noqa: RET504

    def test_wake_event_exists(self):
        """Loop should have a _wake_event asyncio.Event."""
        loop = self._make_loop()
        assert hasattr(loop, "_wake_event")
        assert isinstance(loop._wake_event, asyncio.Event)

    def test_wake_sets_event(self):
        """wake() should set the event."""
        loop = self._make_loop()
        assert not loop._wake_event.is_set()
        loop.wake()
        assert loop._wake_event.is_set()

    @pytest.mark.asyncio
    async def test_sleep_interruptible_respects_wake(self):
        """_sleep_interruptible should return early when wake() is called."""
        loop = self._make_loop()
        loop.is_running = True

        async def wake_after_delay():
            await asyncio.sleep(0.05)
            loop.wake()

        _task = asyncio.create_task(wake_after_delay())  # noqa: RUF006

        start = asyncio.get_event_loop().time()
        await loop._sleep_interruptible(10.0)  # Would sleep 10s without wake
        elapsed = asyncio.get_event_loop().time() - start

        # Should have returned much faster than 10s
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_sleep_interruptible_normal_timeout(self):
        """_sleep_interruptible should return after timeout if no wake."""
        loop = self._make_loop()
        loop.is_running = True

        start = asyncio.get_event_loop().time()
        await loop._sleep_interruptible(0.1)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed >= 0.09  # Should have waited ~0.1s


# ============================================================================
# Scheduled Action Tool Tests
# ============================================================================


class TestScheduleActionTool:
    """Tests for the schedule_action tool."""

    @pytest.mark.asyncio
    async def test_schedule_by_hours(self):
        """schedule_action with hours_from_now should return valid schedule."""
        from empla.core.tools.scheduler import schedule_action

        result = await schedule_action(
            description="Follow up with Acme Corp",
            hours_from_now=3,
        )

        assert "action_id" in result
        assert result["description"] == "Follow up with Acme Corp"
        assert result["status"] == "scheduled"
        assert result["recurring"] is False

        # Should be ~3 hours from now
        scheduled = datetime.fromisoformat(result["scheduled_for"])
        now = datetime.now(UTC)
        delta = (scheduled - now).total_seconds()
        assert abs(delta - 3 * 3600) < 5  # Within 5s tolerance

    @pytest.mark.asyncio
    async def test_schedule_at_specific_time(self):
        """schedule_action with scheduled_at should use that time."""
        from empla.core.tools.scheduler import schedule_action

        target = "2026-12-25T09:00:00+00:00"
        result = await schedule_action(
            description="Christmas check",
            scheduled_at=target,
        )

        assert result["scheduled_for"] == datetime.fromisoformat(target).isoformat()

    @pytest.mark.asyncio
    async def test_schedule_recurring(self):
        """Recurring schedule should include interval."""
        from empla.core.tools.scheduler import schedule_action

        result = await schedule_action(
            description="Daily pipeline check",
            hours_from_now=24,
            recurring=True,
            interval_hours=24,
        )

        assert result["recurring"] is True
        assert result["interval_hours"] == 24

    @pytest.mark.asyncio
    async def test_schedule_with_context(self):
        """Context dict should be preserved."""
        from empla.core.tools.scheduler import schedule_action

        ctx = {"deal_id": "123", "contact": "john@acme.com"}
        result = await schedule_action(
            description="Deal follow-up",
            hours_from_now=1,
            context=ctx,
        )

        assert result["context"] == ctx

    @pytest.mark.asyncio
    async def test_schedule_invalid_datetime(self):
        """Invalid scheduled_at should return error."""
        from empla.core.tools.scheduler import schedule_action

        result = await schedule_action(
            description="Test",
            scheduled_at="not-a-date",
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_schedule_no_time_returns_error(self):
        """Neither hours_from_now nor scheduled_at should return error."""
        from empla.core.tools.scheduler import schedule_action

        result = await schedule_action(
            description="Test",
            hours_from_now=0,
            scheduled_at="",
        )

        assert "error" in result


class TestListScheduledActionsTool:
    """Tests for list_scheduled_actions tool."""

    @pytest.mark.asyncio
    async def test_returns_signal(self):
        """Should return a signal dict for the caller to populate."""
        from empla.core.tools.scheduler import list_scheduled_actions

        result = await list_scheduled_actions()
        assert result["_list_scheduled_actions"] is True


class TestCancelScheduledActionTool:
    """Tests for cancel_scheduled_action tool."""

    @pytest.mark.asyncio
    async def test_returns_cancel_signal(self):
        """Should return action_id and cancel signal."""
        from empla.core.tools.scheduler import cancel_scheduled_action

        result = await cancel_scheduled_action(action_id="test-123")
        assert result["action_id"] == "test-123"
        assert result["_cancel_scheduled_action"] is True


# ============================================================================
# Due Action Checking Tests
# ============================================================================


class TestCheckScheduledActions:
    """Tests for _check_scheduled_actions in the execution loop."""

    def _make_loop(self):
        from empla.core.loop.execution import ProactiveExecutionLoop
        from empla.core.loop.models import LoopConfig
        from empla.models.employee import Employee

        employee = Mock(spec=Employee)
        employee.id = uuid4()
        employee.name = "Test"
        employee.status = "active"
        employee.role = "sales_ae"
        employee.tenant_id = uuid4()

        beliefs = Mock()
        goals = Mock()
        intentions = Mock()
        memory = Mock()
        memory.working = Mock()
        memory.working.get_active_items = AsyncMock(return_value=[])
        memory.working.add_item = AsyncMock()
        memory.working.remove_item = AsyncMock()
        memory.working.refresh_item = AsyncMock()

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=beliefs,
            goals=goals,
            intentions=intentions,
            memory=memory,
            config=LoopConfig(cycle_interval_seconds=1),
        )
        return loop  # noqa: RET504

    def _make_scheduled_item(self, description="Test action", hours_ago=1, recurring=False):
        """Create a mock working memory item that looks like a scheduled action."""
        scheduled_for = datetime.now(UTC) - timedelta(hours=hours_ago)
        item = Mock()
        item.id = uuid4()
        item.item_type = "task"
        item.content = {
            "subtype": "scheduled_action",
            "description": description,
            "scheduled_for": scheduled_for.isoformat(),
            "recurring": recurring,
            "interval_hours": 24 if recurring else None,
        }
        return item

    @pytest.mark.asyncio
    async def test_injects_due_actions(self):
        """Due scheduled actions should be injected into working memory."""
        loop = self._make_loop()
        due_item = self._make_scheduled_item("Follow up with Acme", hours_ago=1)
        loop.memory.working.get_active_items = AsyncMock(return_value=[due_item])

        await loop._check_scheduled_actions()

        loop.memory.working.add_item.assert_called_once()
        call_kwargs = loop.memory.working.add_item.call_args.kwargs
        assert "SCHEDULED ACTION DUE" in call_kwargs["content"]["description"]
        assert call_kwargs["importance"] == 0.9

    @pytest.mark.asyncio
    async def test_removes_one_shot_after_fire(self):
        """Non-recurring actions should be removed after firing."""
        loop = self._make_loop()
        item = self._make_scheduled_item(recurring=False)
        loop.memory.working.get_active_items = AsyncMock(return_value=[item])

        await loop._check_scheduled_actions()

        loop.memory.working.remove_item.assert_called_once_with(item.id)

    @pytest.mark.asyncio
    async def test_reschedules_recurring(self):
        """Recurring actions should be removed and re-added with next run time."""
        loop = self._make_loop()
        item = self._make_scheduled_item(recurring=True)
        loop.memory.working.get_active_items = AsyncMock(return_value=[item])

        await loop._check_scheduled_actions()

        # Should remove the old item and add a new one with updated scheduled_for
        loop.memory.working.remove_item.assert_called_once_with(item.id)
        assert loop.memory.working.add_item.call_count == 2  # 1 due notification + 1 rescheduled
        # The second add_item should be the rescheduled action
        reschedule_call = loop.memory.working.add_item.call_args_list[1]
        assert reschedule_call.kwargs["item_type"] == "task"

    @pytest.mark.asyncio
    async def test_ignores_future_actions(self):
        """Actions not yet due should not fire."""
        loop = self._make_loop()
        future_item = Mock()
        future_item.id = uuid4()
        future_item.item_type = "task"
        future_item.content = {
            "subtype": "scheduled_action",
            "description": "Future action",
            "scheduled_for": (datetime.now(UTC) + timedelta(hours=5)).isoformat(),
        }
        loop.memory.working.get_active_items = AsyncMock(return_value=[future_item])

        await loop._check_scheduled_actions()

        loop.memory.working.add_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_non_scheduled_items(self):
        """Working memory items that aren't scheduled_action should be ignored."""
        loop = self._make_loop()
        other_item = Mock()
        other_item.item_type = "focus"
        other_item.content = {"description": "Current focus"}
        loop.memory.working.get_active_items = AsyncMock(return_value=[other_item])

        await loop._check_scheduled_actions()

        loop.memory.working.add_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_none_content(self):
        """Item with content=None should be skipped, not crash."""
        loop = self._make_loop()
        item = Mock()
        item.id = uuid4()
        item.item_type = "task"
        item.content = None
        loop.memory.working.get_active_items = AsyncMock(return_value=[item])

        await loop._check_scheduled_actions()
        loop.memory.working.add_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_scheduled_for(self):
        """Scheduled action without scheduled_for key should be skipped."""
        loop = self._make_loop()
        item = Mock()
        item.id = uuid4()
        item.item_type = "task"
        item.content = {"subtype": "scheduled_action", "description": "No time set"}
        loop.memory.working.get_active_items = AsyncMock(return_value=[item])

        await loop._check_scheduled_actions()
        loop.memory.working.add_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_unparseable_scheduled_for(self):
        """Scheduled action with garbage datetime should be skipped."""
        loop = self._make_loop()
        item = Mock()
        item.id = uuid4()
        item.item_type = "task"
        item.content = {
            "subtype": "scheduled_action",
            "description": "Bad time",
            "scheduled_for": "not-a-date",
        }
        loop.memory.working.get_active_items = AsyncMock(return_value=[item])

        await loop._check_scheduled_actions()
        loop.memory.working.add_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_due_actions_all_processed(self):
        """Multiple due actions should all be injected."""
        loop = self._make_loop()
        items = [
            self._make_scheduled_item("Action 1", hours_ago=1),
            self._make_scheduled_item("Action 2", hours_ago=2),
            self._make_scheduled_item("Action 3", hours_ago=0.5, recurring=True),
        ]
        loop.memory.working.get_active_items = AsyncMock(return_value=items)

        await loop._check_scheduled_actions()

        # 3 due notifications + 1 rescheduled recurring = 4 add_item calls
        assert loop.memory.working.add_item.call_count == 4
        # 3 removes (2 one-shot + 1 recurring before re-add)
        assert loop.memory.working.remove_item.call_count == 3

    @pytest.mark.asyncio
    async def test_no_working_memory_skips(self):
        """Without working memory, should skip gracefully."""
        loop = self._make_loop()
        loop.memory = Mock(spec=[])  # No working attribute

        await loop._check_scheduled_actions()  # Should not raise

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Errors should not crash the loop."""
        loop = self._make_loop()
        loop.memory.working.get_active_items = AsyncMock(side_effect=Exception("DB error"))

        await loop._check_scheduled_actions()  # Should not raise
