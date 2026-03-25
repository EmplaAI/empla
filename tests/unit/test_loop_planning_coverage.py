"""
Coverage tests for empla.core.loop.planning — uncovered lines.

Focuses on:
- _analyze_situation_with_llm (LLM call, semantic memory, reflection context, error paths)
- _manage_goals_from_analysis (opportunity/problem goal creation, dedup, rollback)
- _generate_plans_for_unplanned_goals (procedural memory, plan generation, error paths)
- _apply_goal_recommendations edge cases (abandon failure, priority update failure/None)
- strategic_planning_cycle end-to-end
- _record_strategic_planning_episode
- _get_available_capabilities
- _format helpers
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from empla.core.loop.models import LoopConfig
from empla.core.loop.protocols import GoalRecommendation, SituationAnalysis

# ============================================================================
# Helpers
# ============================================================================


class MockGoal:
    def __init__(
        self,
        description: str = "Test goal",
        goal_type: str = "maintain",
        priority: int = 5,
        target: dict[str, Any] | None = None,
    ):
        self.id = uuid4()
        self.description = description
        self.goal_type = goal_type
        self.priority = priority
        self.target = target or {}
        self.created_at = datetime.now(UTC) - timedelta(hours=1)
        self.current_progress = {}


class MockBelief:
    def __init__(
        self,
        subject: str = "customer",
        predicate: str = "interest",
        confidence: float = 0.8,
        importance: float = 0.5,
    ):
        self.subject = subject
        self.predicate = predicate
        self.object = {"value": 42}
        self.confidence = confidence
        self.importance = importance


def _make_planning_mixin(
    *,
    llm: Any = None,
    tool_router: Any = None,
    memory: Any = None,
):
    from empla.core.loop.planning import PlanningMixin

    mixin = PlanningMixin()
    mixin.employee = Mock(id=uuid4())
    mixin.beliefs = Mock()
    mixin.beliefs.get_all_beliefs = AsyncMock(return_value=[])
    mixin.goals = Mock()
    mixin.goals.get_active_goals = AsyncMock(return_value=[])
    mixin.goals.add_goal = AsyncMock(return_value=Mock())
    mixin.goals.abandon_goal = AsyncMock(return_value=Mock())
    mixin.goals.update_goal_priority = AsyncMock(return_value=Mock())
    mixin.goals.rollback = AsyncMock()
    mixin.intentions = Mock()
    mixin.intentions.get_intentions_for_goal = AsyncMock(return_value=[])
    mixin.intentions.generate_plan_for_goal = AsyncMock(return_value=[Mock()])
    mixin.llm_service = llm
    mixin.tool_router = tool_router
    mixin.memory = memory or Mock(spec=[])  # no episodic/procedural by default
    mixin.config = LoopConfig(cycle_interval_seconds=1)
    mixin._identity_prompt = "You are a sales AE."
    mixin._identity = "sales_ae"
    mixin._refresh_identity_prompt = AsyncMock()
    mixin.last_strategic_planning = None
    return mixin


# ============================================================================
# _analyze_situation_with_llm
# ============================================================================


class TestAnalyzeSituationWithLLM:
    @pytest.mark.asyncio
    async def test_returns_fallback_when_no_llm(self):
        mixin = _make_planning_mixin(llm=None)
        result = await mixin._analyze_situation_with_llm([], [], [])
        assert result.current_state_summary == "No LLM service available"
        assert result.gaps == []

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        llm = Mock()
        expected = SituationAnalysis(
            current_state_summary="All good",
            gaps=["gap1"],
            opportunities=["opp1"],
            problems=["prob1"],
            recommended_focus="pipeline",
        )
        llm.generate_structured = AsyncMock(return_value=(Mock(), expected))
        mixin = _make_planning_mixin(llm=llm)

        result = await mixin._analyze_situation_with_llm(
            beliefs=[MockBelief()],
            goals=[MockGoal()],
            capabilities=["email", "crm"],
        )
        assert result.recommended_focus == "pipeline"
        assert result.gaps == ["gap1"]
        llm.generate_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(self):
        llm = Mock()
        llm.generate_structured = AsyncMock(side_effect=RuntimeError("API down"))
        mixin = _make_planning_mixin(llm=llm)

        result = await mixin._analyze_situation_with_llm([], [], [])
        assert result.current_state_summary == "Analysis failed"

    @pytest.mark.asyncio
    async def test_uses_identity_prompt(self):
        llm = Mock()
        llm.generate_structured = AsyncMock(
            return_value=(
                Mock(),
                SituationAnalysis(
                    current_state_summary="ok",
                    recommended_focus="test",
                ),
            )
        )
        mixin = _make_planning_mixin(llm=llm)
        mixin._identity_prompt = "You are a CSM."

        await mixin._analyze_situation_with_llm([], [], [])
        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "CSM" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_no_identity_prompt_uses_default(self):
        llm = Mock()
        llm.generate_structured = AsyncMock(
            return_value=(
                Mock(),
                SituationAnalysis(
                    current_state_summary="ok",
                    recommended_focus="test",
                ),
            )
        )
        mixin = _make_planning_mixin(llm=llm)
        mixin._identity_prompt = None

        await mixin._analyze_situation_with_llm([], [], [])
        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "digital employee" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_semantic_memory_injected(self):
        """Semantic memory facts are injected into the prompt."""
        llm = Mock()
        llm.generate_structured = AsyncMock(
            return_value=(
                Mock(),
                SituationAnalysis(
                    current_state_summary="ok",
                    recommended_focus="test",
                ),
            )
        )
        memory = Mock()
        fact = Mock(subject="acme", predicate="status", object="active")
        memory.semantic = Mock()
        memory.semantic.query_facts = AsyncMock(return_value=[fact])
        mixin = _make_planning_mixin(llm=llm, memory=memory)

        beliefs = [MockBelief(subject="acme")]
        await mixin._analyze_situation_with_llm(beliefs, [], [])
        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "acme" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_semantic_memory_failure_handled(self):
        """Semantic memory failure doesn't crash the analysis."""
        llm = Mock()
        llm.generate_structured = AsyncMock(
            return_value=(
                Mock(),
                SituationAnalysis(
                    current_state_summary="ok",
                    recommended_focus="test",
                ),
            )
        )
        memory = Mock()
        memory.semantic = Mock()
        memory.semantic.query_facts = AsyncMock(side_effect=RuntimeError("DB"))
        mixin = _make_planning_mixin(llm=llm, memory=memory)

        result = await mixin._analyze_situation_with_llm([MockBelief()], [], [])
        assert result.recommended_focus == "test"

    @pytest.mark.asyncio
    async def test_episodic_reflection_injected(self):
        """Latest deep reflection is injected into the prompt."""
        llm = Mock()
        llm.generate_structured = AsyncMock(
            return_value=(
                Mock(),
                SituationAnalysis(
                    current_state_summary="ok",
                    recommended_focus="test",
                ),
            )
        )
        memory = Mock()
        memory.semantic = Mock()
        memory.semantic.query_facts = AsyncMock(return_value=[])
        ep = Mock(description="Insight: improve pipeline strategy")
        memory.episodic = Mock()
        memory.episodic.recall_recent = AsyncMock(return_value=[ep])
        mixin = _make_planning_mixin(llm=llm, memory=memory)

        await mixin._analyze_situation_with_llm([], [], [])
        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "Insight" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_episodic_reflection_failure_handled(self):
        """Episodic memory failure doesn't crash the analysis."""
        llm = Mock()
        llm.generate_structured = AsyncMock(
            return_value=(
                Mock(),
                SituationAnalysis(
                    current_state_summary="ok",
                    recommended_focus="test",
                ),
            )
        )
        memory = Mock()
        memory.semantic = Mock()
        memory.semantic.query_facts = AsyncMock(return_value=[])
        memory.episodic = Mock()
        memory.episodic.recall_recent = AsyncMock(side_effect=RuntimeError("DB"))
        mixin = _make_planning_mixin(llm=llm, memory=memory)

        result = await mixin._analyze_situation_with_llm([], [], [])
        assert result.recommended_focus == "test"


