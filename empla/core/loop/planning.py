"""
empla.core.loop.planning - Strategic Planning Mixin

Provides strategic planning capabilities for the proactive execution loop.
Extracted from ProactiveExecutionLoop to separate strategic reasoning concerns
(situation analysis, goal management, plan generation) from the core loop machinery.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, cast

from empla.core.loop.protocols import SituationAnalysis

logger = logging.getLogger(__name__)


class PlanningMixin:
    """Mixin providing strategic planning methods for ProactiveExecutionLoop.

    Expects the host class to provide:
        self.employee, self.beliefs, self.goals, self.intentions,
        self.memory, self.llm_service, self.tool_router, self.config,
        self._identity_prompt, self._identity, self._refresh_identity_prompt,
        self.last_strategic_planning
    """

    def should_run_strategic_planning(self, changed_beliefs: list[Any]) -> bool:
        """
        Decide if belief changes warrant strategic replanning.

        Strategic planning is expensive (multiple LLM calls), so only run when:
        1. High-importance belief changed significantly
        2. Belief related to current intentions changed
        3. Belief about goal achievability changed
        4. Scheduled time for strategic planning

        Args:
            changed_beliefs: List of belief changes from this cycle

        Returns:
            True if strategic planning should run, False otherwise
        """
        # 1. Check if scheduled time for strategic planning
        if self.last_strategic_planning is None:
            # Never run strategic planning - do it now
            return True

        hours_since_last_planning = (
            datetime.now(UTC) - self.last_strategic_planning
        ).total_seconds() / 3600

        if hours_since_last_planning >= self.config.strategic_planning_interval_hours:
            logger.info(
                "Triggering strategic planning: scheduled interval reached",
                extra={
                    "employee_id": str(self.employee.id),
                    "hours_since_last": hours_since_last_planning,
                },
            )
            return True

        # 2. Check if significant belief changes
        if self.config.force_strategic_planning_on_significant_change:
            # High-importance belief changed significantly
            important_changed = any(
                b.importance > 0.7 and abs(b.new_confidence - b.old_confidence) > 0.3
                for b in changed_beliefs
            )

            if important_changed:
                logger.info(
                    "Triggering strategic planning: significant belief change",
                    extra={"employee_id": str(self.employee.id)},
                )
                return True

            # Belief about goal achievability changed
            goal_beliefs_changed = any(
                b.predicate in ["achievable", "blocked", "deadline", "priority"]
                for b in changed_beliefs
            )

            if goal_beliefs_changed:
                logger.info(
                    "Triggering strategic planning: goal-related belief changed",
                    extra={"employee_id": str(self.employee.id)},
                )
                return True

        return False

    async def strategic_planning_cycle(self) -> None:
        """
        Deep strategic reasoning cycle.

        This is computationally expensive (multiple LLM calls) and runs less
        frequently than tactical execution.

        Performs:
        1. Comprehensive situation analysis
        2. Gap analysis (current vs desired state)
        3. Root cause analysis
        4. Opportunity detection
        5. Strategy generation and evaluation
        6. Goal formation/abandonment
        7. Strategy documentation
        """
        logger.info(
            "Strategic planning cycle starting",
            extra={"employee_id": str(self.employee.id)},
        )

        start_time = time.time()

        try:
            # ============ STEP 1: Gather Situation ============
            # Get current beliefs, goals, and capabilities
            beliefs = await self.beliefs.get_all_beliefs(min_confidence=0.5)
            active_goals = await self.goals.get_active_goals()
            available_capabilities = self._get_available_capabilities()

            logger.debug(
                "Strategic planning: gathered situation",
                extra={
                    "employee_id": str(self.employee.id),
                    "beliefs_count": len(beliefs),
                    "active_goals_count": len(active_goals),
                    "capabilities_count": len(available_capabilities),
                },
            )

            # ============ STEP 2: LLM Situation Analysis ============
            if self.llm_service:
                situation_analysis = await self._analyze_situation_with_llm(
                    beliefs=beliefs,
                    goals=active_goals,
                    capabilities=available_capabilities,
                )

                logger.info(
                    "Strategic planning: situation analyzed",
                    extra={
                        "employee_id": str(self.employee.id),
                        "gaps_identified": len(situation_analysis.gaps),
                        "opportunities_identified": len(situation_analysis.opportunities),
                        "problems_identified": len(situation_analysis.problems),
                        "recommended_focus": situation_analysis.recommended_focus,
                    },
                )

                # ============ STEP 3: Goal Management ============
                await self._manage_goals_from_analysis(
                    situation_analysis=situation_analysis,
                    active_goals=active_goals,
                )
                # Goals changed — refresh identity prompt so subsequent LLM calls
                # reflect the current goal set.
                await self._refresh_identity_prompt()

            # ============ STEP 4: Generate Plans for Goals Without Intentions ============
            await self._generate_plans_for_unplanned_goals(
                goals=active_goals,
                beliefs=beliefs,
                capabilities=available_capabilities,
            )

            # ============ STEP 5: Document in Episodic Memory ============
            await self._record_strategic_planning_episode(
                beliefs_count=len(beliefs),
                goals_count=len(active_goals),
            )

        except Exception as e:
            logger.error(
                "Strategic planning cycle failed",
                exc_info=True,
                extra={"employee_id": str(self.employee.id), "error": str(e)},
            )

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Strategic planning cycle complete",
            extra={"employee_id": str(self.employee.id), "duration_ms": duration_ms},
        )

        # Update last strategic planning time
        self.last_strategic_planning = datetime.now(UTC)

    def _get_available_capabilities(self) -> list[str]:
        """Get list of available capability/integration names."""
        if not self.tool_router:
            return []

        try:
            return self.tool_router.get_enabled_capabilities(self.employee.id)
        except Exception as e:
            logger.warning(
                f"Failed to get capabilities: {e}", extra={"employee_id": str(self.employee.id)}
            )
            return []

    async def _analyze_situation_with_llm(
        self,
        beliefs: list[Any],
        goals: list[Any],
        capabilities: list[str],
    ) -> SituationAnalysis:
        """Use LLM to analyze current situation."""
        if not self.llm_service:
            return SituationAnalysis(
                current_state_summary="No LLM service available",
                gaps=[],
                opportunities=[],
                problems=[],
                recommended_focus="Continue with current goals",
            )

        # Format beliefs for prompt
        beliefs_text = self._format_beliefs_for_llm(beliefs)
        goals_text = self._format_goals_for_llm(goals)

        base_prompt = """Analyze your current beliefs (world model) and goals to identify:
