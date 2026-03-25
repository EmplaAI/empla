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
    async def test_uses_playbook_when_available(self):
        """When a matching playbook exists, skip LLM and use playbook steps."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        playbook = MockProceduralMemory(
            name="prospecting_playbook",
            is_playbook=True,
            steps=[{"action": "search_leads"}, {"action": "send_email"}],
        )
        mixin.memory.procedural.find_playbooks = AsyncMock(return_value=[playbook])

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        # Should create intention from playbook, not call LLM
        mixin.intentions.add_intention.assert_called_once()
        call_kwargs = mixin.intentions.add_intention.call_args.kwargs
        assert "playbook" in call_kwargs["description"].lower()
        assert call_kwargs["plan"] == {"steps": playbook.steps}
        assert call_kwargs["context"]["playbook_name"] == "prospecting_playbook"

        # LLM should NOT be called
        mixin.intentions.generate_plan_for_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_llm_when_no_playbook(self):
        """When no playbook matches, fall back to LLM generation."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        mixin.memory.procedural.find_playbooks = AsyncMock(return_value=[])

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        # LLM should be called
        mixin.intentions.generate_plan_for_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_on_playbook_error(self):
        """Playbook lookup failure should fall back to LLM, not crash."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        mixin.memory.procedural.find_playbooks = AsyncMock(side_effect=Exception("DB error"))

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        # Should still try LLM
        mixin.intentions.generate_plan_for_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_increments_playbook_execution_count(self):
        """Using a playbook should increment its execution_count."""
        mixin = self._make_planning_mixin()
        goal = self._make_goal()

        playbook = MockProceduralMemory(name="test", is_playbook=True, execution_count=5)
        mixin.memory.procedural.find_playbooks = AsyncMock(return_value=[playbook])

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

        assert playbook.execution_count == 6


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