# ============================================================================
# _manage_goals_from_analysis
# ============================================================================


class TestManageGoalsFromAnalysis:
    @pytest.mark.asyncio
    async def test_creates_opportunity_goals(self):
        mixin = _make_planning_mixin()
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=["expand into enterprise"],
            problems=[],
            recommended_focus="growth",
        )
        await mixin._manage_goals_from_analysis(analysis, [])
        mixin.goals.add_goal.assert_called_once()
        call_kwargs = mixin.goals.add_goal.call_args.kwargs
        assert call_kwargs["goal_type"] == "opportunity"
        assert call_kwargs["priority"] == 6

    @pytest.mark.asyncio
    async def test_creates_problem_goals(self):
        mixin = _make_planning_mixin()
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=[],
            problems=["pipeline is empty"],
            recommended_focus="pipeline",
        )
        await mixin._manage_goals_from_analysis(analysis, [])
        mixin.goals.add_goal.assert_called_once()
        call_kwargs = mixin.goals.add_goal.call_args.kwargs
        assert call_kwargs["goal_type"] == "problem"
        assert call_kwargs["priority"] == 8

    @pytest.mark.asyncio
    async def test_dedup_skips_existing_opportunity(self):
        mixin = _make_planning_mixin()
        existing = MockGoal(description="Pursue opportunity: expand into enterprise")
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=["expand into enterprise"],
            problems=[],
            recommended_focus="growth",
        )
        await mixin._manage_goals_from_analysis(analysis, [existing])
        mixin.goals.add_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedup_skips_existing_problem(self):
        mixin = _make_planning_mixin()
        existing = MockGoal(description="Address problem: pipeline is empty")
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=[],
            problems=["pipeline is empty"],
            recommended_focus="pipeline",
        )
        await mixin._manage_goals_from_analysis(analysis, [existing])
        mixin.goals.add_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_limits_opportunities_to_3(self):
        mixin = _make_planning_mixin()
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=["opp1", "opp2", "opp3", "opp4", "opp5"],
            problems=[],
            recommended_focus="growth",
        )
        await mixin._manage_goals_from_analysis(analysis, [])
        assert mixin.goals.add_goal.call_count == 3

    @pytest.mark.asyncio
    async def test_limits_problems_to_2(self):
        mixin = _make_planning_mixin()
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=[],
            problems=["p1", "p2", "p3", "p4"],
            recommended_focus="fix",
        )
        await mixin._manage_goals_from_analysis(analysis, [])
        assert mixin.goals.add_goal.call_count == 2

    @pytest.mark.asyncio
    async def test_add_goal_failure_triggers_rollback(self):
        mixin = _make_planning_mixin()
        mixin.goals.add_goal = AsyncMock(side_effect=RuntimeError("DB error"))
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=["new opp"],
            problems=[],
            recommended_focus="growth",
        )
        await mixin._manage_goals_from_analysis(analysis, [])
        mixin.goals.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_problem_add_failure_triggers_rollback(self):
        mixin = _make_planning_mixin()
        mixin.goals.add_goal = AsyncMock(side_effect=RuntimeError("DB error"))
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=[],
            problems=["critical problem"],
            recommended_focus="fix",
        )
        await mixin._manage_goals_from_analysis(analysis, [])
        mixin.goals.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_word_overlap_dedup(self):
        """Goals with high word overlap are deduplicated."""
        mixin = _make_planning_mixin()
        existing = MockGoal(description="expand enterprise market coverage")
        analysis = SituationAnalysis(
            current_state_summary="ok",
            opportunities=["expand enterprise market coverage aggressively"],
            problems=[],
            recommended_focus="growth",
        )
        await mixin._manage_goals_from_analysis(analysis, [existing])
        mixin.goals.add_goal.assert_not_called()


