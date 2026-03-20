"""
Tests for BDI loop completion features:
- GoalRecommendation wiring in strategic planning
- Deep reflection → belief conversion
- Non-numeric goal LLM completion check

These are the three Phase 3C stragglers closed by the Production Foundation plan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from empla.core.loop.models import NonNumericGoalBatchEvaluation, NonNumericGoalEvaluation
from empla.core.loop.protocols import GoalRecommendation

# ============================================================================
# Mock Helpers
# ============================================================================


class MockGoal:
    """Mock goal for testing."""

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


class MockBeliefChange:
    """Mock belief change."""

    def __init__(
        self,
        subject: str = "test",
        predicate: str = "value",
        importance: float = 0.5,
        old_confidence: float = 0.3,
        new_confidence: float = 0.7,
    ):
        self.subject = subject
        self.predicate = predicate
        self.importance = importance
        self.old_confidence = old_confidence
        self.new_confidence = new_confidence
        self.belief = Mock(object={"value": 42})


class MockLLMService:
    """Mock LLM service that returns configurable structured outputs."""

    def __init__(self):
        self.generate_structured = AsyncMock()
        self.generate = AsyncMock()


# ============================================================================
# GoalRecommendation Tests
# ============================================================================


class TestGoalRecommendation:
    """Tests for GoalRecommendation wiring in planning.py."""

    def test_model_uses_descriptions_not_uuids(self):
        """GoalRecommendation.goals_to_abandon should contain descriptions."""
        rec = GoalRecommendation(
            goals_to_abandon=["Pursue opportunity: expand into enterprise"],
            priority_adjustments=[],
            new_goals=[],
            reasoning="Enterprise opportunity no longer viable",
        )
        assert "expand into enterprise" in rec.goals_to_abandon[0]

    def test_model_validates_required_fields(self):
        """GoalRecommendation requires reasoning field."""
        with pytest.raises(Exception):
            GoalRecommendation(
                goals_to_abandon=[],
                priority_adjustments=[],
                new_goals=[],
                # reasoning is missing
            )

    def test_model_empty_recommendations_valid(self):
        """Empty recommendations (no changes) should be valid."""
        rec = GoalRecommendation(
            goals_to_abandon=[],
            priority_adjustments=[],
            new_goals=[],
            reasoning="Current goals are well-aligned, no changes needed",
        )
        assert len(rec.goals_to_abandon) == 0
        assert len(rec.priority_adjustments) == 0
        assert len(rec.new_goals) == 0


class TestFuzzyMatchGoal:
    """Tests for _fuzzy_match_goal in PlanningMixin."""

    def _make_mixin(self):
        """Create a minimal PlanningMixin instance for testing."""
        from empla.core.loop.planning import PlanningMixin

        return PlanningMixin()

    def test_exact_substring_match(self):
        """Exact substring should match."""
        mixin = self._make_mixin()
        goal = MockGoal(description="Pursue opportunity: expand into enterprise")
        goals_by_desc = {"Pursue opportunity: expand into enterprise": goal}

        result = mixin._fuzzy_match_goal("expand into enterprise", goals_by_desc)
        assert result is goal

    def test_reverse_substring_match(self):
        """Goal description as substring of query should match."""
        mixin = self._make_mixin()
        goal = MockGoal(description="enterprise expansion")
        goals_by_desc = {"enterprise expansion": goal}

        result = mixin._fuzzy_match_goal(
            "We should abandon enterprise expansion because market shifted", goals_by_desc
        )
        assert result is goal

    def test_fuzzy_word_overlap_match(self):
        """Similar wording should match via Jaccard similarity."""
        mixin = self._make_mixin()
        goal = MockGoal(description="Address problem: pipeline coverage too low")
        goals_by_desc = {"Address problem: pipeline coverage too low": goal}

        result = mixin._fuzzy_match_goal("pipeline coverage is too low", goals_by_desc)
        assert result is goal

    def test_no_match_returns_none(self):
        """Completely unrelated descriptions should not match."""
        mixin = self._make_mixin()
        goal = MockGoal(description="Maintain 3x pipeline coverage")
        goals_by_desc = {"Maintain 3x pipeline coverage": goal}

        result = mixin._fuzzy_match_goal("improve customer satisfaction scores", goals_by_desc)
        assert result is None

    def test_empty_goals_returns_none(self):
        """Empty goals dict should return None."""
        mixin = self._make_mixin()
        result = mixin._fuzzy_match_goal("anything", {})
        assert result is None

    def test_best_match_selected(self):
        """When multiple goals partially match, the best one should win."""
        mixin = self._make_mixin()
        goal1 = MockGoal(description="expand pipeline coverage")
        goal2 = MockGoal(description="expand into enterprise market")
        goals_by_desc = {
            "expand pipeline coverage": goal1,
            "expand into enterprise market": goal2,
        }

        # "expand into enterprise" is a substring of goal2
        result = mixin._fuzzy_match_goal("expand into enterprise", goals_by_desc)
        assert result is goal2


# ============================================================================
# Deep Reflection → Belief Conversion Tests
# ============================================================================


class TestDeepReflectionBeliefConversion:
    """Tests for _convert_insights_to_beliefs in ReflectionMixin."""

    def _make_mixin(self):
        """Create a minimal ReflectionMixin with mocked dependencies."""
        from empla.core.loop.reflection import ReflectionMixin

        mixin = ReflectionMixin()
        mixin.employee = Mock(id=uuid4())
        mixin.beliefs = Mock()
        mixin.beliefs.update_belief = AsyncMock()
        mixin.memory = Mock()
        mixin.memory.procedural = Mock()
        mixin.memory.procedural.record_procedure = AsyncMock()
        return mixin

    @pytest.mark.asyncio
    async def test_creates_strategy_effectiveness_belief(self):
        """Should always create a strategy_effectiveness belief."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs("Things are going well", 0.8)

        mixin.beliefs.update_belief.assert_any_call(
            subject="self",
            predicate="strategy_effectiveness",
            belief_object={
                "assessment": "effective",
                "success_rate": 0.8,
                "insight": "Things are going well"[:200],
            },
            confidence=0.85,
            source="deep_reflection",
        )

    @pytest.mark.asyncio
    async def test_effectiveness_assessment_struggling(self):
        """Low success rate should produce 'struggling' assessment."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs("Many errors detected", 0.3)

        call_args = mixin.beliefs.update_belief.call_args_list[0]
        assert call_args.kwargs["belief_object"]["assessment"] == "struggling"

    @pytest.mark.asyncio
    async def test_effectiveness_assessment_mixed(self):
        """Middle success rate should produce 'mixed' assessment."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs("Some wins some losses", 0.55)

        call_args = mixin.beliefs.update_belief.call_args_list[0]
        assert call_args.kwargs["belief_object"]["assessment"] == "mixed"

    @pytest.mark.asyncio
    async def test_creates_failure_pattern_belief(self):
        """Analysis mentioning failures should create known_failure_patterns belief."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs(
            "Common failure pattern: API timeouts during peak hours", 0.4
        )

        predicates = [c.kwargs["predicate"] for c in mixin.beliefs.update_belief.call_args_list]
        assert "known_failure_patterns" in predicates

    @pytest.mark.asyncio
    async def test_creates_improvement_belief(self):
        """Analysis mentioning improvements should create improvement_opportunities belief."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs(
            "Could improve response times by batching requests", 0.6
        )

        predicates = [c.kwargs["predicate"] for c in mixin.beliefs.update_belief.call_args_list]
        assert "improvement_opportunities" in predicates

    @pytest.mark.asyncio
    async def test_records_procedural_memory_on_low_success(self):
        """Low success rate should trigger procedural memory recording."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs("Strategy failing badly", 0.3)

        mixin.memory.procedural.record_procedure.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_procedural_memory_on_high_success(self):
        """High success rate should NOT trigger procedural memory recording."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs("Everything is great", 0.9)

        mixin.memory.procedural.record_procedure.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_analysis_skips(self):
        """None or empty analysis should skip entirely."""
        mixin = self._make_mixin()

        await mixin._convert_insights_to_beliefs(None, 0.5)
        mixin.beliefs.update_belief.assert_not_called()

        await mixin._convert_insights_to_beliefs("", 0.5)
        mixin.beliefs.update_belief.assert_not_called()

    @pytest.mark.asyncio
    async def test_belief_update_failure_continues(self):
        """Belief update failure should log and continue, not crash."""
        mixin = self._make_mixin()
        mixin.beliefs.update_belief = AsyncMock(side_effect=Exception("DB error"))

        # Should not raise
        await mixin._convert_insights_to_beliefs("Some analysis with failure keywords", 0.5)


