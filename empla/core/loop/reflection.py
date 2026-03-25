"""
empla.core.loop.reflection - Reflection and Learning Mixin

Provides reflection and learning capabilities for the proactive execution loop.
Includes post-execution reflection (episodic + procedural memory updates),
effectiveness belief tracking, and periodic deep reflection with LLM-driven
pattern analysis and memory maintenance.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from empla.core.loop.models import IntentionResult

logger = logging.getLogger(__name__)


class ReflectionMixin:
    """Mixin providing reflection and learning methods for the execution loop.

    Expects the host class to provide:
        self.employee   - Employee instance (with .id)
        self.memory     - Memory system (episodic, procedural, semantic)
        self.beliefs    - BeliefSystem
        self.goals      - GoalSystem
        self.llm_service - LLMService (optional)
        self.config     - LoopConfig
        self._identity_prompt - str identity prompt for LLM
        self.last_deep_reflection - datetime | None
    """

    # ------------------------------------------------------------------
    # Phase 4: Learning & Reflection
    # ------------------------------------------------------------------

    async def reflection_cycle(self, result: IntentionResult) -> None:
        """
        Learn from execution result.

        Updates procedural memory and beliefs based on what worked/failed.
        This is called after every intention execution.

        Args:
            result: Result of intention execution
        """
        logger.debug(
            "Reflection cycle starting",
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(result.intention_id),
                "success": result.success,
            },
        )

        try:
            # ============ STEP 1: Record in Episodic Memory ============
            await self._record_execution_episode(result)

            # ============ STEP 2: Update Procedural Memory ============
            await self._update_procedural_memory(result)

            # ============ STEP 3: Update Effectiveness Beliefs ============
            await self._update_effectiveness_beliefs(result)

            logger.debug(
                "Reflection cycle complete",
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(result.intention_id),
                },
            )

        except Exception as e:
            logger.warning(
                f"Reflection cycle error: {e}",
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(result.intention_id),
                },
            )

    async def _record_execution_episode(self, result: IntentionResult) -> None:
        """Record execution outcome in episodic memory."""
        try:
            if hasattr(self.memory, "episodic"):
                await self.memory.episodic.record_episode(
                    episode_type="intention_execution",
                    description=f"Executed intention {result.intention_id}",
                    content={
                        "intention_id": str(result.intention_id),
                        "success": result.success,
                        "outcome": result.outcome,
                        "duration_ms": result.duration_ms,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    importance=0.7
                    if result.success
                    else 0.8,  # Failures more important to remember
                )
        except Exception as e:
            logger.warning(
                f"Failed to record execution episode: {e}",
                extra={"employee_id": str(self.employee.id)},
            )

    async def _update_procedural_memory(self, result: IntentionResult) -> None:
        """Update procedural memory based on execution outcome."""
        try:
            if not hasattr(self.memory, "procedural"):
                return

            outcome = result.outcome or {}
            tools_used = outcome.get("tools_used", [])

            # Build trigger_conditions from goal context so
            # find_procedures_for_situation can match on goal_type/goal_description
            trigger_conditions = await self._build_procedure_trigger_conditions(outcome)
            intention_desc = outcome.get("intention_description", "")
            procedure_name = (
                intention_desc[:120] if intention_desc else f"intention_{result.intention_id}"
            )

            # Record procedure for successful executions
            if result.success and tools_used:
                # Prefer per-tool results for accurate success/failure per step
                tool_results = outcome.get("tool_results", [])
                if tool_results:
                    steps = [
                        {"action": tr.get("tool", "unknown"), "success": tr.get("success", True)}
                        for tr in tool_results
                    ]
                else:
                    steps = [{"action": tool, "success": True} for tool in tools_used]

                await self.memory.procedural.record_procedure(
                    procedure_type="intention_execution",
                    name=procedure_name,
                    steps=steps,
                    trigger_conditions=trigger_conditions,
                    outcome=f"success:{len(tools_used)}_tools",
                    success=True,
                    execution_time=result.duration_ms / 1000.0,
                    context={
                        "intention_id": str(result.intention_id),
                        "tool_count": len(tools_used),
                    },
                )

            # For failures, record the failure pattern to avoid
            elif not result.success:
                error = outcome.get("error", "Unknown error")

                await self.memory.procedural.record_procedure(
                    procedure_type="intention_failure",
                    name=f"failed: {procedure_name}",
                    steps=[{"action": "failed", "error": error}],
                    trigger_conditions=trigger_conditions,
                    outcome=f"failure:{error[:100]}",
                    success=False,
                    execution_time=result.duration_ms / 1000.0,
                    context={
                        "intention_id": str(result.intention_id),
                        "error": error,
                    },
                )

        except Exception as e:
            logger.warning(
                f"Failed to update procedural memory: {e}",
                extra={"employee_id": str(self.employee.id)},
            )

    async def _build_procedure_trigger_conditions(self, outcome: dict[str, Any]) -> dict[str, Any]:
        """Build trigger_conditions dict for procedural memory from outcome's goal context.

        Looks up goal_type from the goals system if a goal_id is present.
        Returns a dict with goal_type and goal_description that
        find_procedures_for_situation can match against.
        """
        conditions: dict[str, Any] = {}
        goal_id_str = outcome.get("goal_id")
        if goal_id_str:
            try:
                from uuid import UUID as _UUID

                goal = await self.goals.get_goal(_UUID(goal_id_str))
                if goal:
                    goal_type = getattr(goal, "goal_type", "")
                    goal_desc = getattr(goal, "description", "")
                    if goal_type:
                        conditions["goal_type"] = goal_type
                    if goal_desc:
                        conditions["goal_description"] = goal_desc
            except Exception as e:
                logger.warning(
                    "Failed to look up goal %s for procedure trigger conditions: %s",
                    goal_id_str,
                    e,
                    extra={"employee_id": str(self.employee.id)},
                )
        return conditions

    async def _update_effectiveness_beliefs(self, result: IntentionResult) -> None:
        """Update beliefs about per-tool effectiveness based on execution outcome."""
        try:
            outcome = result.outcome or {}
            tool_results = outcome.get("tool_results", [])

            if not tool_results:
                return

            for tr in tool_results:
                tool_name = tr.get("tool", "")
                if not tool_name:
                    continue
                tool_success = tr.get("success", False)
                confidence = 0.8 if tool_success else 0.3
                await self.beliefs.update_belief(
                    subject=tool_name,
                    predicate="effectiveness",
                    belief_object={
                        "value": 1.0 if tool_success else 0.0,
                        "last_result": tool_success,
                    },
                    confidence=confidence,
                    source="execution_outcome",
                )

        except Exception as e:
            logger.warning(
                "Failed to update effectiveness beliefs: %s",
                e,
                extra={"employee_id": str(self.employee.id)},
            )

    def should_run_deep_reflection(self) -> bool:
        """
        Decide if it's time for deep reflection.

        Deep reflection analyzes recent outcomes to identify meta-patterns
        and skill gaps. It runs less frequently (e.g., daily).

        Returns:
            True if deep reflection should run, False otherwise
        """
        if self.last_deep_reflection is None:
            # Never run deep reflection - do it now
            return True

        hours_since_last = (datetime.now(UTC) - self.last_deep_reflection).total_seconds() / 3600

        return hours_since_last >= self.config.deep_reflection_interval_hours

    async def deep_reflection_cycle(self) -> None:
        """
        Periodic deep reflection on patterns and learnings.

        Runs less frequently (e.g., daily) to identify meta-patterns across
        recent outcomes, identify skill gaps, and form learning goals.
        """
        logger.info(
            "Deep reflection cycle starting",
            extra={"employee_id": str(self.employee.id)},
        )

        start_time = time.time()

        try:
            # ============ STEP 1: Gather Recent Episodes ============
            recent_episodes = await self._get_recent_episodes(days=1)

            if not recent_episodes:
                logger.debug("No recent episodes to reflect on")
                self.last_deep_reflection = datetime.now(UTC)
                return

            # ============ STEP 2: Analyze Patterns ============
            success_count = sum(
                1 for ep in recent_episodes if ep.get("content", {}).get("success", False)
            )
            failure_count = len(recent_episodes) - success_count
            success_rate = success_count / len(recent_episodes) if recent_episodes else 0

            # ============ STEP 3: Update Beliefs About Performance ============
            await self.beliefs.update_belief(
                subject="self",
                predicate="recent_success_rate",
                belief_object={
                    "value": success_rate,
                    "successes": success_count,
                    "failures": failure_count,
                    "total_episodes": len(recent_episodes),
                },
                confidence=0.9,
                source="deep_reflection",
            )

            # ============ STEP 4: Identify Patterns with LLM ============
            if self.llm_service and len(recent_episodes) >= 3:
                await self._analyze_patterns_with_llm(recent_episodes, success_rate)

            # ============ STEP 5: Reinforce/Decay Memory ============
            await self._maintain_memory_health()

            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "Deep reflection cycle complete",
                extra={
                    "employee_id": str(self.employee.id),
                    "episodes_analyzed": len(recent_episodes),
                    "success_rate": f"{success_rate:.2%}",
                    "duration_ms": duration_ms,
                },
            )

        except Exception as e:
            logger.error(
                "Deep reflection cycle failed",
                exc_info=True,
                extra={"employee_id": str(self.employee.id), "error": str(e)},
            )

        self.last_deep_reflection = datetime.now(UTC)

    async def _get_recent_episodes(self, days: int = 1) -> list[dict[str, Any]]:
        """Get recent episodes from episodic memory."""
        try:
            if hasattr(self.memory, "episodic"):
                episodes = await self.memory.episodic.recall_recent(
                    days=days,
                    limit=100,
                    episode_type="intention_execution",
                )
                # Convert to dicts for easier processing
                return [
                    {
                        "id": str(ep.id),
                        "type": ep.episode_type,
                        "description": ep.description,
                        "content": ep.content,
                        "importance": ep.importance,
                        "occurred_at": ep.occurred_at.isoformat() if ep.occurred_at else None,
                    }
                    for ep in episodes
                ]
        except Exception as e:
            logger.warning(
                f"Failed to get recent episodes: {e}", extra={"employee_id": str(self.employee.id)}
            )
        return []

    async def _analyze_patterns_with_llm(
        self, episodes: list[dict[str, Any]], success_rate: float
    ) -> None:
        """Use LLM to identify patterns in recent execution history."""
        if not self.llm_service:
            return

        # Format episodes for prompt
        episodes_text = "\n".join(
            [
                f"- {ep.get('description', 'Unknown')}: "
                f"{'Success' if ep.get('content', {}).get('success') else 'Failed'}"
                for ep in episodes[:20]
            ]
        )

        base_prompt = """Analyze your recent execution history.