# ============================================================================
# _generate_plans_for_unplanned_goals
# ============================================================================


class TestGeneratePlansForUnplannedGoals:
    @pytest.mark.asyncio
    async def test_no_llm_service_skips(self):
        mixin = _make_planning_mixin(llm=None)
        await mixin._generate_plans_for_unplanned_goals(
            goals=[MockGoal()], beliefs=[], capabilities=[]
        )
        mixin.intentions.generate_plan_for_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_goals_with_existing_intentions(self):
        llm = Mock()
        mixin = _make_planning_mixin(llm=llm)
        goal = MockGoal()
        mixin.intentions.get_intentions_for_goal = AsyncMock(return_value=[Mock()])
        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])
        mixin.intentions.generate_plan_for_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_generates_plan_for_unplanned_goal(self):
        llm = Mock()
        mixin = _make_planning_mixin(llm=llm)
        goal = MockGoal()
        await mixin._generate_plans_for_unplanned_goals(
            goals=[goal], beliefs=[], capabilities=["email"]
        )
        mixin.intentions.generate_plan_for_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_limits_to_5_goals(self):
        llm = Mock()
        mixin = _make_planning_mixin(llm=llm)
        goals = [MockGoal(description=f"goal {i}") for i in range(8)]
        await mixin._generate_plans_for_unplanned_goals(goals=goals, beliefs=[], capabilities=[])
        assert mixin.intentions.generate_plan_for_goal.call_count == 5

    @pytest.mark.asyncio
    async def test_skips_goal_without_id(self):
        llm = Mock()
        mixin = _make_planning_mixin(llm=llm)
        goal = Mock(spec=[])  # no .id attribute
        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])
        mixin.intentions.generate_plan_for_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_intention_check_failure_continues(self):
        llm = Mock()
        mixin = _make_planning_mixin(llm=llm)
        goal1 = MockGoal(description="goal1")
        goal2 = MockGoal(description="goal2")
        mixin.intentions.get_intentions_for_goal = AsyncMock(side_effect=[RuntimeError("DB"), []])
        await mixin._generate_plans_for_unplanned_goals(
            goals=[goal1, goal2], beliefs=[], capabilities=[]
        )
        # goal1 errors, goal2 proceeds
        mixin.intentions.generate_plan_for_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_generation_failure_continues(self):
        llm = Mock()
        mixin = _make_planning_mixin(llm=llm)
        goal = MockGoal()
        mixin.intentions.generate_plan_for_goal = AsyncMock(side_effect=RuntimeError("LLM error"))
        # Should not raise
        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])

    @pytest.mark.asyncio
    async def test_procedural_memory_queried(self):
        llm = Mock()
        memory = Mock()
        proc = Mock(name="proc1", steps=[{"action": "send_email"}], success_rate=0.9)
        proc.name = "proc1"
        memory.procedural = Mock()
        memory.procedural.find_procedures_for_situation = AsyncMock(return_value=[proc])
        mixin = _make_planning_mixin(llm=llm, memory=memory)
        goal = MockGoal()

        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])
        memory.procedural.find_procedures_for_situation.assert_called_once()
        # Verify procedural context is passed to generate_plan_for_goal
        call_kwargs = mixin.intentions.generate_plan_for_goal.call_args.kwargs
        assert "proc1" in (call_kwargs.get("identity_context") or "")

    @pytest.mark.asyncio
    async def test_procedural_memory_failure_handled(self):
        llm = Mock()
        memory = Mock()
        memory.procedural = Mock()
        memory.procedural.find_procedures_for_situation = AsyncMock(
            side_effect=RuntimeError("DB error")
        )
        mixin = _make_planning_mixin(llm=llm, memory=memory)
        goal = MockGoal()

        # Should not raise, proceeds without procedural context
        await mixin._generate_plans_for_unplanned_goals(goals=[goal], beliefs=[], capabilities=[])
        mixin.intentions.generate_plan_for_goal.assert_called_once()