1. Gaps between current state and desired outcomes
2. Opportunities that could be pursued
3. Problems requiring immediate attention
4. What you should focus on next

IMPORTANT: Do NOT suggest opportunities or problems that are already covered by existing
active goals. Review the goals list carefully — if a goal already addresses a topic,
do not duplicate it as an opportunity or problem. Only suggest genuinely new items.

Be specific and actionable in your analysis."""

        system_prompt = (
            f"{self._identity_prompt}\n\n{base_prompt}"
            if self._identity_prompt
            else f"You are a digital employee.\n\n{base_prompt}"
        )

        # Inject semantic memory (long-term entity knowledge)
        entity_context = ""
        if hasattr(self.memory, "semantic"):
            try:
                subjects = {getattr(b, "subject", "") for b in beliefs[:20]}
                entity_lines = []
                for subj in list(subjects)[:10]:
                    if not subj:
                        continue
                    facts = await self.memory.semantic.query_facts(subject=subj, limit=3)
                    for f in facts:
                        entity_lines.append(f"  {f.subject} → {f.predicate}: {f.object}")
                if entity_lines:
                    entity_context = "\n\nKnown entity facts:\n" + "\n".join(entity_lines[:20])
            except Exception:
                logger.debug(
                    "Failed to load semantic memory for strategic planning",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        # Inject latest deep reflection insight
        reflection_context = ""
        if hasattr(self.memory, "episodic"):
            try:
                reflections = await self.memory.episodic.recall_recent(
                    episode_type="deep_reflection", limit=1
                )
                if reflections:
                    reflection_context = (
                        f"\n\nRecent self-reflection:\n{reflections[0].description[:300]}"
                    )
            except Exception:
                logger.debug(
                    "Failed to load recent reflection for strategic planning",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        user_prompt = f"""Current Beliefs (World Model):
{beliefs_text}