# ============================================================================
# Non-Numeric Goal Completion Tests
# ============================================================================


class TestNonNumericGoalEvaluation:
    """Tests for _evaluate_non_numeric_goals in GoalManagementMixin."""

    def test_model_validation(self):
        """NonNumericGoalEvaluation should validate fields."""
        eval_result = NonNumericGoalEvaluation(
            goal_id=str(uuid4()),
            is_complete=True,
            confidence=0.85,
            reasoning="The pipeline issue has been resolved",
        )
        assert eval_result.is_complete is True
        assert eval_result.confidence == 0.85

    def test_batch_model(self):
        """NonNumericGoalBatchEvaluation should hold multiple results."""
        batch = NonNumericGoalBatchEvaluation(
            results=[
                NonNumericGoalEvaluation(
                    goal_id=str(uuid4()),
                    is_complete=True,
                    confidence=0.9,
                    reasoning="Done",
                ),
                NonNumericGoalEvaluation(
                    goal_id=str(uuid4()),
                    is_complete=False,
                    confidence=0.8,
                    reasoning="Still in progress",
                ),
            ]
        )
        assert len(batch.results) == 2

    def test_confidence_range_validation(self):
        """Confidence must be between 0 and 1."""
        with pytest.raises(Exception):
            NonNumericGoalEvaluation(
                goal_id=str(uuid4()),
                is_complete=True,
                confidence=1.5,  # Out of range
                reasoning="test",
            )


class TestGoalRecommendationModel:
    """Tests for the GoalRecommendation Pydantic model."""

    def test_priority_adjustments_with_description(self):
        """Priority adjustments should use descriptions, not UUIDs."""
        rec = GoalRecommendation(
            goals_to_abandon=[],
            priority_adjustments=[
                {"description": "Maintain 3x pipeline coverage", "new_priority": 9}
            ],
            new_goals=[],
            reasoning="Pipeline is critical right now",
        )
        assert rec.priority_adjustments[0]["description"] == "Maintain 3x pipeline coverage"
        assert rec.priority_adjustments[0]["new_priority"] == 9

    def test_new_goals_format(self):
        """New goals should include description, priority, and goal_type."""
        rec = GoalRecommendation(
            goals_to_abandon=[],
            priority_adjustments=[],
            new_goals=[
                {
                    "description": "Build relationship with key accounts",
                    "priority": 7,
                    "goal_type": "opportunity",
                }
            ],
            reasoning="Key accounts need attention",
        )
        assert len(rec.new_goals) == 1
        assert rec.new_goals[0]["priority"] == 7
