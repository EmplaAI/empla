"""
Coverage tests for empla.core.loop.goal_management — uncovered lines.

Focuses on:
- _evaluate_goals_progress (TTL expiry, LLM batch evaluation, error paths)
- _evaluate_goals_progress_via_llm (validation, filtering, edge cases)
- _evaluate_non_numeric_goals edge cases (DB errors, invalid UUID, hook emission)
- _check_goal_achievement edge cases
- _complete_goal_with_retry (retry logic, completion_pending fallback)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from empla.core.loop.models import (
    GoalMetricResult,
    GoalProgressEvaluation,
    LoopConfig,
    NonNumericGoalBatchEvaluation,
    NonNumericGoalEvaluation,
)

# ============================================================================
# Helpers
# ============================================================================


class MockGoal:
    def __init__(
        self,
        description: str = "Test goal",
        goal_type: str = "achievement",
        priority: int = 5,
        target: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ):
        self.id = uuid4()
        self.description = description
        self.goal_type = goal_type
        self.priority = priority
        self.target = target or {}
        self.created_at = created_at or (datetime.now(UTC) - timedelta(hours=1))


class MockBeliefChange:
    def __init__(
        self,
        subject: str = "metric",
        predicate: str = "value",
        old_confidence: float = 0.3,
        new_confidence: float = 0.7,
    ):
        self.subject = subject
        self.predicate = predicate
        self.importance = 0.5
        self.old_confidence = old_confidence
        self.new_confidence = new_confidence
        self.belief = Mock(object={"value": 42})


def _make_goal_mgmt_mixin(*, llm: Any = None):
    from empla.core.loop.goal_management import GoalManagementMixin

    mixin = GoalManagementMixin()
    mixin.employee = Mock(id=uuid4())
    mixin.goals = Mock()
    mixin.goals.get_active_goals = AsyncMock(return_value=[])
    mixin.goals.get_pursuing_goals = AsyncMock(return_value=[])
    mixin.goals.update_goal_progress = AsyncMock()
    mixin.goals.complete_goal = AsyncMock(return_value=Mock())
    mixin.goals.abandon_goal = AsyncMock(return_value=Mock())
    mixin.llm_service = llm
    mixin.config = LoopConfig(cycle_interval_seconds=1)
    mixin._hooks = Mock()
    mixin._hooks.emit = AsyncMock()
    return mixin


# ============================================================================
# _evaluate_goals_progress
# ============================================================================


class TestEvaluateGoalsProgress:
    @pytest.mark.asyncio
    async def test_empty_beliefs_returns_empty(self):
        mixin = _make_goal_mgmt_mixin()
        result = await mixin._evaluate_goals_progress(goals=[MockGoal()], changed_beliefs=[])
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_goals_returns_empty(self):
        mixin = _make_goal_mgmt_mixin()
        result = await mixin._evaluate_goals_progress(
            goals=[], changed_beliefs=[MockBeliefChange()]
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_ttl_expired_goal_abandoned(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(
            goal_type="opportunity",
            target={"type": "opportunity", "max_age_hours": 1},
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        await mixin._evaluate_goals_progress(goals=[goal], changed_beliefs=[MockBeliefChange()])
        mixin.goals.abandon_goal.assert_called_once_with(goal.id)

    @pytest.mark.asyncio
    async def test_ttl_not_expired_not_abandoned(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(
            goal_type="opportunity",
            target={"type": "opportunity", "max_age_hours": 48},
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        await mixin._evaluate_goals_progress(goals=[goal], changed_beliefs=[MockBeliefChange()])
        mixin.goals.abandon_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_ttl_abandon_failure_handled(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(
            goal_type="opportunity",
            target={"type": "opportunity", "max_age_hours": 1},
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        mixin.goals.abandon_goal = AsyncMock(side_effect=RuntimeError("DB"))
        # Should not raise
        await mixin._evaluate_goals_progress(goals=[goal], changed_beliefs=[MockBeliefChange()])

    @pytest.mark.asyncio
    async def test_no_numeric_goals_returns_empty(self):
        mixin = _make_goal_mgmt_mixin(llm=Mock())
        goal = MockGoal(target={"type": "opportunity"})  # no metric/value
        result = await mixin._evaluate_goals_progress(
            goals=[goal], changed_beliefs=[MockBeliefChange()]
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_llm_returns_empty(self):
        mixin = _make_goal_mgmt_mixin(llm=None)
        goal = MockGoal(target={"metric": "deals", "value": 10})
        result = await mixin._evaluate_goals_progress(
            goals=[goal], changed_beliefs=[MockBeliefChange()]
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self):
        llm = Mock()
        llm.generate_structured = AsyncMock(side_effect=RuntimeError("API"))
        mixin = _make_goal_mgmt_mixin(llm=llm)
        goal = MockGoal(target={"metric": "deals", "value": 10})
        result = await mixin._evaluate_goals_progress(
            goals=[goal], changed_beliefs=[MockBeliefChange()]
        )
        assert result == {}


# ============================================================================
# _evaluate_goals_progress_via_llm
# ============================================================================


class TestEvaluateGoalsProgressViaLLM:
    @pytest.mark.asyncio
    async def test_successful_evaluation(self):
        llm = Mock()
        goal = MockGoal(target={"metric": "deals_closed", "value": 10})
        eval_result = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(goal.id),
                    metric="deals_closed",
                    current_value=7.0,
                    confidence=0.8,
                    reasoning="From belief changes",
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(Mock(), eval_result))
        mixin = _make_goal_mgmt_mixin(llm=llm)

        result = await mixin._evaluate_goals_progress_via_llm(
            goals=[goal],
            beliefs_text="some beliefs",
            goals_text="some goals",
        )
        assert str(goal.id) in result
        assert result[str(goal.id)]["deals_closed"] == 7.0

    @pytest.mark.asyncio
    async def test_filters_null_current_value(self):
        llm = Mock()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        eval_result = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(goal.id),
                    metric="deals",
                    current_value=None,
                    confidence=0.8,
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(Mock(), eval_result))
        mixin = _make_goal_mgmt_mixin(llm=llm)

        result = await mixin._evaluate_goals_progress_via_llm([goal], "beliefs", "goals")
        assert result == {}

    @pytest.mark.asyncio
    async def test_filters_low_confidence(self):
        llm = Mock()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        eval_result = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(goal.id),
                    metric="deals",
                    current_value=5.0,
                    confidence=0.2,  # below 0.3 threshold
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(Mock(), eval_result))
        mixin = _make_goal_mgmt_mixin(llm=llm)

        result = await mixin._evaluate_goals_progress_via_llm([goal], "beliefs", "goals")
        assert result == {}

    @pytest.mark.asyncio
    async def test_filters_unknown_goal_id(self):
        llm = Mock()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        eval_result = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(uuid4()),  # unknown
                    metric="deals",
                    current_value=5.0,
                    confidence=0.8,
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(Mock(), eval_result))
        mixin = _make_goal_mgmt_mixin(llm=llm)

        result = await mixin._evaluate_goals_progress_via_llm([goal], "beliefs", "goals")
        assert result == {}

    @pytest.mark.asyncio
    async def test_filters_wrong_metric(self):
        llm = Mock()
        goal = MockGoal(target={"metric": "deals_closed", "value": 10})
        eval_result = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(goal.id),
                    metric="revenue",  # wrong metric
                    current_value=5.0,
                    confidence=0.8,
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(Mock(), eval_result))
        mixin = _make_goal_mgmt_mixin(llm=llm)

        result = await mixin._evaluate_goals_progress_via_llm([goal], "beliefs", "goals")
        assert result == {}


# ============================================================================
# _evaluate_non_numeric_goals — additional edge cases
# ============================================================================


class TestEvaluateNonNumericGoalsEdgeCases:
    @pytest.mark.asyncio
    async def test_no_changed_beliefs_returns_early(self):
        llm = Mock()
        mixin = _make_goal_mgmt_mixin(llm=llm)
        goal = MockGoal(goal_type="opportunity", target={"type": "opportunity"})
        await mixin._evaluate_non_numeric_goals([goal], [])
        llm.generate_structured = AsyncMock()
        llm.generate_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_on_complete_goal(self):
        llm = Mock()
        mixin = _make_goal_mgmt_mixin(llm=llm)
        goal = MockGoal(goal_type="opportunity", target={"type": "opportunity"})
        eval_result = NonNumericGoalBatchEvaluation(
            results=[
                NonNumericGoalEvaluation(
                    goal_id=str(goal.id),
                    is_complete=True,
                    confidence=0.9,
                    reasoning="Done",
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(None, eval_result))
        mixin.goals.complete_goal = AsyncMock(side_effect=RuntimeError("DB"))

        # Should not raise
        await mixin._evaluate_non_numeric_goals([goal], [MockBeliefChange()])
        # complete_goal was attempted but failed
        mixin.goals.complete_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_goal_returns_none(self):
        llm = Mock()
        mixin = _make_goal_mgmt_mixin(llm=llm)
        goal = MockGoal(goal_type="opportunity", target={"type": "opportunity"})
        eval_result = NonNumericGoalBatchEvaluation(
            results=[
                NonNumericGoalEvaluation(
                    goal_id=str(goal.id),
                    is_complete=True,
                    confidence=0.9,
                    reasoning="Done",
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(None, eval_result))
        mixin.goals.complete_goal = AsyncMock(return_value=None)

        await mixin._evaluate_non_numeric_goals([goal], [MockBeliefChange()])
        # Hook should NOT be emitted since complete_goal returned None
        mixin._hooks.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_hook_emitted_on_completion(self):
        llm = Mock()
        mixin = _make_goal_mgmt_mixin(llm=llm)
        goal = MockGoal(
            goal_type="opportunity",
            description="Fix pipeline",
            target={"type": "opportunity"},
        )
        eval_result = NonNumericGoalBatchEvaluation(
            results=[
                NonNumericGoalEvaluation(
                    goal_id=str(goal.id),
                    is_complete=True,
                    confidence=0.85,
                    reasoning="Pipeline resolved",
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(None, eval_result))

        await mixin._evaluate_non_numeric_goals([goal], [MockBeliefChange()])
        mixin._hooks.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_hook_failure_doesnt_crash(self):
        llm = Mock()
        mixin = _make_goal_mgmt_mixin(llm=llm)
        goal = MockGoal(goal_type="opportunity", target={"type": "opportunity"})
        eval_result = NonNumericGoalBatchEvaluation(
            results=[
                NonNumericGoalEvaluation(
                    goal_id=str(goal.id),
                    is_complete=True,
                    confidence=0.9,
                    reasoning="Done",
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(None, eval_result))
        mixin._hooks.emit = AsyncMock(side_effect=RuntimeError("Hook error"))

        # Should not raise
        await mixin._evaluate_non_numeric_goals([goal], [MockBeliefChange()])

    @pytest.mark.asyncio
    async def test_invalid_uuid_from_llm_skipped(self):
        llm = Mock()
        mixin = _make_goal_mgmt_mixin(llm=llm)
        goal = MockGoal(goal_type="opportunity", target={"type": "opportunity"})
        eval_result = NonNumericGoalBatchEvaluation(
            results=[
                NonNumericGoalEvaluation(
                    goal_id="not-a-uuid",  # will be in valid_ids check first
                    is_complete=True,
                    confidence=0.9,
                    reasoning="Done",
                )
            ]
        )
        llm.generate_structured = AsyncMock(return_value=(None, eval_result))

        await mixin._evaluate_non_numeric_goals([goal], [MockBeliefChange()])
        mixin.goals.complete_goal.assert_not_called()


# ============================================================================
# _check_goal_achievement
# ============================================================================


class TestCheckGoalAchievement:
    @pytest.mark.asyncio
    async def test_maintenance_goal_stays_active(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(
            goal_type="maintenance",
            target={"metric": "coverage", "value": 3.0},
        )
        await mixin._check_goal_achievement(goal, {"coverage": 4.0})
        mixin.goals.complete_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_metric_returns_early(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={})
        await mixin._check_goal_achievement(goal, {"x": 1})
        mixin.goals.complete_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_target_value_returns_early(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={"metric": "x"})
        await mixin._check_goal_achievement(goal, {"x": 1})
        mixin.goals.complete_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_metric_not_in_progress(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        await mixin._check_goal_achievement(goal, {"other": 15})
        mixin.goals.complete_goal.assert_not_called()


# ============================================================================
# _complete_goal_with_retry
# ============================================================================


class TestCompleteGoalWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        await mixin._complete_goal_with_retry(goal, {"deals": 12}, "deals", 12, 10)
        mixin.goals.complete_goal.assert_called_once()
        mixin._hooks.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        mixin.goals.complete_goal = AsyncMock(
            side_effect=[RuntimeError("DB"), None]  # fail then succeed
        )
        await mixin._complete_goal_with_retry(goal, {"deals": 12}, "deals", 12, 10)
        assert mixin.goals.complete_goal.call_count == 2
        mixin._hooks.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_retries_fail_marks_completion_pending(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        mixin.goals.complete_goal = AsyncMock(side_effect=RuntimeError("DB"))

        await mixin._complete_goal_with_retry(goal, {"deals": 12}, "deals", 12, 10, max_attempts=2)
        assert mixin.goals.complete_goal.call_count == 2
        # Should mark as completion_pending
        mixin.goals.update_goal_progress.assert_called_once_with(
            goal.id, {"_completion_pending": True}
        )
        mixin._hooks.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_completion_pending_fallback_also_fails(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        mixin.goals.complete_goal = AsyncMock(side_effect=RuntimeError("DB"))
        mixin.goals.update_goal_progress = AsyncMock(side_effect=RuntimeError("DB too"))

        # Should not raise
        await mixin._complete_goal_with_retry(goal, {"deals": 12}, "deals", 12, 10, max_attempts=1)

    @pytest.mark.asyncio
    async def test_strips_completion_pending_flag(self):
        mixin = _make_goal_mgmt_mixin()
        goal = MockGoal(target={"metric": "deals", "value": 10})
        progress = {"deals": 12, "_completion_pending": True}

        await mixin._complete_goal_with_retry(goal, progress, "deals", 12, 10)
        # Should strip _completion_pending before passing to complete_goal
        call_args = mixin.goals.complete_goal.call_args
        clean_progress = call_args[0][1]
        assert "_completion_pending" not in clean_progress
