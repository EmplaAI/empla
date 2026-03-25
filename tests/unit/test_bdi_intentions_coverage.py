"""
Unit tests for empla.bdi.intentions (IntentionStack + Pydantic models).

Covers all methods with mocked AsyncSession (no real DB).
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from empla.bdi.intentions import (
    GeneratedIntention,
    IntentionStack,
    PlanGenerationResult,
    PlanStep,
)
from empla.models.employee import EmployeeIntention

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intention(**overrides):
    """Create a minimal EmployeeIntention-like object."""
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "employee_id": uuid4(),
        "goal_id": uuid4(),
        "intention_type": "action",
        "description": "Send follow-up email",
        "plan": {"type": "send_email"},
        "status": "planned",
        "priority": 7,
        "context": {},
        "dependencies": [],
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _wire_execute_scalars(session, rows):
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)


def _wire_execute_scalar_one_or_none(session, value):
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = value
    session.execute = AsyncMock(return_value=result_mock)


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestPlanStep:
    def test_valid(self):
        step = PlanStep(
            action="search_web",
            description="Search for competitors",
            expected_outcome="List of competitors",
        )
        assert step.action == "search_web"
        assert step.parameters == {}
        assert step.required_capabilities == []

    def test_with_all_fields(self):
        step = PlanStep(
            action="search_web",
            description="Search for competitors",
            parameters={"query": "acme"},
            expected_outcome="Results",
            estimated_duration_minutes=15,
            required_capabilities=["research"],
        )
        assert step.estimated_duration_minutes == 15

    def test_action_min_length(self):
        with pytest.raises(ValidationError):
            PlanStep(action="", description="x", expected_outcome="y")


class TestGeneratedIntention:
    def test_valid_action(self):
        gi = GeneratedIntention(
            intention_type="action",
            description="Do something",
            priority=5,
            plan={"steps": []},
            reasoning="Because",
        )
        assert gi.intention_type == "action"

    def test_type_normalization_task(self):
        gi = GeneratedIntention(
            intention_type="task",
            description="Do something",
            priority=5,
            plan={},
            reasoning="Because",
        )
        assert gi.intention_type == "action"

    def test_type_normalization_step(self):
        gi = GeneratedIntention(
            intention_type="Step",
            description="Do something",
            priority=5,
            plan={},
            reasoning="Because",
        )
        assert gi.intention_type == "action"

    def test_type_normalization_approach(self):
        gi = GeneratedIntention(
            intention_type="approach",
            description="Do something",
            priority=5,
            plan={},
            reasoning="Because",
        )
        assert gi.intention_type == "tactic"

    def test_type_normalization_method(self):
        gi = GeneratedIntention(
            intention_type="Method",
            description="Do something",
            priority=5,
            plan={},
            reasoning="Because",
        )
        assert gi.intention_type == "tactic"

    def test_type_normalization_plan(self):
        gi = GeneratedIntention(
            intention_type="plan",
            description="Do something",
            priority=5,
            plan={},
            reasoning="Because",
        )
        assert gi.intention_type == "strategy"

    def test_type_normalization_campaign(self):
        gi = GeneratedIntention(
            intention_type="Campaign",
            description="Do something",
            priority=5,
            plan={},
            reasoning="Because",
        )
        assert gi.intention_type == "strategy"

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            GeneratedIntention(
                intention_type="invalid",
                description="Do something",
                priority=5,
                plan={},
                reasoning="Because",
            )

    def test_priority_bounds(self):
        with pytest.raises(ValidationError):
            GeneratedIntention(
                intention_type="action",
                description="Do something",
                priority=0,
                plan={},
                reasoning="Because",
            )
        with pytest.raises(ValidationError):
            GeneratedIntention(
                intention_type="action",
                description="Do something",
                priority=11,
                plan={},
                reasoning="Because",
            )

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            GeneratedIntention(
                intention_type="action",
                description="",
                priority=5,
                plan={},
                reasoning="Because",
            )


class TestPlanGenerationResult:
    def test_valid(self):
        result = PlanGenerationResult(
            strategy_summary="Multi-touch campaign",
            intentions=[],
            assumptions=["Has budget"],
            risks=["Competitor timing"],
            success_criteria=["Meeting booked"],
        )
        assert result.strategy_summary == "Multi-touch campaign"

    def test_defaults(self):
        result = PlanGenerationResult(strategy_summary="Summary")
        assert result.intentions == []
        assert result.assumptions == []
        assert result.risks == []
        assert result.success_criteria == []


# ---------------------------------------------------------------------------
# Tests: IntentionStack.__init__
# ---------------------------------------------------------------------------


class TestIntentionStackInit:
    def test_stores_ids(self):
        session = _mock_session()
        eid, tid = uuid4(), uuid4()
        stack = IntentionStack(session, eid, tid)
        assert stack.employee_id == eid
        assert stack.tenant_id == tid


# ---------------------------------------------------------------------------
# Tests: add_intention
# ---------------------------------------------------------------------------


class TestAddIntention:
    @pytest.mark.asyncio
    async def test_creates_and_flushes(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        intention = await stack.add_intention(
            intention_type="action",
            description="Send email",
            plan={"type": "send_email"},
            priority=7,
        )

        assert isinstance(intention, EmployeeIntention)
        assert intention.status == "planned"
        assert intention.priority == 7
        assert intention.dependencies == []
        assert intention.context == {}
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_goal_and_dependencies(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())
        goal_id = uuid4()
        dep_ids = [uuid4(), uuid4()]

        intention = await stack.add_intention(
            intention_type="tactic",
            description="Research",
            plan={"steps": []},
            priority=5,
            goal_id=goal_id,
            context={"reason": "strategic"},
            dependencies=dep_ids,
        )

        assert intention.goal_id == goal_id
        assert intention.dependencies == dep_ids
        assert intention.context == {"reason": "strategic"}

    @pytest.mark.asyncio
    async def test_default_priority(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())
        intention = await stack.add_intention(
            intention_type="action",
            description="desc",
            plan={},
        )
        assert intention.priority == 5


# ---------------------------------------------------------------------------
# Tests: get_intention
# ---------------------------------------------------------------------------


class TestGetIntention:
    @pytest.mark.asyncio
    async def test_found(self):
        session = _mock_session()
        expected = _make_intention()
        _wire_execute_scalar_one_or_none(session, expected)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_intention(expected.id)
        assert result is expected

    @pytest.mark.asyncio
    async def test_not_found(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.get_intention(uuid4()) is None


# ---------------------------------------------------------------------------
# Tests: get_planned_intentions
# ---------------------------------------------------------------------------


class TestGetPlannedIntentions:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        session = _mock_session()
        items = [_make_intention(priority=9), _make_intention(priority=5)]
        _wire_execute_scalars(session, items)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_planned_intentions()
        assert result == items

    @pytest.mark.asyncio
    async def test_empty(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.get_planned_intentions() == []

    @pytest.mark.asyncio
    async def test_with_min_priority(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_planned_intentions(min_priority=8)
        assert result == []
        session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: get_intentions_for_goal
# ---------------------------------------------------------------------------


class TestGetIntentionsForGoal:
    @pytest.mark.asyncio
    async def test_returns_for_goal(self):
        session = _mock_session()
        goal_id = uuid4()
        items = [_make_intention(goal_id=goal_id)]
        _wire_execute_scalars(session, items)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_intentions_for_goal(goal_id)
        assert result == items

    @pytest.mark.asyncio
    async def test_empty(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.get_intentions_for_goal(uuid4()) == []


# ---------------------------------------------------------------------------
# Tests: _are_dependencies_satisfied / dependencies_satisfied
# ---------------------------------------------------------------------------


class TestDependenciesSatisfied:
    @pytest.mark.asyncio
    async def test_no_dependencies_satisfied(self):
        session = _mock_session()
        intention = _make_intention(dependencies=[])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack._are_dependencies_satisfied(intention) is True

    @pytest.mark.asyncio
    async def test_all_completed(self):
        session = _mock_session()
        dep1_id, dep2_id = uuid4(), uuid4()
        intention = _make_intention(dependencies=[dep1_id, dep2_id])

        dep1 = _make_intention(id=dep1_id, status="completed")
        dep2 = _make_intention(id=dep2_id, status="completed")
        _wire_execute_scalars(session, [dep1, dep2])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack._are_dependencies_satisfied(intention) is True

    @pytest.mark.asyncio
    async def test_one_not_completed(self):
        session = _mock_session()
        dep1_id, dep2_id = uuid4(), uuid4()
        intention = _make_intention(dependencies=[dep1_id, dep2_id])

        dep1 = _make_intention(id=dep1_id, status="completed")
        dep2 = _make_intention(id=dep2_id, status="in_progress")
        _wire_execute_scalars(session, [dep1, dep2])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack._are_dependencies_satisfied(intention) is False

    @pytest.mark.asyncio
    async def test_missing_dependency(self):
        """If a dependency was deleted, returns False."""
        session = _mock_session()
        dep1_id, dep2_id = uuid4(), uuid4()
        intention = _make_intention(dependencies=[dep1_id, dep2_id])

        # Only one found (one was deleted)
        dep1 = _make_intention(id=dep1_id, status="completed")
        _wire_execute_scalars(session, [dep1])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack._are_dependencies_satisfied(intention) is False

    @pytest.mark.asyncio
    async def test_public_interface(self):
        session = _mock_session()
        intention = _make_intention(dependencies=[])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.dependencies_satisfied(intention) is True


# ---------------------------------------------------------------------------
# Tests: get_next_intention
# ---------------------------------------------------------------------------


class TestGetNextIntention:
    @pytest.mark.asyncio
    async def test_returns_first_with_satisfied_deps(self):
        session = _mock_session()
        i1 = _make_intention(priority=9, dependencies=[])
        i2 = _make_intention(priority=5, dependencies=[])
        _wire_execute_scalars(session, [i1, i2])

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_next_intention()
        assert result is i1

    @pytest.mark.asyncio
    async def test_skips_unsatisfied_deps(self):
        session = _mock_session()
        dep_id = uuid4()
        i1 = _make_intention(priority=9, dependencies=[dep_id])
        i2 = _make_intention(priority=5, dependencies=[])

        # get_planned_intentions returns [i1, i2]
        _wire_execute_scalars(session, [i1, i2])

        stack = IntentionStack(session, uuid4(), uuid4())

        # Mock _are_dependencies_satisfied to control behavior
        call_count = 0

        async def mock_deps(intention):
            nonlocal call_count
            call_count += 1
            return intention is not i1  # i1 unsatisfied, i2 satisfied

        stack._are_dependencies_satisfied = mock_deps
        result = await stack.get_next_intention()
        assert result is i2

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.get_next_intention() is None

    @pytest.mark.asyncio
    async def test_returns_none_when_all_blocked(self):
        session = _mock_session()
        i1 = _make_intention(dependencies=[uuid4()])
        _wire_execute_scalars(session, [i1])

        stack = IntentionStack(session, uuid4(), uuid4())

        async def mock_deps(intention):
            return False

        stack._are_dependencies_satisfied = mock_deps
        assert await stack.get_next_intention() is None


# ---------------------------------------------------------------------------
# Tests: start_intention
# ---------------------------------------------------------------------------


class TestStartIntention:
    @pytest.mark.asyncio
    async def test_starts_planned_with_satisfied_deps(self):
        session = _mock_session()
        intention = _make_intention(status="planned", dependencies=[])
        _wire_execute_scalar_one_or_none(session, intention)

        # Need to also mock deps check (calls session.execute)
        stack = IntentionStack(session, uuid4(), uuid4())
        stack._are_dependencies_satisfied = AsyncMock(return_value=True)

        result = await stack.start_intention(intention.id)
        assert result.status == "in_progress"
        assert result.started_at is not None
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_unchanged_if_already_started(self):
        session = _mock_session()
        intention = _make_intention(status="in_progress")
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.start_intention(intention.id)
        assert result.status == "in_progress"

    @pytest.mark.asyncio
    async def test_returns_unchanged_if_deps_not_satisfied(self):
        session = _mock_session()
        intention = _make_intention(status="planned", dependencies=[uuid4()])
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        stack._are_dependencies_satisfied = AsyncMock(return_value=False)

        result = await stack.start_intention(intention.id)
        assert result.status == "planned"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.start_intention(uuid4()) is None


# ---------------------------------------------------------------------------
# Tests: complete_intention
# ---------------------------------------------------------------------------


class TestCompleteIntention:
    @pytest.mark.asyncio
    async def test_completes(self):
        session = _mock_session()
        intention = _make_intention(status="in_progress")
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.complete_intention(intention.id)
        assert result.status == "completed"
        assert result.completed_at is not None
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_with_outcome(self):
        session = _mock_session()
        intention = _make_intention(status="in_progress", context={"original": True})
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.complete_intention(intention.id, outcome={"success": True})
        assert result.context["outcome"] == {"success": True}
        assert result.context["original"] is True

    @pytest.mark.asyncio
    async def test_without_outcome(self):
        session = _mock_session()
        intention = _make_intention(status="in_progress", context={"x": 1})
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.complete_intention(intention.id)
        assert "outcome" not in result.context

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.complete_intention(uuid4()) is None


# ---------------------------------------------------------------------------
# Tests: fail_intention
# ---------------------------------------------------------------------------


class TestFailIntention:
    @pytest.mark.asyncio
    async def test_fails(self):
        session = _mock_session()
        intention = _make_intention(status="in_progress")
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.fail_intention(intention.id, "Timeout")
        assert result.status == "failed"
        assert result.failed_at is not None
        assert result.context["error"] == "Timeout"
        assert result.context["retry"] is True
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_retry(self):
        session = _mock_session()
        intention = _make_intention(status="in_progress")
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.fail_intention(intention.id, "Fatal", retry=False)
        assert result.context["retry"] is False

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.fail_intention(uuid4(), "err") is None


# ---------------------------------------------------------------------------
# Tests: abandon_intention
# ---------------------------------------------------------------------------


class TestAbandonIntention:
    @pytest.mark.asyncio
    async def test_abandons(self):
        session = _mock_session()
        intention = _make_intention(status="planned")
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.abandon_intention(intention.id, "No longer relevant")
        assert result.status == "abandoned"
        assert result.context["abandonment_reason"] == "No longer relevant"
        assert "abandoned_at" in result.context
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.abandon_intention(uuid4(), "reason") is None


# ---------------------------------------------------------------------------
# Tests: update_intention_priority
# ---------------------------------------------------------------------------


class TestUpdateIntentionPriority:
    @pytest.mark.asyncio
    async def test_updates(self):
        session = _mock_session()
        intention = _make_intention(priority=5)
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.update_intention_priority(intention.id, 10)
        assert result.priority == 10
        assert result.updated_at is not None
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.update_intention_priority(uuid4(), 5) is None


# ---------------------------------------------------------------------------
# Tests: get_in_progress_intentions
# ---------------------------------------------------------------------------


class TestGetInProgressIntentions:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        session = _mock_session()
        items = [_make_intention(status="in_progress")]
        _wire_execute_scalars(session, items)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_in_progress_intentions()
        assert result == items

    @pytest.mark.asyncio
    async def test_empty(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.get_in_progress_intentions() == []


# ---------------------------------------------------------------------------
# Tests: get_failed_intentions
# ---------------------------------------------------------------------------


class TestGetFailedIntentions:
    @pytest.mark.asyncio
    async def test_retryable_only(self):
        session = _mock_session()
        i1 = _make_intention(status="failed", context={"retry": True})
        i2 = _make_intention(status="failed", context={"retry": False})
        _wire_execute_scalars(session, [i1, i2])

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_failed_intentions(retryable_only=True)
        assert result == [i1]

    @pytest.mark.asyncio
    async def test_all_failed(self):
        session = _mock_session()
        i1 = _make_intention(status="failed", context={"retry": True})
        i2 = _make_intention(status="failed", context={"retry": False})
        _wire_execute_scalars(session, [i1, i2])

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.get_failed_intentions(retryable_only=False)
        assert result == [i1, i2]

    @pytest.mark.asyncio
    async def test_empty(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.get_failed_intentions() == []


# ---------------------------------------------------------------------------
# Tests: retry_intention
# ---------------------------------------------------------------------------


class TestRetryIntention:
    @pytest.mark.asyncio
    async def test_resets_to_planned(self):
        session = _mock_session()
        intention = _make_intention(
            status="failed",
            failed_at=datetime.now(UTC),
            context={"error": "Timeout", "retry": True},
        )
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.retry_intention(intention.id)
        assert result.status == "planned"
        assert result.failed_at is None
        assert result.context["retry_count"] == 1
        assert "last_retry_at" in result.context
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_increments_retry_count(self):
        session = _mock_session()
        intention = _make_intention(
            status="failed",
            context={"retry_count": 2},
        )
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.retry_intention(intention.id)
        assert result.context["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_returns_unchanged_if_not_failed(self):
        session = _mock_session()
        intention = _make_intention(status="planned")
        _wire_execute_scalar_one_or_none(session, intention)

        stack = IntentionStack(session, uuid4(), uuid4())
        result = await stack.retry_intention(intention.id)
        assert result.status == "planned"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        session = _mock_session()
        _wire_execute_scalar_one_or_none(session, None)

        stack = IntentionStack(session, uuid4(), uuid4())
        assert await stack.retry_intention(uuid4()) is None


# ---------------------------------------------------------------------------
# Tests: clear_completed_intentions
# ---------------------------------------------------------------------------


class TestClearCompletedIntentions:
    @pytest.mark.asyncio
    async def test_soft_deletes_old(self):
        session = _mock_session()
        old = _make_intention(
            status="completed",
            completed_at=datetime.now(UTC) - timedelta(days=10),
        )
        _wire_execute_scalars(session, [old])

        stack = IntentionStack(session, uuid4(), uuid4())
        count = await stack.clear_completed_intentions(older_than_days=7)
        assert count == 1
        assert old.deleted_at is not None
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        count = await stack.clear_completed_intentions()
        assert count == 0

    @pytest.mark.asyncio
    async def test_custom_days(self):
        session = _mock_session()
        _wire_execute_scalars(session, [])

        stack = IntentionStack(session, uuid4(), uuid4())
        count = await stack.clear_completed_intentions(older_than_days=1)
        assert count == 0
        session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: generate_plan_for_goal
# ---------------------------------------------------------------------------


class TestGeneratePlanForGoal:
    @pytest.mark.asyncio
    async def test_generates_intentions_from_llm(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        goal = _make_intention(
            goal_type="achievement",
            description="Close deal",
            priority=9,
            target={"metric": "deal_value", "value": 50000},
            current_progress={"stage": "proposal"},
        )

        plan_result = PlanGenerationResult(
            strategy_summary="Research then propose",
            intentions=[
                GeneratedIntention(
                    intention_type="action",
                    description="Research account",
                    priority=8,
                    plan={"steps": [{"action": "research"}]},
                    reasoning="Need context",
                    dependencies=[],
                ),
                GeneratedIntention(
                    intention_type="action",
                    description="Send proposal",
                    priority=7,
                    plan={"steps": [{"action": "send_email"}]},
                    reasoning="Follow up",
                    dependencies=[0],
                ),
            ],
            assumptions=["Has budget"],
            risks=["Competitor"],
            success_criteria=["Deal closed"],
        )

        llm_service = AsyncMock()
        llm_service.generate_structured = AsyncMock(return_value=("raw", plan_result))

        result = await stack.generate_plan_for_goal(
            goal=goal,
            beliefs=[],
            llm_service=llm_service,
            capabilities=["email", "research"],
        )

        assert len(result) == 2
        assert all(isinstance(i, EmployeeIntention) for i in result)
        # Second intention should have dependency on first
        assert result[1].dependencies == [result[0].id]
        llm_service.generate_structured.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        goal = _make_intention(
            goal_type="achievement",
            description="Goal",
            priority=5,
            target={},
            current_progress={},
        )

        llm_service = AsyncMock()
        llm_service.generate_structured = AsyncMock(side_effect=RuntimeError("LLM down"))

        result = await stack.generate_plan_for_goal(
            goal=goal,
            beliefs=[],
            llm_service=llm_service,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_with_identity_context(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        goal = _make_intention(
            goal_type="achievement",
            description="Goal",
            priority=5,
            target={},
            current_progress={},
        )

        plan_result = PlanGenerationResult(
            strategy_summary="Simple plan",
            intentions=[],
        )

        llm_service = AsyncMock()
        llm_service.generate_structured = AsyncMock(return_value=("raw", plan_result))

        await stack.generate_plan_for_goal(
            goal=goal,
            beliefs=[],
            llm_service=llm_service,
            identity_context="You are Jordan, a sales AE.",
        )

        call_kwargs = llm_service.generate_structured.call_args
        assert "Jordan" in call_kwargs.kwargs.get("system", "") or "Jordan" in call_kwargs[1].get(
            "system", ""
        )

    @pytest.mark.asyncio
    async def test_without_identity_context(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        goal = _make_intention(
            goal_type="achievement",
            description="Goal",
            priority=5,
            target={},
            current_progress={},
        )

        plan_result = PlanGenerationResult(
            strategy_summary="Plan",
            intentions=[],
        )

        llm_service = AsyncMock()
        llm_service.generate_structured = AsyncMock(return_value=("raw", plan_result))

        await stack.generate_plan_for_goal(
            goal=goal,
            beliefs=[],
            llm_service=llm_service,
        )

        call_kwargs = llm_service.generate_structured.call_args
        system = call_kwargs.kwargs.get("system", "") or call_kwargs[1].get("system", "")
        assert "digital employee" in system

    @pytest.mark.asyncio
    async def test_invalid_dependency_index_skipped(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        goal = _make_intention(
            goal_type="achievement",
            description="Goal",
            priority=5,
            target={},
            current_progress={},
        )

        plan_result = PlanGenerationResult(
            strategy_summary="Plan",
            intentions=[
                GeneratedIntention(
                    intention_type="action",
                    description="Step 1",
                    priority=5,
                    plan={},
                    reasoning="First",
                    dependencies=[99],  # Invalid index
                ),
            ],
        )

        llm_service = AsyncMock()
        llm_service.generate_structured = AsyncMock(return_value=("raw", plan_result))

        result = await stack.generate_plan_for_goal(
            goal=goal,
            beliefs=[],
            llm_service=llm_service,
        )
        assert len(result) == 1
        assert result[0].dependencies == []

    @pytest.mark.asyncio
    async def test_no_capabilities_provided(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        goal = _make_intention(
            goal_type="achievement",
            description="Goal",
            priority=5,
            target={},
            current_progress={},
        )

        plan_result = PlanGenerationResult(strategy_summary="Plan")

        llm_service = AsyncMock()
        llm_service.generate_structured = AsyncMock(return_value=("raw", plan_result))

        result = await stack.generate_plan_for_goal(
            goal=goal,
            beliefs=[],
            llm_service=llm_service,
            capabilities=None,
        )
        assert result == []


# ---------------------------------------------------------------------------
# Tests: _format_beliefs_for_prompt
# ---------------------------------------------------------------------------


class TestFormatBeliefsForPrompt:
    def test_empty_beliefs(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())
        assert stack._format_beliefs_for_prompt([]) == "No current beliefs"

    def test_formats_beliefs(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        belief = SimpleNamespace(
            subject="pipeline",
            predicate="coverage",
            object={"value": 2.1},
            confidence=0.9,
        )
        result = stack._format_beliefs_for_prompt([belief])
        assert "pipeline" in result
        assert "coverage" in result
        assert "0.90" in result

    def test_truncates_long_objects(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        belief = SimpleNamespace(
            subject="data",
            predicate="content",
            object="x" * 200,
            confidence=0.5,
        )
        result = stack._format_beliefs_for_prompt([belief])
        assert "..." in result

    def test_limits_to_20_beliefs(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        beliefs = [
            SimpleNamespace(
                subject=f"s{i}",
                predicate=f"p{i}",
                object=f"o{i}",
                confidence=0.5,
            )
            for i in range(25)
        ]
        result = stack._format_beliefs_for_prompt(beliefs)
        assert "5 more beliefs" in result

    def test_exactly_20_no_overflow_message(self):
        session = _mock_session()
        stack = IntentionStack(session, uuid4(), uuid4())

        beliefs = [
            SimpleNamespace(
                subject=f"s{i}",
                predicate=f"p{i}",
                object=f"o{i}",
                confidence=0.5,
            )
            for i in range(20)
        ]
        result = stack._format_beliefs_for_prompt(beliefs)
        assert "more beliefs" not in result
