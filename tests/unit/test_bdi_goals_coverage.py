"""
Unit tests for empla.bdi.goals.GoalSystem.

Covers all methods with mocked AsyncSession (no real DB).
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.bdi.goals import GoalSystem
from empla.models.employee import EmployeeGoal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_goal(**overrides):
    """Create a minimal EmployeeGoal-like object for testing."""
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "employee_id": uuid4(),
        "goal_type": "achievement",
        "description": "Close 10 deals",
        "priority": 8,
        "target": {"metric": "deals_closed", "value": 10},
        "current_progress": {},
        "status": "active",
        "completed_at": None,
        "abandoned_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_session():
    """Return AsyncMock session with common helpers wired."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _wire_execute_scalars(session, rows):
    """Make session.execute(...).scalars().all() return *rows*."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)


def _wire_execute_scalar_one_or_none(session, value):
    """Make session.execute(...).scalar_one_or_none() return *value*."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = value
    session.execute = AsyncMock(return_value=result_mock)


# ---------------------------------------------------------------------------
# Tests: __init__ / rollback
# ---------------------------------------------------------------------------


class TestGoalSystemInit:
    def test_stores_ids(self):
        session = _mock_session()
        eid, tid = uuid4(), uuid4()
        gs = GoalSystem(session, eid, tid)
        assert gs.employee_id == eid
        assert gs.tenant_id == tid
        assert gs.session is session

    @pytest.mark.asyncio
    async def test_rollback_delegates(self):
        session = _mock_session()
        gs = GoalSystem(session, uuid4(), uuid4())
        await gs.rollback()
        session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: add_goal
# ---------------------------------------------------------------------------


class TestAddGoal:
    @pytest.mark.asyncio
    async def test_creates_and_flushes(self):
        session = _mock_session()
        gs = GoalSystem(session, uuid4(), uuid4())

        goal = await gs.add_goal(
            goal_type="achievement",
            description="Build pipeline",
            priority=9,
            target={"metric": "pipeline_coverage", "value": 3.0},
        )

        assert isinstance(goal, EmployeeGoal)
        assert goal.status == "active"
        assert goal.priority == 9
        assert goal.current_progress == {}
        session.add.assert_called_once_with(goal)
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initial_progress(self):
        session = _mock_session()
        gs = GoalSystem(session, uuid4(), uuid4())
        progress = {"deals_closed": 2}
        goal = await gs.add_goal("achievement", "desc", 5, {}, current_progress=progress)
        assert goal.current_progress == progress


# ---------------------------------------------------------------------------
# Tests: get_goal
# ---------------------------------------------------------------------------


