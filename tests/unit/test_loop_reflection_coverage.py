"""
Coverage tests for empla.core.loop.reflection — uncovered lines.

Focuses on:
- reflection_cycle (full flow, error path)
- _record_execution_episode
- _update_procedural_memory (success/failure paths, trigger conditions)
- _update_effectiveness_beliefs
- deep_reflection_cycle (full flow, no episodes, LLM analysis)
- _get_recent_episodes
- _analyze_patterns_with_llm (episodic record, semantic store, insight conversion)
- _maintain_memory_health (episodic + procedural maintenance)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from empla.core.loop.models import IntentionResult, LoopConfig

# ============================================================================
# Helpers
# ============================================================================


def _make_reflection_mixin(
    *,
    llm: Any = None,
    memory: Any = None,
    has_episodic: bool = False,
    has_procedural: bool = False,
    has_semantic: bool = False,
):
    from empla.core.loop.reflection import ReflectionMixin

    mixin = ReflectionMixin()
    mixin.employee = Mock(id=uuid4())
    mixin.beliefs = Mock()
    mixin.beliefs.update_belief = AsyncMock()
    mixin.goals = Mock()
    mixin.goals.get_goal = AsyncMock(return_value=None)
    mixin.llm_service = llm
    mixin.config = LoopConfig(cycle_interval_seconds=1, deep_reflection_interval_hours=24)
    mixin._identity_prompt = "You are a sales AE."
    mixin.last_deep_reflection = None

    if memory is not None:
        mixin.memory = memory
    else:
        mem = Mock(spec=[])
        if has_episodic:
            mem.episodic = Mock()
            mem.episodic.record_episode = AsyncMock()
            mem.episodic.recall_recent = AsyncMock(return_value=[])
            mem.episodic.reinforce_frequently_recalled = AsyncMock(return_value=2)
            mem.episodic.decay_rarely_recalled = AsyncMock(return_value=1)
        if has_procedural:
            mem.procedural = Mock()
            mem.procedural.record_procedure = AsyncMock()
            mem.procedural.reinforce_successful_procedures = AsyncMock()
            mem.procedural.archive_poor_procedures = AsyncMock()
        if has_semantic:
            mem.semantic = Mock()
            mem.semantic.store_fact = AsyncMock()
        mixin.memory = mem

    return mixin


def _make_result(
    *,
    success: bool = True,
    outcome: dict[str, Any] | None = None,
    duration_ms: float = 500.0,
) -> IntentionResult:
    return IntentionResult(
        intention_id=uuid4(),
        success=success,
        outcome=outcome or {},
        duration_ms=duration_ms,
    )


# ============================================================================
# reflection_cycle
# ============================================================================


class TestReflectionCycle:
    @pytest.mark.asyncio
    async def test_successful_reflection(self):
        mixin = _make_reflection_mixin(has_episodic=True, has_procedural=True)
        result = _make_result(
            success=True,
            outcome={
                "tools_used": ["email.send"],
                "tool_results": [{"tool": "email.send", "success": True}],
            },
        )
        await mixin.reflection_cycle(result)
        mixin.memory.episodic.record_episode.assert_called_once()
        mixin.memory.procedural.record_procedure.assert_called_once()

    @pytest.mark.asyncio
    async def test_reflection_handles_exception(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        mixin.memory.episodic.record_episode = AsyncMock(side_effect=RuntimeError("DB"))
        result = _make_result()
        # Should not raise
        await mixin.reflection_cycle(result)


# ============================================================================
# _record_execution_episode
# ============================================================================


class TestRecordExecutionEpisode:
    @pytest.mark.asyncio
    async def test_records_success_episode(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        result = _make_result(success=True)
        await mixin._record_execution_episode(result)
        call_kwargs = mixin.memory.episodic.record_episode.call_args.kwargs
        assert call_kwargs["importance"] == 0.7

    @pytest.mark.asyncio
    async def test_records_failure_episode_higher_importance(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        result = _make_result(success=False)
        await mixin._record_execution_episode(result)
        call_kwargs = mixin.memory.episodic.record_episode.call_args.kwargs
        assert call_kwargs["importance"] == 0.8

    @pytest.mark.asyncio
    async def test_no_episodic_no_error(self):
        mixin = _make_reflection_mixin()
        result = _make_result()
        await mixin._record_execution_episode(result)

    @pytest.mark.asyncio
    async def test_episodic_failure_handled(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        mixin.memory.episodic.record_episode = AsyncMock(side_effect=RuntimeError("DB"))
        result = _make_result()
        # Should not raise
        await mixin._record_execution_episode(result)


# ============================================================================
# _update_procedural_memory
# ============================================================================


class TestUpdateProceduralMemory:
    @pytest.mark.asyncio
    async def test_records_success_with_tools(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        result = _make_result(
            success=True,
            outcome={
                "tools_used": ["email.send", "crm.update"],
                "tool_results": [
                    {"tool": "email.send", "success": True},
                    {"tool": "crm.update", "success": True},
                ],
                "intention_description": "Send follow-up email",
            },
        )
        await mixin._update_procedural_memory(result)
        call_kwargs = mixin.memory.procedural.record_procedure.call_args.kwargs
        assert call_kwargs["procedure_type"] == "intention_execution"
        assert call_kwargs["success"] is True
        assert len(call_kwargs["steps"]) == 2

    @pytest.mark.asyncio
    async def test_records_success_without_tool_results(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        result = _make_result(
            success=True,
            outcome={"tools_used": ["email.send"]},
        )
        await mixin._update_procedural_memory(result)
        call_kwargs = mixin.memory.procedural.record_procedure.call_args.kwargs
        assert call_kwargs["steps"] == [{"action": "email.send", "success": True}]

    @pytest.mark.asyncio
    async def test_records_failure(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        result = _make_result(
            success=False,
            outcome={"error": "API timeout"},
        )
        await mixin._update_procedural_memory(result)
        call_kwargs = mixin.memory.procedural.record_procedure.call_args.kwargs
        assert call_kwargs["procedure_type"] == "intention_failure"
        assert call_kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_no_procedural_no_error(self):
        mixin = _make_reflection_mixin()
        result = _make_result(success=True, outcome={"tools_used": ["x"]})
        await mixin._update_procedural_memory(result)

    @pytest.mark.asyncio
    async def test_procedural_failure_handled(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        mixin.memory.procedural.record_procedure = AsyncMock(side_effect=RuntimeError("DB"))
        result = _make_result(success=True, outcome={"tools_used": ["x"]})
        # Should not raise
        await mixin._update_procedural_memory(result)

    @pytest.mark.asyncio
    async def test_success_without_tools_not_recorded(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        result = _make_result(success=True, outcome={})
        await mixin._update_procedural_memory(result)
        mixin.memory.procedural.record_procedure.assert_not_called()


# ============================================================================
# _build_procedure_trigger_conditions
# ============================================================================


class TestBuildProcedureTriggerConditions:
    @pytest.mark.asyncio
    async def test_with_goal_id(self):
        mixin = _make_reflection_mixin()
        goal_id = uuid4()
        goal = Mock(goal_type="maintain", description="Pipeline coverage")
        mixin.goals.get_goal = AsyncMock(return_value=goal)

        conditions = await mixin._build_procedure_trigger_conditions({"goal_id": str(goal_id)})
        assert conditions["goal_type"] == "maintain"
        assert conditions["goal_description"] == "Pipeline coverage"

    @pytest.mark.asyncio
    async def test_without_goal_id(self):
        mixin = _make_reflection_mixin()
        conditions = await mixin._build_procedure_trigger_conditions({})
        assert conditions == {}

    @pytest.mark.asyncio
    async def test_goal_lookup_failure(self):
        mixin = _make_reflection_mixin()
        mixin.goals.get_goal = AsyncMock(side_effect=RuntimeError("DB"))
        conditions = await mixin._build_procedure_trigger_conditions({"goal_id": str(uuid4())})
        assert conditions == {}


# ============================================================================
# _update_effectiveness_beliefs
# ============================================================================


class TestUpdateEffectivenessBeliefs:
    @pytest.mark.asyncio
    async def test_updates_beliefs_for_tool_results(self):
        mixin = _make_reflection_mixin()
        result = _make_result(
            success=True,
            outcome={
                "tool_results": [
                    {"tool": "email.send", "success": True},
                    {"tool": "crm.update", "success": False},
                ]
            },
        )
        await mixin._update_effectiveness_beliefs(result)
        assert mixin.beliefs.update_belief.call_count == 2

        # Check first call (success)
        call0 = mixin.beliefs.update_belief.call_args_list[0].kwargs
        assert call0["subject"] == "email.send"
        assert call0["confidence"] == 0.8

        # Check second call (failure)
        call1 = mixin.beliefs.update_belief.call_args_list[1].kwargs
        assert call1["subject"] == "crm.update"
        assert call1["confidence"] == 0.3

    @pytest.mark.asyncio
    async def test_no_tool_results_skips(self):
        mixin = _make_reflection_mixin()
        result = _make_result(outcome={})
        await mixin._update_effectiveness_beliefs(result)
        mixin.beliefs.update_belief.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_tool_name_skipped(self):
        mixin = _make_reflection_mixin()
        result = _make_result(outcome={"tool_results": [{"tool": "", "success": True}]})
        await mixin._update_effectiveness_beliefs(result)
        mixin.beliefs.update_belief.assert_not_called()

    @pytest.mark.asyncio
    async def test_belief_update_failure_handled(self):
        mixin = _make_reflection_mixin()
        mixin.beliefs.update_belief = AsyncMock(side_effect=RuntimeError("DB"))
        result = _make_result(outcome={"tool_results": [{"tool": "x", "success": True}]})
        # Should not raise
        await mixin._update_effectiveness_beliefs(result)


# ============================================================================
# deep_reflection_cycle
# ============================================================================


class TestDeepReflectionCycle:
    @pytest.mark.asyncio
    async def test_no_episodes_returns_early(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        mixin.memory.episodic.recall_recent = AsyncMock(return_value=[])

        await mixin.deep_reflection_cycle()
        assert mixin.last_deep_reflection is not None
        # update_belief should NOT be called (no episodes)
        mixin.beliefs.update_belief.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_episodes_updates_beliefs(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        ep1 = Mock(
            id=uuid4(),
            episode_type="intention_execution",
            description="exec 1",
            content={"success": True},
            importance=0.7,
            occurred_at=datetime.now(UTC),
        )
        ep2 = Mock(
            id=uuid4(),
            episode_type="intention_execution",
            description="exec 2",
            content={"success": False},
            importance=0.8,
            occurred_at=datetime.now(UTC),
        )
        mixin.memory.episodic.recall_recent = AsyncMock(return_value=[ep1, ep2])

        await mixin.deep_reflection_cycle()
        # Should update recent_success_rate belief
        mixin.beliefs.update_belief.assert_called()
        call_kwargs = mixin.beliefs.update_belief.call_args_list[0].kwargs
        assert call_kwargs["predicate"] == "recent_success_rate"
        assert call_kwargs["belief_object"]["value"] == 0.5  # 1/2

    @pytest.mark.asyncio
    async def test_with_llm_and_enough_episodes(self):
        llm = Mock()
        response = Mock(content="Pattern: failures due to timeouts. Improve batching.")
        llm.generate = AsyncMock(return_value=response)
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True)

        episodes = []
        for i in range(5):
            ep = Mock(
                id=uuid4(),
                episode_type="intention_execution",
                description=f"exec {i}",
                content={"success": i % 2 == 0},
                importance=0.7,
                occurred_at=datetime.now(UTC),
            )
            episodes.append(ep)
        mixin.memory.episodic.recall_recent = AsyncMock(return_value=episodes)

        await mixin.deep_reflection_cycle()
        llm.generate.assert_called_once()
        # Should record reflection episode
        assert mixin.memory.episodic.record_episode.call_count >= 1

    @pytest.mark.asyncio
    async def test_skips_llm_with_fewer_than_3_episodes(self):
        llm = Mock()
        llm.generate = AsyncMock()
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True)

        ep = Mock(
            id=uuid4(),
            episode_type="intention_execution",
            description="exec 1",
            content={"success": True},
            importance=0.7,
            occurred_at=datetime.now(UTC),
        )
        mixin.memory.episodic.recall_recent = AsyncMock(return_value=[ep])

        await mixin.deep_reflection_cycle()
        llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        mixin.memory.episodic.recall_recent = AsyncMock(side_effect=RuntimeError("DB"))
        # Should not raise
        await mixin.deep_reflection_cycle()
        assert mixin.last_deep_reflection is not None


# ============================================================================
# _get_recent_episodes
# ============================================================================


class TestGetRecentEpisodes:
    @pytest.mark.asyncio
    async def test_returns_episodes(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        ep = Mock(
            id=uuid4(),
            episode_type="intention_execution",
            description="test",
            content={"success": True},
            importance=0.7,
            occurred_at=datetime.now(UTC),
        )
        mixin.memory.episodic.recall_recent = AsyncMock(return_value=[ep])

        result = await mixin._get_recent_episodes(days=1)
        assert len(result) == 1
        assert result[0]["type"] == "intention_execution"

    @pytest.mark.asyncio
    async def test_no_episodic_returns_empty(self):
        mixin = _make_reflection_mixin()
        result = await mixin._get_recent_episodes()
        assert result == []

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        mixin.memory.episodic.recall_recent = AsyncMock(side_effect=RuntimeError("DB"))
        result = await mixin._get_recent_episodes()
        assert result == []


# ============================================================================
# _analyze_patterns_with_llm
# ============================================================================


class TestAnalyzePatternsWithLLM:
    @pytest.mark.asyncio
    async def test_no_llm_returns(self):
        mixin = _make_reflection_mixin(llm=None, has_episodic=True)
        await mixin._analyze_patterns_with_llm([], 0.5)
        mixin.memory.episodic.record_episode.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_analysis_in_episodic(self):
        llm = Mock()
        response = Mock(content="Analysis: things work well")
        llm.generate = AsyncMock(return_value=response)
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True)

        episodes = [{"description": "exec 1", "content": {"success": True}}]
        await mixin._analyze_patterns_with_llm(episodes, 0.8)
        mixin.memory.episodic.record_episode.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_insight_in_semantic(self):
        llm = Mock()
        response = Mock(content="Insight about patterns")
        llm.generate = AsyncMock(return_value=response)
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True, has_semantic=True)

        episodes = [{"description": "exec 1", "content": {"success": True}}]
        await mixin._analyze_patterns_with_llm(episodes, 0.8)
        mixin.memory.semantic.store_fact.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_store_failure_handled(self):
        llm = Mock()
        response = Mock(content="Insight")
        llm.generate = AsyncMock(return_value=response)
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True, has_semantic=True)
        mixin.memory.semantic.store_fact = AsyncMock(side_effect=RuntimeError("DB"))

        episodes = [{"description": "exec 1", "content": {"success": True}}]
        # Should not raise
        await mixin._analyze_patterns_with_llm(episodes, 0.5)

    @pytest.mark.asyncio
    async def test_llm_failure_handled(self):
        llm = Mock()
        llm.generate = AsyncMock(side_effect=RuntimeError("API error"))
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True)

        episodes = [{"description": "exec 1", "content": {"success": True}}]
        # Should not raise
        await mixin._analyze_patterns_with_llm(episodes, 0.5)

    @pytest.mark.asyncio
    async def test_uses_identity_prompt(self):
        llm = Mock()
        response = Mock(content="Analysis")
        llm.generate = AsyncMock(return_value=response)
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True)
        mixin._identity_prompt = "You are a CSM."

        episodes = [{"description": "exec 1", "content": {"success": True}}]
        await mixin._analyze_patterns_with_llm(episodes, 0.5)
        call_kwargs = llm.generate.call_args.kwargs
        assert "CSM" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_no_identity_prompt_uses_default(self):
        llm = Mock()
        response = Mock(content="Analysis")
        llm.generate = AsyncMock(return_value=response)
        mixin = _make_reflection_mixin(llm=llm, has_episodic=True)
        mixin._identity_prompt = None

        episodes = [{"description": "exec 1", "content": {"success": True}}]
        await mixin._analyze_patterns_with_llm(episodes, 0.5)
        call_kwargs = llm.generate.call_args.kwargs
        assert "digital employee" in call_kwargs["system"]


# ============================================================================
# _maintain_memory_health
# ============================================================================


class TestMaintainMemoryHealth:
    @pytest.mark.asyncio
    async def test_episodic_maintenance(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        await mixin._maintain_memory_health()
        mixin.memory.episodic.reinforce_frequently_recalled.assert_called_once()
        mixin.memory.episodic.decay_rarely_recalled.assert_called_once()

    @pytest.mark.asyncio
    async def test_procedural_maintenance(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        await mixin._maintain_memory_health()
        mixin.memory.procedural.reinforce_successful_procedures.assert_called_once()
        mixin.memory.procedural.archive_poor_procedures.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_memory_systems(self):
        mixin = _make_reflection_mixin()
        # Should not raise
        await mixin._maintain_memory_health()

    @pytest.mark.asyncio
    async def test_episodic_failure_handled(self):
        mixin = _make_reflection_mixin(has_episodic=True)
        mixin.memory.episodic.reinforce_frequently_recalled = AsyncMock(
            side_effect=RuntimeError("DB")
        )
        # Should not raise
        await mixin._maintain_memory_health()

    @pytest.mark.asyncio
    async def test_procedural_reinforce_failure_handled(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        mixin.memory.procedural.reinforce_successful_procedures = AsyncMock(
            side_effect=RuntimeError("DB")
        )
        # Should not raise — archive_poor_procedures should still be attempted
        await mixin._maintain_memory_health()
        mixin.memory.procedural.archive_poor_procedures.assert_called_once()

    @pytest.mark.asyncio
    async def test_procedural_archive_failure_handled(self):
        mixin = _make_reflection_mixin(has_procedural=True)
        mixin.memory.procedural.archive_poor_procedures = AsyncMock(side_effect=RuntimeError("DB"))
        # Should not raise
        await mixin._maintain_memory_health()