# ============================================================================
# _apply_goal_recommendations — edge cases
# ============================================================================


class TestApplyGoalRecommendationsEdgeCases:
    def _make_mixin(self):
        return _make_planning_mixin(llm=Mock())

    @pytest.mark.asyncio
    async def test_abandon_failure_triggers_rollback(self):
        mixin = self._make_mixin()
        goal = MockGoal(description="test goal")
        rec = GoalRecommendation(
            goals_to_abandon=["test goal"],
            priority_adjustments=[],
            new_goals=[],
            reasoning="not needed",
        )
        mixin.llm_service.generate_structured = AsyncMock(return_value=(None, rec))
        mixin.goals.abandon_goal = AsyncMock(side_effect=RuntimeError("DB error"))

        await mixin._apply_goal_recommendations(
            beliefs=[],
            active_goals=[goal],
            situation_analysis=SituationAnalysis(
                current_state_summary="ok", recommended_focus="test"
            ),
        )
        mixin.goals.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_abandon_returns_none_triggers_rollback(self):
        mixin = self._make_mixin()
        goal = MockGoal(description="test goal")
        rec = GoalRecommendation(
            goals_to_abandon=["test goal"],
            priority_adjustments=[],
            new_goals=[],
            reasoning="not needed",
        )
        mixin.llm_service.generate_structured = AsyncMock(return_value=(None, rec))
        mixin.goals.abandon_goal = AsyncMock(return_value=None)

        await mixin._apply_goal_recommendations(
            beliefs=[],
            active_goals=[goal],
            situation_analysis=SituationAnalysis(
                current_state_summary="ok", recommended_focus="test"
            ),
        )
        mixin.goals.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_priority_update_failure_triggers_rollback(self):
        mixin = self._make_mixin()
        goal = MockGoal(description="test goal")
        rec = GoalRecommendation(
            goals_to_abandon=[],
            priority_adjustments=[{"description": "test goal", "new_priority": 8}],
            new_goals=[],
            reasoning="reprioritize",
        )
        mixin.llm_service.generate_structured = AsyncMock(return_value=(None, rec))
        mixin.goals.update_goal_priority = AsyncMock(side_effect=RuntimeError("DB"))

        await mixin._apply_goal_recommendations(
            beliefs=[],
            active_goals=[goal],
            situation_analysis=SituationAnalysis(
                current_state_summary="ok", recommended_focus="test"
            ),
        )
        mixin.goals.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_priority_update_returns_none_triggers_rollback(self):
        mixin = self._make_mixin()
        goal = MockGoal(description="test goal")
        rec = GoalRecommendation(
            goals_to_abandon=[],
            priority_adjustments=[{"description": "test goal", "new_priority": 8}],
            new_goals=[],
            reasoning="reprioritize",
        )
        mixin.llm_service.generate_structured = AsyncMock(return_value=(None, rec))
        mixin.goals.update_goal_priority = AsyncMock(return_value=None)

        await mixin._apply_goal_recommendations(
            beliefs=[],
            active_goals=[goal],
            situation_analysis=SituationAnalysis(
                current_state_summary="ok", recommended_focus="test"
            ),
        )
        mixin.goals.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_priority_adjustment_missing_fields_skipped(self):
        mixin = self._make_mixin()
        goal = MockGoal(description="test goal")
        rec = GoalRecommendation(
            goals_to_abandon=[],
            priority_adjustments=[
                {"description": "", "new_priority": 8},  # empty desc
                {"description": "test goal"},  # missing new_priority
            ],
            new_goals=[],
            reasoning="test",
        )
        mixin.llm_service.generate_structured = AsyncMock(return_value=(None, rec))

        await mixin._apply_goal_recommendations(
            beliefs=[],
            active_goals=[goal],
            situation_analysis=SituationAnalysis(
                current_state_summary="ok", recommended_focus="test"
            ),
        )
        mixin.goals.update_goal_priority.assert_not_called()


