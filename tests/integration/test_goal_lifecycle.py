"""
Integration tests for goal lifecycle: progress evaluation → achievement → hooks.

Tests the full path from belief changes through LLM-driven progress evaluation
to goal completion and hook emission, using mock LLM and real loop logic.
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from empla.core.hooks import HOOK_GOAL_ACHIEVED, HookRegistry
from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.loop.models import (
    GoalMetricResult,
    GoalProgressEvaluation,
    LoopConfig,
)
from empla.llm.models import LLMResponse, TokenUsage
from empla.models.employee import Employee
from empla.services.activity_recorder import ActivityRecorder

# ============================================================================
# Mocks
# ============================================================================


class MockBeliefChange:
    """Mock belief change with optional .belief attribute."""

    def __init__(
        self,
        subject: str,
        predicate: str,
        importance: float = 0.7,
        old_confidence: float = 0.5,
        new_confidence: float = 0.9,
        belief_object: dict | None = None,
    ) -> None:
        self.subject = subject
        self.predicate = predicate
        self.importance = importance
        self.old_confidence = old_confidence
        self.new_confidence = new_confidence
        if belief_object is not None:
            self.belief = Mock()
            self.belief.object = belief_object
        else:
            self.belief = None


class MockGoal:
    """Mock goal with target and status tracking."""

    def __init__(
        self,
        goal_type: str = "achievement",
        target: dict | None = None,
        description: str = "Test goal",
        current_progress: dict | None = None,
    ) -> None:
        self.id = uuid4()
        self.goal_type = goal_type
        self.description = description
        self.target = target or {}
        self.current_progress = current_progress or {}


def _make_llm_response() -> LLMResponse:
    return LLMResponse(
        content="",
        model="test",
        usage=TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30),
        finish_reason="end_turn",
    )


def _make_loop(
    mock_goals: AsyncMock | None = None,
    llm_service: Mock | None = None,
) -> ProactiveExecutionLoop:
    """Create a ProactiveExecutionLoop with minimal mocks."""
    employee = Mock(spec=Employee)
    employee.id = uuid4()
    employee.name = "Test Employee"
    employee.role = "sales_ae"
    employee.status = "active"

    beliefs = Mock()
    beliefs.update_beliefs = AsyncMock(return_value=[])
    beliefs.get_all_beliefs = AsyncMock(return_value=[])

    goals = mock_goals or Mock()
    if mock_goals is None:
        goals.get_active_goals = AsyncMock(return_value=[])
        goals.get_pursuing_goals = AsyncMock(return_value=[])
        goals.update_goal_progress = AsyncMock()
        goals.complete_goal = AsyncMock()
        goals.get_goal = AsyncMock(return_value=None)

    intentions = Mock()
    intentions.get_next_intention = AsyncMock(return_value=None)

    return ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=Mock(),
        config=LoopConfig(cycle_interval_seconds=1),
        llm_service=llm_service,
    )


# ============================================================================
# Tests: LLM-driven goal progress evaluation
# ============================================================================


class TestGoalProgressViaLLM:
    """Test LLM-driven goal progress evaluation."""

    @pytest.mark.asyncio
    async def test_llm_returns_progress_for_matching_goal(self) -> None:
        """LLM evaluation returns progress when beliefs match a goal's metric."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals_closed", "value": 10},
        )

        beliefs = [
            MockBeliefChange(
                subject="sales",
                predicate="deals_closed_count",
                belief_object={"value": 7},
            )
        ]

        evaluation = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(goal.id),
                    metric="deals_closed",
                    current_value=7.0,
                    confidence=0.9,
                    reasoning="Belief indicates 7 deals closed",
                )
            ]
        )

        llm = Mock()
        llm.generate_structured = AsyncMock(return_value=(_make_llm_response(), evaluation))

        loop = _make_loop(llm_service=llm)
        result = await loop._evaluate_goals_progress([goal], beliefs)

        assert str(goal.id) in result
        assert result[str(goal.id)]["deals_closed"] == 7.0
        assert result[str(goal.id)]["llm_confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_llm_returns_empty_when_no_relevant_beliefs(self) -> None:
        """LLM returns no progress when beliefs don't relate to goals."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals_closed", "value": 10},
        )

        beliefs = [MockBeliefChange(subject="weather", predicate="sunny")]

        evaluation = GoalProgressEvaluation(results=[])

        llm = Mock()
        llm.generate_structured = AsyncMock(return_value=(_make_llm_response(), evaluation))

        loop = _make_loop(llm_service=llm)
        result = await loop._evaluate_goals_progress([goal], beliefs)

        assert result == {}

    @pytest.mark.asyncio
    async def test_batches_multiple_goals_in_single_call(self) -> None:
        """Multiple goals are evaluated in a single LLM call."""
        goal1 = MockGoal(target={"metric": "deals_closed", "value": 10})
        goal2 = MockGoal(
            goal_type="maintenance",
            target={"metric": "pipeline_coverage", "value": 3.0},
        )

        beliefs = [
            MockBeliefChange(subject="sales", predicate="metrics", belief_object={"value": 5})
        ]

        evaluation = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(goal1.id),
                    metric="deals_closed",
                    current_value=5.0,
                    confidence=0.8,
                ),
                GoalMetricResult(
                    goal_id=str(goal2.id),
                    metric="pipeline_coverage",
                    current_value=3.5,
                    confidence=0.7,
                ),
            ]
        )

        llm = Mock()
        llm.generate_structured = AsyncMock(return_value=(_make_llm_response(), evaluation))

        loop = _make_loop(llm_service=llm)
        result = await loop._evaluate_goals_progress([goal1, goal2], beliefs)

        # Both goals should have progress
        assert str(goal1.id) in result
        assert str(goal2.id) in result
        # Only one LLM call
        assert llm.generate_structured.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_beliefs_returns_no_progress(self) -> None:
        """No LLM call when there are no belief changes."""
        goal = MockGoal(target={"metric": "deals_closed", "value": 10})

        llm = Mock()
        llm.generate_structured = AsyncMock()

        loop = _make_loop(llm_service=llm)
        result = await loop._evaluate_goals_progress([goal], [])

        assert result == {}
        llm.generate_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_goals_without_targets_are_skipped(self) -> None:
        """Goals with no metric or no value are not evaluated."""
        goal_no_metric = MockGoal(target={"value": 10})
        goal_no_value = MockGoal(target={"metric": "deals_closed"})

        beliefs = [MockBeliefChange(subject="sales", predicate="update")]

        llm = Mock()
        llm.generate_structured = AsyncMock()

        loop = _make_loop(llm_service=llm)
        result = await loop._evaluate_goals_progress([goal_no_metric, goal_no_value], beliefs)

        assert result == {}
        llm.generate_structured.assert_not_called()


# ============================================================================
# Tests: Heuristic fallback
# ============================================================================


class TestGoalProgressHeuristicFallback:
    """Test heuristic fallback when LLM is unavailable."""

    @pytest.mark.asyncio
    async def test_falls_back_to_heuristic_when_no_llm(self) -> None:
        """Uses heuristic when llm_service is None."""
        goal = MockGoal(target={"metric": "pipeline_coverage", "value": 3.0})

        beliefs = [
            MockBeliefChange(
                subject="pipeline",
                predicate="coverage",
                belief_object={"value": 3.5},
            )
        ]

        loop = _make_loop(llm_service=None)
        result = await loop._evaluate_goals_progress([goal], beliefs)

        assert str(goal.id) in result
        assert result[str(goal.id)]["pipeline_coverage"] == 3.5

    @pytest.mark.asyncio
    async def test_falls_back_to_heuristic_on_llm_error(self) -> None:
        """Falls back to heuristic when LLM call fails."""
        goal = MockGoal(target={"metric": "pipeline_coverage", "value": 3.0})

        beliefs = [
            MockBeliefChange(
                subject="pipeline",
                predicate="coverage",
                belief_object={"value": 2.8},
            )
        ]

        llm = Mock()
        llm.generate_structured = AsyncMock(side_effect=RuntimeError("LLM down"))

        loop = _make_loop(llm_service=llm)
        result = await loop._evaluate_goals_progress([goal], beliefs)

        # Should still get heuristic result
        assert str(goal.id) in result
        assert result[str(goal.id)]["pipeline_coverage"] == 2.8

    @pytest.mark.asyncio
    async def test_heuristic_no_match_returns_empty(self) -> None:
        """Heuristic returns empty when beliefs don't match metric pattern."""
        goal = MockGoal(target={"metric": "deals_closed", "value": 10})

        beliefs = [
            MockBeliefChange(
                subject="weather",
                predicate="forecast",
                belief_object={"value": "sunny"},
            )
        ]

        loop = _make_loop(llm_service=None)
        result = await loop._evaluate_goals_progress([goal], beliefs)

        assert result == {}


# ============================================================================
# Tests: Goal achievement lifecycle
# ============================================================================


class TestGoalAchievementLifecycle:
    """Test the full goal achievement path."""

    @pytest.mark.asyncio
    async def test_achievement_goal_completed_on_target_met(self) -> None:
        """Achievement goal is completed when metric reaches target."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals_closed", "value": 10},
        )

        mock_goals = Mock()
        mock_goals.get_active_goals = AsyncMock(return_value=[])
        mock_goals.get_pursuing_goals = AsyncMock(return_value=[])
        mock_goals.update_goal_progress = AsyncMock()
        mock_goals.complete_goal = AsyncMock()
        mock_goals.get_goal = AsyncMock(return_value=None)

        loop = _make_loop(mock_goals=mock_goals)
        progress = {"deals_closed": 12}

        await loop._check_goal_achievement(goal, progress)

        mock_goals.complete_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_maintain_goal_stays_active_after_target_met(self) -> None:
        """Maintenance goal stays active when metric meets target."""
        goal = MockGoal(
            goal_type="maintenance",
            target={"metric": "pipeline_coverage", "value": 3.0},
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock()

        loop = _make_loop(mock_goals=mock_goals)
        progress = {"pipeline_coverage": 4.0}

        await loop._check_goal_achievement(goal, progress)

        mock_goals.complete_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_maintain_alias_also_stays_active(self) -> None:
        """Goal type 'maintain' (alias for 'maintenance') stays active."""
        goal = MockGoal(
            goal_type="maintain",
            target={"metric": "pipeline_coverage", "value": 3.0},
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock()

        loop = _make_loop(mock_goals=mock_goals)
        await loop._check_goal_achievement(goal, {"pipeline_coverage": 5.0})

        mock_goals.complete_goal.assert_not_called()


# ============================================================================
# Tests: Goal achievement hook emission
# ============================================================================


class TestGoalAchievementHook:
    """Test HOOK_GOAL_ACHIEVED emission."""

    @pytest.mark.asyncio
    async def test_hook_emitted_on_goal_completion(self) -> None:
        """HOOK_GOAL_ACHIEVED fires after successful goal completion."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals_closed", "value": 10},
            description="Close 10 deals",
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock()
        mock_goals.get_active_goals = AsyncMock(return_value=[])
        mock_goals.get_pursuing_goals = AsyncMock(return_value=[])
        mock_goals.update_goal_progress = AsyncMock()
        mock_goals.get_goal = AsyncMock(return_value=None)

        loop = _make_loop(mock_goals=mock_goals)

        hook_calls: list[dict] = []

        async def capture_hook(**kwargs):
            hook_calls.append(kwargs)

        loop._hooks.register(HOOK_GOAL_ACHIEVED, capture_hook)

        await loop._check_goal_achievement(goal, {"deals_closed": 15})

        assert len(hook_calls) == 1
        assert hook_calls[0]["goal_id"] == goal.id
        assert hook_calls[0]["goal_description"] == "Close 10 deals"
        assert hook_calls[0]["metric"] == "deals_closed"
        assert hook_calls[0]["current_value"] == 15
        assert hook_calls[0]["target_value"] == 10
        assert hook_calls[0]["goal_type"] == "achievement"

    @pytest.mark.asyncio
    async def test_hook_not_emitted_for_maintain_goal(self) -> None:
        """HOOK_GOAL_ACHIEVED does not fire for maintenance goals."""
        goal = MockGoal(
            goal_type="maintenance",
            target={"metric": "coverage", "value": 3.0},
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock()

        loop = _make_loop(mock_goals=mock_goals)

        hook_calls: list[dict] = []

        async def capture_hook(**kwargs):
            hook_calls.append(kwargs)

        loop._hooks.register(HOOK_GOAL_ACHIEVED, capture_hook)

        await loop._check_goal_achievement(goal, {"coverage": 5.0})

        assert len(hook_calls) == 0

    @pytest.mark.asyncio
    async def test_hook_not_emitted_on_completion_failure(self) -> None:
        """HOOK_GOAL_ACHIEVED does not fire when complete_goal fails."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals_closed", "value": 10},
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock(side_effect=RuntimeError("DB error"))
        mock_goals.update_goal_progress = AsyncMock()

        loop = _make_loop(mock_goals=mock_goals)

        hook_calls: list[dict] = []

        async def capture_hook(**kwargs):
            hook_calls.append(kwargs)

        loop._hooks.register(HOOK_GOAL_ACHIEVED, capture_hook)

        await loop._check_goal_achievement(goal, {"deals_closed": 15})

        assert len(hook_calls) == 0


# ============================================================================
# Tests: ActivityRecorder goal achievement handler
# ============================================================================


class TestActivityRecorderGoalAchieved:
    """Test ActivityRecorder._on_goal_achieved handler."""

    @pytest.mark.asyncio
    async def test_goal_achieved_activity_recorded(self) -> None:
        """ActivityRecorder records GOAL_ACHIEVED activity."""
        session = AsyncMock()
        session.add = Mock()

        recorder = ActivityRecorder(
            session=session,
            tenant_id=uuid4(),
            employee_id=uuid4(),
        )

        hooks = HookRegistry()
        recorder.register(hooks)

        goal_id = uuid4()
        await hooks.emit(
            HOOK_GOAL_ACHIEVED,
            employee_id=uuid4(),
            goal_id=goal_id,
            goal_description="Close 10 deals",
            metric="deals_closed",
            current_value=12,
            target_value=10,
            goal_type="achievement",
        )

        # Verify an activity was added to the session
        session.add.assert_called_once()
        activity = session.add.call_args[0][0]
        assert activity.event_type == "goal_achieved"
        assert "Close 10 deals" in activity.description
        assert activity.importance == 1.0
        assert activity.data["metric"] == "deals_closed"
        assert activity.data["current_value"] == 12
        assert activity.data["target_value"] == 10


# ============================================================================
# Tests: Retry logic and _completion_pending
# ============================================================================


class TestGoalCompletionRetry:
    """Test _complete_goal_with_retry retry logic."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self) -> None:
        """Goal completes when complete_goal fails once then succeeds."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals", "value": 5},
            description="Close 5 deals",
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock(side_effect=[RuntimeError("transient"), None])
        mock_goals.update_goal_progress = AsyncMock()
        mock_goals.get_active_goals = AsyncMock(return_value=[])
        mock_goals.get_pursuing_goals = AsyncMock(return_value=[])
        mock_goals.get_goal = AsyncMock(return_value=None)

        loop = _make_loop(mock_goals=mock_goals)

        hook_calls: list[dict] = []

        async def capture(**kwargs):
            hook_calls.append(kwargs)

        loop._hooks.register(HOOK_GOAL_ACHIEVED, capture)

        await loop._check_goal_achievement(goal, {"deals": 10})

        assert mock_goals.complete_goal.call_count == 2
        assert len(hook_calls) == 1

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_sets_completion_pending(self) -> None:
        """When all retries fail, _completion_pending is persisted."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals", "value": 5},
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock(side_effect=RuntimeError("always fails"))
        mock_goals.update_goal_progress = AsyncMock()
        mock_goals.get_active_goals = AsyncMock(return_value=[])
        mock_goals.get_pursuing_goals = AsyncMock(return_value=[])
        mock_goals.get_goal = AsyncMock(return_value=None)

        loop = _make_loop(mock_goals=mock_goals)

        await loop._check_goal_achievement(goal, {"deals": 10})

        assert mock_goals.complete_goal.call_count == 3
        mock_goals.update_goal_progress.assert_called_once()
        pending_arg = mock_goals.update_goal_progress.call_args[0][1]
        assert pending_arg["_completion_pending"] is True

    @pytest.mark.asyncio
    async def test_completion_pending_stripped_from_final_progress(self) -> None:
        """_completion_pending flag is not passed to complete_goal."""
        goal = MockGoal(
            goal_type="achievement",
            target={"metric": "deals", "value": 5},
        )

        mock_goals = Mock()
        mock_goals.complete_goal = AsyncMock()
        mock_goals.update_goal_progress = AsyncMock()
        mock_goals.get_active_goals = AsyncMock(return_value=[])
        mock_goals.get_pursuing_goals = AsyncMock(return_value=[])
        mock_goals.get_goal = AsyncMock(return_value=None)

        loop = _make_loop(mock_goals=mock_goals)

        progress = {"deals": 10, "_completion_pending": True}
        await loop._check_goal_achievement(goal, progress)

        call_args = mock_goals.complete_goal.call_args[0]
        assert "_completion_pending" not in call_args[1]

    @pytest.mark.asyncio
    async def test_llm_result_with_none_value_filtered_out(self) -> None:
        """GoalMetricResult with current_value=None is excluded from progress."""
        goal = MockGoal(target={"metric": "deals_closed", "value": 10})
        beliefs = [MockBeliefChange(subject="sales", predicate="update")]

        evaluation = GoalProgressEvaluation(
            results=[
                GoalMetricResult(
                    goal_id=str(goal.id),
                    metric="deals_closed",
                    current_value=None,
                    confidence=0.3,
                    reasoning="Insufficient data",
                )
            ]
        )

        llm = Mock()
        llm.generate_structured = AsyncMock(return_value=(_make_llm_response(), evaluation))

        loop = _make_loop(llm_service=llm)
        result = await loop._evaluate_goals_progress([goal], beliefs)

        assert result == {}
