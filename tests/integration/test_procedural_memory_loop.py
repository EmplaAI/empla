"""
Integration tests for procedural memory → execution loop.

Tests the path: intention execution → reflection → record_procedure →
find_procedures_for_situation → plan generation, and memory maintenance.
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.loop.models import IntentionResult, LoopConfig
from empla.models.employee import Employee

# ============================================================================
# Helpers
# ============================================================================


def _make_memory(
    procedural: Mock | None = None,
    episodic: Mock | None = None,
) -> Mock:
    """Create a mock memory system with procedural and episodic subsystems."""
    memory = Mock()

    if procedural is not None:
        memory.procedural = procedural
    else:
        proc = Mock()
        proc.record_procedure = AsyncMock()
        proc.find_procedures_for_situation = AsyncMock(return_value=[])
        proc.reinforce_successful_procedures = AsyncMock()
        proc.archive_poor_procedures = AsyncMock()
        memory.procedural = proc

    if episodic is not None:
        memory.episodic = episodic
    else:
        ep = Mock()
        ep.record_episode = AsyncMock()
        ep.reinforce_frequently_recalled = AsyncMock(return_value=0)
        ep.decay_rarely_recalled = AsyncMock(return_value=0)
        memory.episodic = ep

    return memory


def _make_loop(
    memory: Mock | None = None,
    mock_goals: Mock | None = None,
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
    beliefs.update_belief = AsyncMock()

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
        memory=memory or _make_memory(),
        config=LoopConfig(cycle_interval_seconds=1),
    )


# ============================================================================
# Tests: Procedure recorded after intention execution
# ============================================================================


class TestProcedureRecordedAfterIntention:
    """Test that reflection_cycle records procedures in procedural memory."""

    @pytest.mark.asyncio
    async def test_successful_intention_records_procedure(self) -> None:
        """Successful intention with tools records procedure with steps."""
        memory = _make_memory()
        loop = _make_loop(memory=memory)

        result = IntentionResult(
            intention_id=uuid4(),
            success=True,
            outcome={
                "tools_used": ["email.send_email", "crm.update_deal"],
                "tool_results": [
                    {"tool": "email.send_email", "success": True},
                    {"tool": "crm.update_deal", "success": True},
                ],
                "intention_description": "Send follow-up email and update CRM",
            },
            duration_ms=1500.0,
        )

        await loop.reflection_cycle(result)

        memory.procedural.record_procedure.assert_called_once()
        call_kwargs = memory.procedural.record_procedure.call_args[1]
        assert call_kwargs["procedure_type"] == "intention_execution"
        assert call_kwargs["success"] is True
        assert len(call_kwargs["steps"]) == 2
        assert call_kwargs["steps"][0]["action"] == "email.send_email"
        assert call_kwargs["steps"][1]["action"] == "crm.update_deal"

    @pytest.mark.asyncio
    async def test_failed_intention_records_failure_pattern(self) -> None:
        """Failed intention records failure pattern for avoidance."""
        memory = _make_memory()
        loop = _make_loop(memory=memory)

        result = IntentionResult(
            intention_id=uuid4(),
            success=False,
            outcome={
                "tools_used": [],
                "error": "API rate limit exceeded",
                "intention_description": "Send bulk emails",
            },
            duration_ms=500.0,
        )

        await loop.reflection_cycle(result)

        memory.procedural.record_procedure.assert_called_once()
        call_kwargs = memory.procedural.record_procedure.call_args[1]
        assert call_kwargs["procedure_type"] == "intention_failure"
        assert call_kwargs["success"] is False
        assert "failed" in call_kwargs["name"]

    @pytest.mark.asyncio
    async def test_trigger_conditions_include_goal_context(self) -> None:
        """Procedure trigger_conditions include goal_type and goal_description."""
        memory = _make_memory()

        mock_goal = Mock()
        mock_goal.goal_type = "maintenance"
        mock_goal.description = "Maintain 3x pipeline coverage"

        mock_goals = Mock()
        mock_goals.get_goal = AsyncMock(return_value=mock_goal)
        mock_goals.get_active_goals = AsyncMock(return_value=[])
        mock_goals.get_pursuing_goals = AsyncMock(return_value=[])
        mock_goals.update_goal_progress = AsyncMock()
        mock_goals.complete_goal = AsyncMock()

        loop = _make_loop(memory=memory, mock_goals=mock_goals)

        goal_id = uuid4()
        result = IntentionResult(
            intention_id=uuid4(),
            success=True,
            outcome={
                "tools_used": ["crm.get_pipeline_metrics"],
                "tool_results": [
                    {"tool": "crm.get_pipeline_metrics", "success": True},
                ],
                "goal_id": str(goal_id),
                "intention_description": "Check pipeline metrics",
            },
            duration_ms=800.0,
        )

        await loop.reflection_cycle(result)

        memory.procedural.record_procedure.assert_called_once()
        call_kwargs = memory.procedural.record_procedure.call_args[1]
        assert call_kwargs["trigger_conditions"]["goal_type"] == "maintenance"
        assert "pipeline" in call_kwargs["trigger_conditions"]["goal_description"].lower()

    @pytest.mark.asyncio
    async def test_per_tool_results_captured_in_steps(self) -> None:
        """Steps reflect per-tool success/failure from tool_results."""
        memory = _make_memory()
        loop = _make_loop(memory=memory)

        result = IntentionResult(
            intention_id=uuid4(),
            success=True,
            outcome={
                "tools_used": ["email.send_email", "crm.update_deal"],
                "tool_results": [
                    {"tool": "email.send_email", "success": True},
                    {"tool": "crm.update_deal", "success": False},
                ],
                "intention_description": "Update deal and notify",
            },
            duration_ms=1200.0,
        )

        await loop.reflection_cycle(result)

        call_kwargs = memory.procedural.record_procedure.call_args[1]
        steps = call_kwargs["steps"]
        assert steps[0]["success"] is True
        assert steps[1]["success"] is False


# ============================================================================
# Tests: Procedures influence plan generation
# ============================================================================


class TestProcedureInfluencesPlanning:
    """Test that recorded procedures are used during plan generation."""

    @pytest.mark.asyncio
    async def test_procedures_queried_for_matching_goal(self) -> None:
        """find_procedures_for_situation is called with goal context during planning."""
        memory = _make_memory()
        memory.procedural.find_procedures_for_situation = AsyncMock(return_value=[])

        mock_goal = Mock()
        mock_goal.id = uuid4()
        mock_goal.goal_type = "achievement"
        mock_goal.description = "Close 10 deals"
        mock_goal.priority = 8

        loop = _make_loop(memory=memory)

        # Call the relevant part — _generate_plans_for_goals
        # We need to set up the intentions mock to indicate no existing plans
        loop.intentions.get_intentions_for_goal = AsyncMock(return_value=[])
        loop._identity_prompt = "You are a sales employee."

        # Mock LLM to avoid actual call
        llm = Mock()
        llm.generate = AsyncMock(
            return_value=Mock(
                content='[{"description": "Reach out to leads", "priority": 7}]',
            )
        )
        loop.llm_service = llm

        await loop._generate_plans_for_unplanned_goals(
            goals=[mock_goal],
            beliefs=[],
            capabilities=["email", "crm"],
        )

        memory.procedural.find_procedures_for_situation.assert_called_once()
        call_kwargs = memory.procedural.find_procedures_for_situation.call_args[1]
        assert call_kwargs["situation"]["goal_type"] == "achievement"
        assert "Close 10 deals" in call_kwargs["situation"]["goal_description"]
        assert call_kwargs["procedure_type"] == "intention_execution"


# ============================================================================
# Tests: Memory maintenance (reinforcement & archival)
# ============================================================================


class TestProcedureMaintenanceHealth:
    """Test _maintain_memory_health for procedural memory."""

    @pytest.mark.asyncio
    async def test_reinforces_successful_procedures(self) -> None:
        """Memory maintenance calls reinforce_successful_procedures."""
        memory = _make_memory()
        loop = _make_loop(memory=memory)

        await loop._maintain_memory_health()

        memory.procedural.reinforce_successful_procedures.assert_called_once_with(
            min_success_rate=0.8,
            min_executions=3,
        )

    @pytest.mark.asyncio
    async def test_archives_poor_procedures(self) -> None:
        """Memory maintenance archives procedures with low success rate."""
        memory = _make_memory()
        loop = _make_loop(memory=memory)

        await loop._maintain_memory_health()

        memory.procedural.archive_poor_procedures.assert_called_once_with(
            max_success_rate=0.2,
            min_executions=3,
        )

    @pytest.mark.asyncio
    async def test_reinforcement_error_does_not_block_archival(self) -> None:
        """If reinforcement fails, archival still runs."""
        memory = _make_memory()
        memory.procedural.reinforce_successful_procedures = AsyncMock(
            side_effect=RuntimeError("DB error")
        )
        loop = _make_loop(memory=memory)

        await loop._maintain_memory_health()

        # Archival should still have been called
        memory.procedural.archive_poor_procedures.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_procedural_memory_is_noop(self) -> None:
        """No error when memory has no procedural subsystem."""
        memory = Mock(spec=[])  # No attributes at all
        # Add episodic for the first part of _maintain_memory_health
        memory.episodic = Mock()
        memory.episodic.reinforce_frequently_recalled = AsyncMock(return_value=0)
        memory.episodic.decay_rarely_recalled = AsyncMock(return_value=0)

        # Remove procedural — hasattr should return False
        del memory.episodic  # Actually remove it too so both skip
        loop = _make_loop(memory=memory)

        # Should not raise
        await loop._maintain_memory_health()