# ============================================================================
# strategic_planning_cycle end-to-end
# ============================================================================


class TestStrategicPlanningCycle:
    @pytest.mark.asyncio
    async def test_full_cycle_with_llm(self):
        llm = Mock()
        analysis = SituationAnalysis(
            current_state_summary="ok",
            gaps=[],
            opportunities=[],
            problems=[],
            recommended_focus="pipeline",
        )
        rec = GoalRecommendation(
            goals_to_abandon=[],
            priority_adjustments=[],
            new_goals=[],
            reasoning="all good",
        )
        llm.generate_structured = AsyncMock(side_effect=[(Mock(), analysis), (Mock(), rec)])
        memory = Mock()
        memory.episodic = Mock()
        memory.episodic.record_episode = AsyncMock()
        mixin = _make_planning_mixin(llm=llm, memory=memory)

        await mixin.strategic_planning_cycle()

        assert mixin.last_strategic_planning is not None
        mixin._refresh_identity_prompt.assert_called_once()
        memory.episodic.record_episode.assert_called_once()

    @pytest.mark.asyncio
    async def test_cycle_without_llm(self):
        mixin = _make_planning_mixin(llm=None)
        await mixin.strategic_planning_cycle()
        assert mixin.last_strategic_planning is not None

    @pytest.mark.asyncio
    async def test_cycle_handles_exception(self):
        llm = Mock()
        llm.generate_structured = AsyncMock(side_effect=RuntimeError("Boom"))
        mixin = _make_planning_mixin(llm=llm)
        mixin.beliefs.get_all_beliefs = AsyncMock(side_effect=RuntimeError("DB"))

        # Should not raise
        await mixin.strategic_planning_cycle()
        assert mixin.last_strategic_planning is not None