Identify patterns in what succeeded and failed. Focus on:
1. Common factors in successes
2. Common factors in failures
3. Recommended improvements"""

        system_prompt = (
            f"{self._identity_prompt}\n\n{base_prompt}"
            if self._identity_prompt
            else f"You are a digital employee.\n\n{base_prompt}"
        )

        user_prompt = f"""Recent execution history (success rate: {success_rate:.1%}):

{episodes_text}

Analyze the patterns and provide brief recommendations."""

        try:
            response = await self.llm_service.generate(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.3,
                max_tokens=500,
            )

            # Store analysis in episodic memory
            if hasattr(self.memory, "episodic"):
                await self.memory.episodic.record_episode(
                    episode_type="deep_reflection",
                    description=response.content[:300] if response.content else "Pattern analysis",
                    content={
                        "analysis": response.content,
                        "episodes_analyzed": len(episodes),
                        "success_rate": success_rate,
                    },
                    importance=0.8,
                )

            # Store insight in semantic memory for use in future strategic planning
            if hasattr(self.memory, "semantic") and response.content:
                try:
                    await self.memory.semantic.store_fact(
                        subject="self",
                        predicate="execution_patterns",
                        fact_object=response.content[:500],
                        confidence=0.7,
                        source="deep_reflection",
                        fact_type="rule",
                    )
                except Exception:
                    logger.debug(
                        "Failed to store reflection insight in semantic memory",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )

            # Convert insights into typed beliefs so planning can act on them.
            # Each insight type gets its own belief predicate to avoid collapse.
            await self._convert_insights_to_beliefs(response.content, success_rate)

        except Exception as e:
            logger.warning(
                f"LLM pattern analysis failed: {e}", extra={"employee_id": str(self.employee.id)}
            )

    async def _convert_insights_to_beliefs(self, analysis: str | None, success_rate: float) -> None:
        """Convert deep reflection insights into actionable beliefs.

        Creates typed beliefs from the LLM analysis so strategic planning
        can use them. Each insight type gets a distinct predicate to avoid
        all insights collapsing into a single belief.

        Args:
            analysis: LLM analysis text from deep reflection.
            success_rate: Recent execution success rate.
        """
        if not analysis or not analysis.strip():
            return

        # Strategy effectiveness belief — always update from success rate
        try:
            effectiveness = (
                "effective"
                if success_rate >= 0.7
                else ("struggling" if success_rate < 0.4 else "mixed")
            )
            await self.beliefs.update_belief(
                subject="self",
                predicate="strategy_effectiveness",
                belief_object={
                    "assessment": effectiveness,
                    "success_rate": round(success_rate, 3),
                    "insight": analysis[:200],
                },
                confidence=0.85,
                source="deep_reflection",
            )
        except Exception:
            logger.warning(
                "Failed to update strategy_effectiveness belief",
                exc_info=True,
                extra={"employee_id": str(self.employee.id)},
            )

        # Extract pattern-based beliefs from the analysis text.
        # Use simple heuristic: if analysis mentions failures/improvements, create beliefs.
        analysis_lower = analysis.lower()

        if any(kw in analysis_lower for kw in ["fail", "error", "problem", "issue", "wrong"]):
            try:
                await self.beliefs.update_belief(
                    subject="self",
                    predicate="known_failure_patterns",
                    belief_object={"patterns": analysis[:300], "from_reflection": True},
                    confidence=0.7,
                    source="deep_reflection",
                )
            except Exception:
                logger.warning(
                    "Failed to update known_failure_patterns belief",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        if any(kw in analysis_lower for kw in ["improv", "better", "learn", "adapt", "skill"]):
            try:
                await self.beliefs.update_belief(
                    subject="self",
                    predicate="improvement_opportunities",
                    belief_object={"opportunities": analysis[:300], "from_reflection": True},
                    confidence=0.65,
                    source="deep_reflection",
                )
            except Exception:
                logger.warning(
                    "Failed to update improvement_opportunities belief",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        # Update procedural memory with success/failure patterns
        if hasattr(self.memory, "procedural") and success_rate < 0.5:
            try:
                await self.memory.procedural.record_procedure(
                    procedure_type="reflection_adjustment",
                    name=f"Strategy adjustment: {analysis[:100]}",
                    steps=[
                        {"action": "Review failing patterns from deep reflection"},
                        {"action": "Adjust approach based on identified issues"},
                    ],
                    success=success_rate >= 0.5,
                    context={"source": "deep_reflection", "success_rate": success_rate},
                )
            except Exception:
                logger.debug(
                    "Failed to record procedural memory from reflection",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

    async def _maintain_memory_health(self) -> None:
        """Perform memory maintenance: reinforce and decay."""
        if hasattr(self.memory, "episodic"):
            try:
                reinforced = await self.memory.episodic.reinforce_frequently_recalled(
                    min_recall_count=3,
                    importance_boost=1.05,
                )
                decayed = await self.memory.episodic.decay_rarely_recalled(
                    min_days_old=30,
                    importance_decay=0.95,
                )
                logger.debug(
                    "Memory maintenance: reinforced %d, decayed %d",
                    reinforced,
                    decayed,
                    extra={"employee_id": str(self.employee.id)},
                )
            except Exception as e:
                logger.warning(
                    "Episodic memory maintenance failed: %s",
                    e,
                    extra={"employee_id": str(self.employee.id)},
                )

        if hasattr(self.memory, "procedural"):
            try:
                await self.memory.procedural.reinforce_successful_procedures(
                    min_success_rate=0.8,
                    min_executions=3,
                )
            except Exception as e:
                logger.warning(
                    "Procedural memory reinforcement failed: %s",
                    e,
                    extra={"employee_id": str(self.employee.id)},
                )
            try:
                await self.memory.procedural.archive_poor_procedures(
                    max_success_rate=0.2,
                    min_executions=3,
                )
            except Exception as e:
                logger.warning(
                    "Procedural memory archiving failed: %s",
                    e,
                    extra={"employee_id": str(self.employee.id)},
                )
