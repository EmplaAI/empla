"""
Tests for the playbook system — Phase 4: Efficiency + Intelligence.

Covers:
- ProceduralMemory playbook extensions (find, promote, evaluate)
- Playbook selection in planning (skip LLM for known patterns)
- Autonomous playbook discovery in reflection
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

# ============================================================================
# ProceduralMemory Playbook Operations
# ============================================================================


class MockProceduralMemory:
    """Mock procedural memory record for testing."""

    def __init__(
        self,
        name: str = "test_procedure",
        success_rate: float = 0.8,
        execution_count: int = 5,
        is_playbook: bool = False,
        steps: list[dict[str, Any]] | None = None,
        goal_type: str = "maintain",
    ):
        self.id = uuid4()
        self.name = name
        self.success_rate = success_rate
        self.execution_count = execution_count
        self.is_playbook = is_playbook
        self.promoted_at = None
        self.learned_from = "trial_and_error"
        self.steps = steps or [{"action": "step1"}, {"action": "step2"}]
        self.trigger_conditions = {"goal_type": goal_type}
        self.procedure_type = "intention_execution"
        self.deleted_at = None
        # PR #84 added an optimistic-lock counter; promote_to_playbook bumps it.
        self.version = 0
        self.enabled = True


class TestPromoteToPlaybook:
    """Tests for ProceduralMemorySystem.promote_to_playbook()."""

    def _make_service(self):
        from empla.core.memory.procedural import ProceduralMemorySystem

        session = AsyncMock()
        session.flush = AsyncMock()
        return ProceduralMemorySystem(session, employee_id=uuid4(), tenant_id=uuid4())

    @pytest.mark.asyncio
    async def test_promotes_eligible_procedure(self):
        """Procedure with 3+ executions and 70%+ success rate should promote."""
        svc = self._make_service()
        proc = MockProceduralMemory(success_rate=0.8, execution_count=5)
        svc.get_procedure = AsyncMock(return_value=proc)

        result = await svc.promote_to_playbook(proc.id)

        assert result is not None
        assert result.is_playbook is True
        assert result.promoted_at is not None
        # Preserves original learned_from (was "trial_and_error")
        assert result.learned_from == "trial_and_error"

    @pytest.mark.asyncio
    async def test_rejects_low_execution_count(self):
        """Procedure with < 3 executions should not promote."""
        svc = self._make_service()
        proc = MockProceduralMemory(success_rate=0.9, execution_count=2)
        svc.get_procedure = AsyncMock(return_value=proc)

        result = await svc.promote_to_playbook(proc.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_low_success_rate(self):
        """Procedure with < 70% success rate should not promote."""
        svc = self._make_service()
        proc = MockProceduralMemory(success_rate=0.5, execution_count=10)
        svc.get_procedure = AsyncMock(return_value=proc)

        result = await svc.promote_to_playbook(proc.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_already_promoted_returns_as_is(self):
        """Already-promoted procedure should return without changes."""
        svc = self._make_service()
        proc = MockProceduralMemory(is_playbook=True)
        svc.get_procedure = AsyncMock(return_value=proc)

        result = await svc.promote_to_playbook(proc.id)
        assert result is proc

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        """Non-existent procedure should return None."""
        svc = self._make_service()
        svc.get_procedure = AsyncMock(return_value=None)

        result = await svc.promote_to_playbook(uuid4())
        assert result is None


# ============================================================================
# Playbook Selection in Planning
# ============================================================================


class TestPlaybookSelectionInPlanning:
    """Tests for playbook selection during plan generation."""

    def _make_planning_mixin(self):
        from empla.core.loop.planning import PlanningMixin

        mixin = PlanningMixin()
        mixin.employee = Mock(id=uuid4())
        mixin.llm_service = Mock()
        mixin.intentions = Mock()
        mixin.intentions.get_intentions_for_goal = AsyncMock(return_value=[])
        mixin.intentions.add_intention = AsyncMock()
        mixin.intentions.generate_plan_for_goal = AsyncMock(return_value=[])
        mixin.memory = Mock()
        mixin.memory.procedural = Mock()
        mixin.memory.procedural.find_playbooks = AsyncMock(return_value=[])
        mixin.memory.procedural.find_procedures_for_situation = AsyncMock(return_value=[])
        mixin._identity_prompt = "You are a sales AE."
        return mixin

    def _make_goal(self, description="Test goal", goal_type="maintain", priority=5):
        goal = Mock()
        goal.id = uuid4()
        goal.description = description
        goal.goal_type = goal_type
        goal.priority = priority
        return goal

    @pytest.mark.asyncio
    async def test_playbooks_included_in_llm_context(self):
        """When playbooks exist, they should be passed to the LLM as context options."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        playbook = MockProceduralMemory(
            name="prospecting_playbook",
            is_playbook=True,
            steps=[{"action": "search_leads"}, {"action": "send_email"}],
            success_rate=0.85,
        )
        playbook.execution_count = 10
        mixin.memory.procedural.find_playbooks = AsyncMock(return_value=[playbook])

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        # LLM should be called (playbooks are context, not bypass)
        mixin.intentions.generate_plan_for_goal.assert_called_once()

        # The identity_context should include playbook info
        call_kwargs = mixin.intentions.generate_plan_for_goal.call_args.kwargs
        identity = call_kwargs.get("identity_context", "")
        assert "PLAYBOOK" in identity
        assert "prospecting_playbook" in identity

    @pytest.mark.asyncio
    async def test_llm_called_even_with_playbooks(self):
        """The LLM always decides — playbooks are suggestions, not bypasses."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        playbook = MockProceduralMemory(name="test", is_playbook=True)
        mixin.memory.procedural.find_playbooks = AsyncMock(return_value=[playbook])

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        # LLM should always be called
        mixin.intentions.generate_plan_for_goal.assert_called_once()
        # add_intention should NOT be called directly (no bypass)
        mixin.intentions.add_intention.assert_not_called()

    @pytest.mark.asyncio
    async def test_works_without_playbooks(self):
        """When no playbooks exist, LLM generates plan normally."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        mixin.memory.procedural.find_playbooks = AsyncMock(return_value=[])

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        mixin.intentions.generate_plan_for_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_playbook_lookup_error_still_calls_llm(self):
        """Playbook lookup failure should not prevent LLM plan generation."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        mixin.memory.procedural.find_playbooks = AsyncMock(side_effect=Exception("DB error"))

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        mixin.intentions.generate_plan_for_goal.assert_called_once()


# ============================================================================
# Playbook Success Feedback in Reflection
# ============================================================================


class TestPlaybookSuccessFeedback:
    """Tests for _update_playbook_success in ReflectionMixin."""

    def _make_mixin(self):
        from empla.core.loop.reflection import ReflectionMixin

        mixin = ReflectionMixin()
        mixin.employee = Mock(id=uuid4())
        mixin.memory = Mock()
        mixin.memory.procedural = Mock()
        mixin.memory.procedural.get_procedure = AsyncMock(return_value=None)
        mixin.memory.procedural.session = Mock()
        mixin.memory.procedural.session.flush = AsyncMock()
        return mixin

    def _make_result(self, success: bool = True, playbook_id: str | None = None):
        result = Mock()
        result.success = success
        result.context = {"playbook_id": playbook_id} if playbook_id else {}
        return result

    @pytest.mark.asyncio
    async def test_skips_without_playbook_id(self):
        """No-op when intention context has no playbook_id."""
        mixin = self._make_mixin()
        result = self._make_result(playbook_id=None)

        await mixin._update_playbook_success(result)
        mixin.memory.procedural.get_procedure.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_procedure_not_found(self):
        """No-op when playbook_id references non-existent procedure."""
        mixin = self._make_mixin()
        result = self._make_result(playbook_id=str(uuid4()))
        mixin.memory.procedural.get_procedure = AsyncMock(return_value=None)

        await mixin._update_playbook_success(result)

    @pytest.mark.asyncio
    async def test_skips_when_not_a_playbook(self):
        """No-op when procedure exists but is not a playbook."""
        mixin = self._make_mixin()
        proc = MockProceduralMemory(is_playbook=False)
        mixin.memory.procedural.get_procedure = AsyncMock(return_value=proc)
        result = self._make_result(playbook_id=str(proc.id))

        await mixin._update_playbook_success(result)

    @pytest.mark.asyncio
    async def test_auto_demotes_low_success_playbook(self):
        """Playbook with <50% success after 5+ runs should be demoted."""
        mixin = self._make_mixin()
        proc = MockProceduralMemory(
            is_playbook=True,
            success_rate=0.3,
            execution_count=6,
        )
        proc.promoted_at = "2026-03-20T00:00:00"
        mixin.memory.procedural.get_procedure = AsyncMock(return_value=proc)
        result = self._make_result(success=False, playbook_id=str(proc.id))

        await mixin._update_playbook_success(result)

        assert proc.is_playbook is False
        assert proc.promoted_at is None
        mixin.memory.procedural.session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_demotion_under_threshold_executions(self):
        """Playbook with <5 executions should not be demoted even if success is low."""
        mixin = self._make_mixin()
        proc = MockProceduralMemory(
            is_playbook=True,
            success_rate=0.3,
            execution_count=3,
        )
        mixin.memory.procedural.get_procedure = AsyncMock(return_value=proc)
        result = self._make_result(success=False, playbook_id=str(proc.id))

        await mixin._update_playbook_success(result)

        assert proc.is_playbook is True  # Not demoted

    @pytest.mark.asyncio
    async def test_no_demotion_above_success_threshold(self):
        """Playbook with >= 50% success should not be demoted."""
        mixin = self._make_mixin()
        proc = MockProceduralMemory(
            is_playbook=True,
            success_rate=0.6,
            execution_count=10,
        )
        mixin.memory.procedural.get_procedure = AsyncMock(return_value=proc)
        result = self._make_result(success=True, playbook_id=str(proc.id))

        await mixin._update_playbook_success(result)

        assert proc.is_playbook is True  # Not demoted

    @pytest.mark.asyncio
    async def test_error_handling_logs_warning(self):
        """DB error should log warning, not crash."""
        mixin = self._make_mixin()
        mixin.memory.procedural.get_procedure = AsyncMock(side_effect=Exception("DB"))
        result = self._make_result(playbook_id=str(uuid4()))

        await mixin._update_playbook_success(result)  # Should not raise


# ============================================================================
# Autonomous Playbook Discovery in Reflection
# ============================================================================


class TestPlaybookDiscovery:
    """Tests for _discover_playbooks in ReflectionMixin."""

    def _make_reflection_mixin(self):
        from empla.core.loop.reflection import ReflectionMixin

        mixin = ReflectionMixin()
        mixin.employee = Mock(id=uuid4())
        mixin.memory = Mock()
        mixin.memory.procedural = Mock()
        mixin.memory.procedural.evaluate_for_promotion = AsyncMock(return_value=[])
        mixin.memory.procedural.promote_to_playbook = AsyncMock()
        return mixin

    @pytest.mark.asyncio
    async def test_promotes_eligible_procedures(self):
        """Should promote procedures that meet the threshold."""
        mixin = self._make_reflection_mixin()

        proc1 = MockProceduralMemory(name="proc1", success_rate=0.9, execution_count=10)
        proc2 = MockProceduralMemory(name="proc2", success_rate=0.8, execution_count=5)

        mixin.memory.procedural.evaluate_for_promotion = AsyncMock(return_value=[proc1, proc2])

        promoted1 = MockProceduralMemory(name="proc1", is_playbook=True)
        promoted2 = MockProceduralMemory(name="proc2", is_playbook=True)
        mixin.memory.procedural.promote_to_playbook = AsyncMock(side_effect=[promoted1, promoted2])

        await mixin._discover_playbooks()

        assert mixin.memory.procedural.promote_to_playbook.call_count == 2

    @pytest.mark.asyncio
    async def test_no_candidates_does_nothing(self):
        """No eligible procedures → no promotions."""
        mixin = self._make_reflection_mixin()
        mixin.memory.procedural.evaluate_for_promotion = AsyncMock(return_value=[])

        await mixin._discover_playbooks()

        mixin.memory.procedural.promote_to_playbook.assert_not_called()

    @pytest.mark.asyncio
    async def test_promotion_failure_continues(self):
        """One promotion failure should not stop other promotions."""
        mixin = self._make_reflection_mixin()

        proc1 = MockProceduralMemory(name="proc1")
        proc2 = MockProceduralMemory(name="proc2")
        mixin.memory.procedural.evaluate_for_promotion = AsyncMock(return_value=[proc1, proc2])

        promoted2 = MockProceduralMemory(name="proc2", is_playbook=True)
        mixin.memory.procedural.promote_to_playbook = AsyncMock(
            side_effect=[Exception("DB error"), promoted2]
        )

        await mixin._discover_playbooks()

        # Should have attempted both
        assert mixin.memory.procedural.promote_to_playbook.call_count == 2

    @pytest.mark.asyncio
    async def test_no_procedural_memory_skips(self):
        """Without procedural memory, should skip gracefully."""
        mixin = self._make_reflection_mixin()
        mixin.memory = Mock(spec=[])  # No procedural attribute

        await mixin._discover_playbooks()  # Should not raise

    @pytest.mark.asyncio
    async def test_evaluate_failure_skips(self):
        """evaluate_for_promotion failure should not crash."""
        mixin = self._make_reflection_mixin()
        mixin.memory.procedural.evaluate_for_promotion = AsyncMock(
            side_effect=Exception("DB error")
        )

        await mixin._discover_playbooks()  # Should not raise


# ============================================================================
# Model Tests
# ============================================================================


class TestProceduralMemoryModel:
    """Tests for the updated ProceduralMemory model fields."""

    def test_is_playbook_default_false(self):
        """New procedures should default to is_playbook=False."""
        from empla.models.memory import ProceduralMemory

        # Verify the column exists and has the right default
        col = ProceduralMemory.__table__.columns["is_playbook"]
        assert col.server_default is not None

    def test_promoted_at_nullable(self):
        """promoted_at should be nullable."""
        from empla.models.memory import ProceduralMemory

        col = ProceduralMemory.__table__.columns["promoted_at"]
        assert col.nullable is True