# ============================================================================
# _get_available_capabilities
# ============================================================================


class TestGetAvailableCapabilities:
    def test_no_tool_router(self):
        mixin = _make_planning_mixin(tool_router=None)
        assert mixin._get_available_capabilities() == []

    def test_tool_router_returns_capabilities(self):
        router = Mock()
        router.get_enabled_capabilities = Mock(return_value=["email", "crm"])
        mixin = _make_planning_mixin(tool_router=router)
        assert mixin._get_available_capabilities() == ["email", "crm"]

    def test_tool_router_failure_returns_empty(self):
        router = Mock()
        router.get_enabled_capabilities = Mock(side_effect=RuntimeError("err"))
        mixin = _make_planning_mixin(tool_router=router)
        assert mixin._get_available_capabilities() == []


# ============================================================================
# _format helpers
# ============================================================================


class TestFormatHelpers:
    def test_format_beliefs_empty(self):
        mixin = _make_planning_mixin()
        assert mixin._format_beliefs_for_llm([]) == "No current beliefs"

    def test_format_beliefs_truncates_at_20(self):
        mixin = _make_planning_mixin()
        beliefs = [MockBelief(subject=f"s{i}") for i in range(25)]
        text = mixin._format_beliefs_for_llm(beliefs)
        assert "and 5 more beliefs" in text

    def test_format_goals_empty(self):
        mixin = _make_planning_mixin()
        assert mixin._format_goals_for_llm([]) == "No active goals"

    def test_format_goals_with_content(self):
        mixin = _make_planning_mixin()
        goal = MockGoal(description="Test", priority=7, target={"metric": "x"})
        text = mixin._format_goals_for_llm([goal])
        assert "[7/10]" in text
        assert "Test" in text


# ============================================================================
# _record_strategic_planning_episode
# ============================================================================


class TestRecordStrategicPlanningEpisode:
    @pytest.mark.asyncio
    async def test_records_when_episodic_available(self):
        memory = Mock()
        memory.episodic = Mock()
        memory.episodic.record_episode = AsyncMock()
        mixin = _make_planning_mixin(memory=memory)

        await mixin._record_strategic_planning_episode(beliefs_count=10, goals_count=3)
        memory.episodic.record_episode.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_episodic_no_error(self):
        mixin = _make_planning_mixin()  # no episodic
        await mixin._record_strategic_planning_episode(beliefs_count=0, goals_count=0)

    @pytest.mark.asyncio
    async def test_episodic_failure_handled(self):
        memory = Mock()
        memory.episodic = Mock()
        memory.episodic.record_episode = AsyncMock(side_effect=RuntimeError("DB"))
        mixin = _make_planning_mixin(memory=memory)

        # Should not raise
        await mixin._record_strategic_planning_episode(beliefs_count=10, goals_count=3)


# ============================================================================
# _words_overlap
# ============================================================================


class TestWordsOverlap:
    def test_identical(self):
        from empla.core.loop.planning import PlanningMixin

        assert PlanningMixin._words_overlap("a b c", "a b c") == 1.0

    def test_no_overlap(self):
        from empla.core.loop.planning import PlanningMixin

        assert PlanningMixin._words_overlap("a b", "c d") == 0.0

    def test_partial(self):
        from empla.core.loop.planning import PlanningMixin

        result = PlanningMixin._words_overlap("a b c", "b c d")
        assert 0.4 < result < 0.7

    def test_empty(self):
        from empla.core.loop.planning import PlanningMixin

        assert PlanningMixin._words_overlap("", "a") == 0.0
        assert PlanningMixin._words_overlap("a", "") == 0.0


# ============================================================================
# _safe_rollback_goals
# ============================================================================


class TestSafeRollbackGoals:
    @pytest.mark.asyncio
    async def test_rollback_success(self):
        mixin = _make_planning_mixin()
        await mixin._safe_rollback_goals()
        mixin.goals.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_failure_handled(self):
        mixin = _make_planning_mixin()
        mixin.goals.rollback = AsyncMock(side_effect=RuntimeError("rollback failed"))
        # Should not raise
        await mixin._safe_rollback_goals()