Active Goals:
{goals_text}

Available Capabilities: {", ".join(capabilities) if capabilities else "None specified"}
{entity_context}{reflection_context}

Analyze this situation and provide recommendations."""

        try:
            _, analysis = await self.llm_service.generate_structured(
                prompt=user_prompt,
                system=system_prompt,
                response_format=SituationAnalysis,
                temperature=0.3,
            )
            return cast(SituationAnalysis, analysis)
        except Exception as e:
            logger.warning(
                f"LLM situation analysis failed: {e}",
                extra={"employee_id": str(self.employee.id)},
            )
            return SituationAnalysis(
                current_state_summary="Analysis failed",
                gaps=[],
                opportunities=[],
                problems=[],
                recommended_focus="Continue with current priorities",
            )

    def _format_beliefs_for_llm(self, beliefs: list[Any]) -> str:
        """Format beliefs for LLM prompt."""
        if not beliefs:
            return "No current beliefs"

        lines = []
        for belief in beliefs[:20]:  # Limit to top 20
            subject = getattr(belief, "subject", "unknown")
            predicate = getattr(belief, "predicate", "unknown")
            obj = getattr(belief, "object", {})
            confidence = getattr(belief, "confidence", 0.0)
            lines.append(f"- {subject} → {predicate}: {obj} (confidence: {confidence:.2f})")

        if len(beliefs) > 20:
            lines.append(f"... and {len(beliefs) - 20} more beliefs")

        return "\n".join(lines)

    def _format_goals_for_llm(self, goals: list[Any]) -> str:
        """Format goals for LLM prompt."""
        if not goals:
            return "No active goals"

        lines = []
        for goal in goals:
            description = getattr(goal, "description", "unknown")
            priority = getattr(goal, "priority", 5)
            target = getattr(goal, "target", {})
            progress = getattr(goal, "current_progress", {})
            lines.append(
                f"- [{priority}/10] {description}\n  Target: {target}\n  Progress: {progress}"
            )

        return "\n".join(lines)

    @staticmethod
    def _words_overlap(a: str, b: str) -> float:
        """Return word-level Jaccard similarity between two strings."""
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    async def _safe_rollback_goals(self) -> None:
        """Attempt to rollback the goals session after a failed flush."""
        try:
            await self.goals.rollback()
        except Exception:
            logger.error(
                "Goals session rollback also failed",
                extra={"employee_id": str(self.employee.id)},
                exc_info=True,
            )

    async def _manage_goals_from_analysis(
        self,
        situation_analysis: SituationAnalysis,
        active_goals: list[Any],
    ) -> None:
        """Create/abandon goals based on situation analysis."""
        # Create new goals for identified opportunities
        existing_descs = [getattr(g, "description", "").lower() for g in active_goals]
        for opportunity in situation_analysis.opportunities[:3]:  # Limit to top 3
            # Check if semantically similar goal already exists (bidirectional substring)
            opp_lower = opportunity.lower()
            exists = any(
                opp_lower in desc or desc in opp_lower or self._words_overlap(opp_lower, desc) > 0.6
                for desc in existing_descs
            )
            if not exists:
                try:
                    await self.goals.add_goal(
                        goal_type="opportunity",
                        description=f"Pursue opportunity: {opportunity}",
                        priority=6,  # Medium priority for opportunities
                        target={
                            "type": "opportunity",
                            "description": opportunity,
                            "max_age_hours": 72,
                        },
                    )
                    logger.info(
                        f"Created goal for opportunity: {opportunity[:50]}...",
                        extra={"employee_id": str(self.employee.id)},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to create goal for opportunity: {e}",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )
                    # A failed flush invalidates the session — rollback
                    # and stop trying to create more goals this cycle.
                    await self._safe_rollback_goals()
                    return

        # Create goals for critical problems
        for problem in situation_analysis.problems[:2]:  # Limit to top 2
            prob_lower = problem.lower()
            exists = any(
                prob_lower in desc
                or desc in prob_lower
                or self._words_overlap(prob_lower, desc) > 0.6
                for desc in existing_descs
            )
            if not exists:
                try:
                    await self.goals.add_goal(
                        goal_type="problem",
                        description=f"Address problem: {problem}",
                        priority=8,  # High priority for problems
                        target={"type": "problem", "description": problem, "max_age_hours": 48},
                    )
                    logger.info(
                        f"Created goal for problem: {problem[:50]}...",
                        extra={"employee_id": str(self.employee.id)},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to create goal for problem: {e}",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )
                    await self._safe_rollback_goals()
                    return

    async def _generate_plans_for_unplanned_goals(
        self,
        goals: list[Any],
        beliefs: list[Any],
        capabilities: list[str],
    ) -> None:
        """Generate plans for goals that don't have intentions."""
        if not self.llm_service:
            logger.warning("No LLM service, skipping plan generation")
            return

        for goal in goals[:5]:  # Limit to top 5 goals
            goal_id = getattr(goal, "id", None)
            if not goal_id:
                continue

            # Check if goal already has intentions
            try:
                existing_intentions = await self.intentions.get_intentions_for_goal(goal_id)
                if existing_intentions:
                    continue  # Already has a plan
            except Exception as e:
                logger.warning(
                    f"Failed to check existing intentions for goal {goal_id}: {e}",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )
                continue

            # Query procedural memory for relevant past experience
            past_procedures: list[Any] = []
            if hasattr(self.memory, "procedural"):
                try:
                    past_procedures = await self.memory.procedural.find_procedures_for_situation(
                        situation={
                            "goal_type": getattr(goal, "goal_type", ""),
                            "goal_description": getattr(goal, "description", ""),
                        },
                        procedure_type="intention_execution",
                        min_success_rate=0.5,
                        limit=3,
                    )
                except Exception as e:
                    logger.warning(
                        "Procedural memory query failed for goal %s: %s",
                        goal_id,
                        e,
                        extra={"employee_id": str(self.employee.id)},
                    )

            # Build procedural context for plan generation
            procedural_context = ""
            if past_procedures:
                lines = ["Past experience (successful procedures):"]
                for proc in past_procedures:
                    steps_desc = ", ".join(
                        s.get("action", "?") for s in (getattr(proc, "steps", []) or [])
                    )
                    rate = getattr(proc, "success_rate", 0) or 0
                    lines.append(f"  - {proc.name}: [{steps_desc}] (success_rate={rate:.0%})")
                procedural_context = "\n".join(lines)

            # Generate plan for this goal
            try:
                enriched_identity = self._identity_prompt
                if procedural_context and enriched_identity:
                    enriched_identity = f"{enriched_identity}\n\n{procedural_context}"
                elif procedural_context:
                    enriched_identity = procedural_context

                new_intentions = await self.intentions.generate_plan_for_goal(
                    goal=goal,
                    beliefs=beliefs,
                    llm_service=self.llm_service,
                    capabilities=capabilities,
                    identity_context=enriched_identity,
                )
                if new_intentions:
                    logger.info(
                        f"Generated {len(new_intentions)} intentions for goal",
                        extra={
                            "employee_id": str(self.employee.id),
                            "goal_id": str(goal_id),
                            "intentions_count": len(new_intentions),
                        },
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to generate plan for goal: {e}",
                    extra={"employee_id": str(self.employee.id), "goal_id": str(goal_id)},
                )

    async def _record_strategic_planning_episode(
        self,
        beliefs_count: int,
        goals_count: int,
    ) -> None:
        """Record strategic planning in episodic memory."""
        try:
            if hasattr(self.memory, "episodic"):
                await self.memory.episodic.record_episode(
                    episode_type="strategic_planning",
                    description="Completed strategic planning cycle",
                    content={
                        "beliefs_analyzed": beliefs_count,
                        "goals_analyzed": goals_count,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    importance=0.6,
                )
        except Exception as e:
            logger.warning(
                f"Failed to record strategic planning episode: {e}",
                extra={"employee_id": str(self.employee.id)},
            )