class TestGetGoal:
    @pytest.mark.asyncio
    async def test_returns_found_goal(self):
        session = _mock_session()
        expected = _make_goal()
        _wire_execute_scalar_one_or_none(session, expected)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_goal(expected.id)
        assert result is expected

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_goal(uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# Tests: get_active_goals
# ---------------------------------------------------------------------------


class TestGetActiveGoals:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        session = _mock_session()
        goals = [_make_goal(priority=9), _make_goal(priority=7)]
        _wire_execute_scalars(session, goals)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_active_goals()
        assert result == goals

    @pytest.mark.asyncio
    async def test_with_min_priority(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_active_goals(min_priority=7)
        assert result == []
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_active_goals()
        assert result == []


# ---------------------------------------------------------------------------
# Tests: get_pursuing_goals
# ---------------------------------------------------------------------------


class TestGetPursuingGoals:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        session = _mock_session()
        goals = [_make_goal(status="active"), _make_goal(status="in_progress")]
        _wire_execute_scalars(session, goals)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_pursuing_goals()
        assert result == goals

    @pytest.mark.asyncio
    async def test_returns_empty(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_pursuing_goals()
        assert result == []


# ---------------------------------------------------------------------------
# Tests: get_goals_by_status
# ---------------------------------------------------------------------------


class TestGetGoalsByStatus:
    @pytest.mark.asyncio
    async def test_returns_matching(self):
        session = _mock_session()
        goals = [_make_goal(status="completed")]
        _wire_execute_scalars(session, goals)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_goals_by_status("completed")
        assert result == goals


# ---------------------------------------------------------------------------
# Tests: update_goal_progress
# ---------------------------------------------------------------------------


class TestUpdateGoalProgress:
    @pytest.mark.asyncio
    async def test_merges_progress(self):
        session = _mock_session()
        goal = _make_goal(current_progress={"deals_closed": 2}, status="in_progress")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.update_goal_progress(goal.id, {"deals_closed": 5, "velocity": 0.3})

        assert result is goal
        assert result.current_progress["deals_closed"] == 5
        assert result.current_progress["velocity"] == 0.3

    @pytest.mark.asyncio
    async def test_auto_transitions_to_in_progress(self):
        session = _mock_session()
        goal = _make_goal(current_progress={}, status="active")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.update_goal_progress(goal.id, {"x": 1})
        assert result.status == "in_progress"

    @pytest.mark.asyncio
    async def test_does_not_transition_non_active(self):
        session = _mock_session()
        goal = _make_goal(status="in_progress")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.update_goal_progress(goal.id, {"x": 1})
        assert result.status == "in_progress"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.update_goal_progress(uuid4(), {"x": 1})
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_none_current_progress(self):
        session = _mock_session()
        goal = _make_goal(current_progress=None, status="active")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.update_goal_progress(goal.id, {"x": 1})
        assert result.current_progress == {"x": 1}


# ---------------------------------------------------------------------------
# Tests: complete_goal
# ---------------------------------------------------------------------------


class TestCompleteGoal:
    @pytest.mark.asyncio
    async def test_sets_completed(self):
        session = _mock_session()
        goal = _make_goal(status="in_progress")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.complete_goal(goal.id)
        assert result.status == "completed"
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_with_final_progress(self):
        session = _mock_session()
        goal = _make_goal(status="in_progress", current_progress={"deals": 8})
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.complete_goal(goal.id, final_progress={"deals": 10, "closed": True})
        assert result.current_progress["deals"] == 10
        assert result.current_progress["closed"] is True

    @pytest.mark.asyncio
    async def test_without_final_progress(self):
        session = _mock_session()
        goal = _make_goal(status="active", current_progress={"x": 1})
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.complete_goal(goal.id)
        assert result.current_progress == {"x": 1}

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.complete_goal(uuid4()) is None

    @pytest.mark.asyncio
    async def test_handles_none_current_progress_with_final(self):
        session = _mock_session()
        goal = _make_goal(status="active", current_progress=None)
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.complete_goal(goal.id, final_progress={"done": True})
        assert result.current_progress == {"done": True}


# ---------------------------------------------------------------------------
# Tests: abandon_goal
# ---------------------------------------------------------------------------


class TestAbandonGoal:
    @pytest.mark.asyncio
    async def test_sets_abandoned(self):
        session = _mock_session()
        goal = _make_goal(status="active")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.abandon_goal(goal.id)
        assert result.status == "abandoned"
        assert result.abandoned_at is not None

    @pytest.mark.asyncio
    async def test_with_reason(self):
        session = _mock_session()
        goal = _make_goal(status="active", current_progress={"x": 1})
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.abandon_goal(goal.id, reason="No longer relevant")
        assert result.current_progress["abandonment_reason"] == "No longer relevant"
        assert result.current_progress["x"] == 1

    @pytest.mark.asyncio
    async def test_without_reason(self):
        session = _mock_session()
        goal = _make_goal(status="active", current_progress={"x": 1})
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.abandon_goal(goal.id)
        assert "abandonment_reason" not in result.current_progress

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.abandon_goal(uuid4()) is None


# ---------------------------------------------------------------------------
# Tests: block_goal / unblock_goal
# ---------------------------------------------------------------------------


class TestBlockGoal:
    @pytest.mark.asyncio
    async def test_sets_blocked(self):
        session = _mock_session()
        goal = _make_goal(status="active")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.block_goal(goal.id, "Waiting for data")
        assert result.status == "blocked"
        assert result.current_progress["blocker"] == "Waiting for data"
        assert "blocked_at" in result.current_progress

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.block_goal(uuid4(), "reason") is None

    @pytest.mark.asyncio
    async def test_handles_none_progress(self):
        session = _mock_session()
        goal = _make_goal(status="active", current_progress=None)
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.block_goal(goal.id, "blocked")
        assert result.current_progress["blocker"] == "blocked"


class TestUnblockGoal:
    @pytest.mark.asyncio
    async def test_unblocks(self):
        session = _mock_session()
        goal = _make_goal(
            status="blocked",
            current_progress={"blocker": "Data", "blocked_at": "2025-01-01"},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.unblock_goal(goal.id)
        assert result.status == "active"
        assert "blocker" not in result.current_progress
        assert "blocked_at" not in result.current_progress
        assert "unblocked_at" in result.current_progress

    @pytest.mark.asyncio
    async def test_returns_unchanged_if_not_blocked(self):
        session = _mock_session()
        goal = _make_goal(status="active")
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.unblock_goal(goal.id)
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.unblock_goal(uuid4()) is None


# ---------------------------------------------------------------------------
# Tests: update_goal_priority
# ---------------------------------------------------------------------------


class TestUpdateGoalPriority:
    @pytest.mark.asyncio
    async def test_updates_priority(self):
        session = _mock_session()
        goal = _make_goal(priority=5)
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.update_goal_priority(goal.id, 10)
        assert result.priority == 10
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.update_goal_priority(uuid4(), 5) is None


# ---------------------------------------------------------------------------
# Tests: get_highest_priority_goal
# ---------------------------------------------------------------------------


class TestGetHighestPriorityGoal:
    @pytest.mark.asyncio
    async def test_returns_first(self):
        session = _mock_session()
        g1 = _make_goal(priority=10)
        g2 = _make_goal(priority=5)
        _wire_execute_scalars(session, [g1, g2])

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.get_highest_priority_goal()
        assert result is g1

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.get_highest_priority_goal() is None


# ---------------------------------------------------------------------------
# Tests: calculate_goal_progress_percentage
# ---------------------------------------------------------------------------


class TestCalculateProgress:
    @pytest.mark.asyncio
    async def test_normal_calculation(self):
        session = _mock_session()
        goal = _make_goal(
            target={"metric": "deals", "value": 10},
            current_progress={"deals": 5},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result == 50.0

    @pytest.mark.asyncio
    async def test_over_100_capped(self):
        session = _mock_session()
        goal = _make_goal(
            target={"metric": "deals", "value": 10},
            current_progress={"deals": 15},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result == 100.0

    @pytest.mark.asyncio
    async def test_zero_target_positive_current(self):
        session = _mock_session()
        goal = _make_goal(
            target={"metric": "errors", "value": 0},
            current_progress={"errors": 0},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result == 100.0

    @pytest.mark.asyncio
    async def test_zero_target_negative_current(self):
        session = _mock_session()
        goal = _make_goal(
            target={"metric": "errors", "value": 0},
            current_progress={"errors": -1},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_missing_metric_returns_none(self):
        session = _mock_session()
        goal = _make_goal(
            target={"value": 10},  # no "metric" key
            current_progress={},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_target_value_returns_none(self):
        session = _mock_session()
        goal = _make_goal(
            target={"metric": "deals"},  # no "value" key
            current_progress={"deals": 5},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_current_value_returns_none(self):
        session = _mock_session()
        goal = _make_goal(
            target={"metric": "deals", "value": 10},
            current_progress={},  # no "deals" key
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_goal_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.calculate_goal_progress_percentage(uuid4()) is None

    @pytest.mark.asyncio
    async def test_negative_clamped_to_zero(self):
        session = _mock_session()
        goal = _make_goal(
            target={"metric": "deals", "value": 10},
            current_progress={"deals": -5},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        result = await gs.calculate_goal_progress_percentage(goal.id)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Tests: should_focus_on_goal
# ---------------------------------------------------------------------------


class TestShouldFocusOnGoal:
    @pytest.mark.asyncio
    async def test_high_priority_active_returns_true(self):
        session = _mock_session()
        goal = _make_goal(status="active", priority=8)
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.should_focus_on_goal(goal.id) is True

    @pytest.mark.asyncio
    async def test_high_priority_in_progress_returns_true(self):
        session = _mock_session()
        goal = _make_goal(status="in_progress", priority=7)
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.should_focus_on_goal(goal.id) is True

    @pytest.mark.asyncio
    async def test_completed_goal_returns_false(self):
        session = _mock_session()
        goal = _make_goal(status="completed", priority=10)
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.should_focus_on_goal(goal.id) is False

    @pytest.mark.asyncio
    async def test_missing_goal_returns_false(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.should_focus_on_goal(uuid4()) is False

    @pytest.mark.asyncio
    async def test_low_priority_below_threshold_returns_true(self):
        """Low priority goal with progress below threshold => focus."""
        session = _mock_session()
        goal = _make_goal(
            status="active",
            priority=3,
            target={"metric": "deals", "value": 10},
            current_progress={"deals": 2},  # 20% < 50% threshold
        )
        # get_goal called twice: once by should_focus_on_goal, once by calculate_goal_progress_percentage
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.should_focus_on_goal(goal.id) is True

    @pytest.mark.asyncio
    async def test_low_priority_above_threshold_returns_false(self):
        """Low priority goal with progress above threshold => don't focus."""
        session = _mock_session()
        goal = _make_goal(
            status="active",
            priority=3,
            target={"metric": "deals", "value": 10},
            current_progress={"deals": 8},  # 80% > 50% threshold
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.should_focus_on_goal(goal.id) is False

    @pytest.mark.asyncio
    async def test_low_priority_no_progress_data_returns_true(self):
        """Low priority, can't calculate progress => focus (conservative)."""
        session = _mock_session()
        goal = _make_goal(
            status="active",
            priority=3,
            target={},  # no metric/value
            current_progress={},
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        assert await gs.should_focus_on_goal(goal.id) is True

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        session = _mock_session()
        goal = _make_goal(
            status="active",
            priority=3,
            target={"metric": "deals", "value": 10},
            current_progress={"deals": 3},  # 30%
        )
        _wire_execute_scalar_one_or_none(session, goal)

        gs = GoalSystem(session, uuid4(), uuid4())
        # 30% < 25% threshold => False
        assert await gs.should_focus_on_goal(goal.id, progress_threshold=25.0) is False
