"""
empla.core.loop.goal_management - Goal Progress Evaluation and Achievement

Mixin providing goal progress evaluation (including LLM-driven analysis)
and achievement/completion logic for the proactive execution loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, cast

from empla.core.hooks import HOOK_GOAL_ACHIEVED
from empla.core.loop.models import GoalProgressEvaluation, NonNumericGoalBatchEvaluation
from empla.core.loop.protocols import BeliefChange

logger = logging.getLogger(__name__)


class GoalManagementMixin:
    """Mixin for goal progress evaluation and achievement management.

    Expects the host class to provide:
        self.employee   - The digital employee instance
        self.goals      - GoalSystem for managing goals
        self.llm_service - LLM service for structured generation
        self.config     - Loop configuration
        self._hooks     - HookRegistry for lifecycle events
    """

    async def _evaluate_goals_progress(
        self,
        goals: list[Any],
        changed_beliefs: list[BeliefChange],
    ) -> dict[str, dict[str, Any]]:
        """Evaluate progress for all pursuing goals using LLM-driven analysis.

        Batches all goals into a single LLM call that interprets changed beliefs
        in context. Returns empty if LLM is unavailable (will retry next cycle).

        Args:
            goals: All pursuing goals (filtered internally to those with numeric targets).
            changed_beliefs: Belief changes from this cycle.

        Returns:
            Dict mapping goal_id (str) to progress dict.
        """
        if not changed_beliefs or not goals:
            return {}

        # Check for expired opportunity/problem goals (TTL)
        now = datetime.now(UTC)
        for goal in goals:
            target = getattr(goal, "target", {}) or {}
            max_age_hours = target.get("max_age_hours")
            if max_age_hours:
                created = getattr(goal, "created_at", None)
                if created and (now - created).total_seconds() > max_age_hours * 3600:
                    try:
                        await self.goals.abandon_goal(goal.id)
                        logger.info(
                            "Abandoned expired goal: %s (age > %dh)",
                            getattr(goal, "description", "")[:50],
                            max_age_hours,
                            extra={"employee_id": str(self.employee.id)},
                        )
                    except Exception:
                        logger.warning(
                            "Failed to abandon expired goal",
                            exc_info=True,
                            extra={"employee_id": str(self.employee.id)},
                        )

        # LLM completion check for opportunity/problem goals (no numeric target)
        await self._evaluate_non_numeric_goals(goals, changed_beliefs)

        # Filter to goals with numeric target metrics
        evaluable_goals = []
        for goal in goals:
            target = getattr(goal, "target", {}) or {}
            if target.get("metric") and target.get("value") is not None:
                evaluable_goals.append(goal)

        if not evaluable_goals:
            return {}

        # Format belief changes as text for the LLM
        belief_lines = []
        for bc in changed_beliefs:
            belief = getattr(bc, "belief", None)
            obj = getattr(belief, "object", {}) if belief else {}
            belief_lines.append(
                f"- {bc.subject} → {bc.predicate}: {obj} "
                f"(confidence: {bc.old_confidence:.2f} → {bc.new_confidence:.2f})"
            )
        beliefs_text = "\n".join(belief_lines) if belief_lines else "No belief changes"

        # Format goals for the LLM
        goal_lines = []
        for g in evaluable_goals:
            target = getattr(g, "target", {}) or {}
            goal_lines.append(
                f"- goal_id={g.id}, metric={target['metric']}, "
                f"target_value={target['value']}, description={getattr(g, 'description', '')}"
            )
        goals_text = "\n".join(goal_lines)

        if self.llm_service is None:
            logger.error(
                "LLM service unavailable, cannot evaluate goal progress (will retry next cycle)",
                extra={"employee_id": str(self.employee.id)},
            )
            return {}

        try:
            return await self._evaluate_goals_progress_via_llm(
                evaluable_goals, beliefs_text, goals_text
            )
        except Exception as e:
            logger.error(
                "LLM goal evaluation failed (will retry next cycle): %s",
                e,
                exc_info=True,
                extra={"employee_id": str(self.employee.id)},
            )
            return {}

    async def _evaluate_goals_progress_via_llm(
        self,
        goals: list[Any],
        beliefs_text: str,
        goals_text: str,
    ) -> dict[str, dict[str, Any]]:
        """Call LLM to evaluate goal progress from belief changes.

        Args:
            goals: Goals being evaluated.
            beliefs_text: Formatted belief changes text.
            goals_text: Formatted goals text.

        Returns:
            Dict mapping goal_id (str) to progress dict.
        """
        system_prompt = (
            "You are evaluating whether recent belief changes indicate progress "
            "toward specific goals. For each goal, determine the current metric "
            "value from the beliefs if possible. Only report a value when the "
            "beliefs clearly contain information about the goal's metric."
        )

        prompt = f"""Recent belief changes:
{beliefs_text}

Goals to evaluate:
{goals_text}

For each goal, extract the current metric value from the belief changes if present.
Only include goals where you can determine a numeric value."""

        _, evaluation = await self.llm_service.generate_structured(
            prompt=prompt,
            system=system_prompt,
            response_format=GoalProgressEvaluation,
            temperature=0.1,
        )
        evaluation = cast(GoalProgressEvaluation, evaluation)

        # Validate and convert to progress dicts
        valid_goals = {str(g.id): (getattr(g, "target", {}) or {}).get("metric", "") for g in goals}
        min_confidence = 0.3
        result: dict[str, dict[str, Any]] = {}
        for metric_result in evaluation.results:
            if metric_result.current_value is None:
                continue
            if metric_result.confidence < min_confidence:
                logger.debug(
                    "LLM goal evaluation below confidence threshold (%.2f < %.2f) for goal %s, skipping",
                    metric_result.confidence,
                    min_confidence,
                    metric_result.goal_id,
                    extra={"employee_id": str(self.employee.id)},
                )
                continue
            if metric_result.goal_id not in valid_goals:
                logger.warning(
                    "LLM returned unknown goal_id %r, skipping",
                    metric_result.goal_id,
                    extra={"employee_id": str(self.employee.id)},
                )
                continue
            expected_metric = valid_goals[metric_result.goal_id]
            if metric_result.metric != expected_metric:
                logger.warning(
                    "LLM returned metric %r for goal %s, expected %r, skipping",
                    metric_result.metric,
                    metric_result.goal_id,
                    expected_metric,
                    extra={"employee_id": str(self.employee.id)},
                )
                continue
            result[metric_result.goal_id] = {
                metric_result.metric: metric_result.current_value,
                "llm_confidence": metric_result.confidence,
                "llm_reasoning": metric_result.reasoning,
            }

        logger.debug(
            "LLM goal evaluation: %d/%d goals with progress",
            len(result),
            len(goals),
            extra={"employee_id": str(self.employee.id)},
        )
        return result

    async def _evaluate_non_numeric_goals(
        self,
        goals: list[Any],
        changed_beliefs: list[BeliefChange],
    ) -> None:
        """Evaluate whether non-numeric goals (opportunity/problem) are complete.

        Opportunity and problem goals don't have numeric targets, so TTL is
        the primary expiry mechanism. This adds an LLM-based check: ask whether
        the goal has been effectively addressed based on recent belief changes.

        Goals that the LLM confidently marks as complete are achieved; others continue.
        Falls back to TTL-only when LLM is unavailable.
        """
        if not self.llm_service or not changed_beliefs:
            return

        # Filter to non-numeric opportunity/problem goals
        non_numeric = []
        for goal in goals:
            goal_type = getattr(goal, "goal_type", "")
            target = getattr(goal, "target", {}) or {}
            if goal_type in ("opportunity", "problem") and not target.get("metric"):
                non_numeric.append(goal)

        if not non_numeric:
            return

        # Format for LLM
        belief_lines = []
        for bc in changed_beliefs[:15]:
            belief = getattr(bc, "belief", None)
            obj = getattr(belief, "object", {}) if belief else {}
            belief_lines.append(
                f"- {bc.subject} → {bc.predicate}: {obj} "
                f"(confidence: {bc.old_confidence:.2f} → {bc.new_confidence:.2f})"
            )
        beliefs_text = "\n".join(belief_lines) if belief_lines else "No belief changes"

        sent_goals = non_numeric[:5]
        goal_lines = []
        for g in sent_goals:
            goal_lines.append(
                f"- goal_id={g.id}, type={getattr(g, 'goal_type', '')}, "
                f"description={getattr(g, 'description', '')}"
            )
        goals_text = "\n".join(goal_lines)

        try:
            _, evaluation = await self.llm_service.generate_structured(
                prompt=(
                    f"Recent belief changes:\n{beliefs_text}\n\n"
                    f"Goals to evaluate for completion:\n{goals_text}\n\n"
                    "For each goal, determine whether it has been effectively "
                    "addressed or resolved based on the belief changes. "
                    "Be conservative — only mark as complete when clearly resolved."
                ),
                system=(
                    "You are evaluating whether opportunity/problem goals have "
                    "been effectively addressed. These goals don't have numeric targets, "
                    "so assess qualitatively from the belief changes."
                ),
                response_format=NonNumericGoalBatchEvaluation,
                temperature=0.1,
            )
            evaluation = cast(NonNumericGoalBatchEvaluation, evaluation)
        except Exception as e:
            logger.warning(
                "LLM non-numeric goal evaluation failed (TTL-only fallback): %s",
                e,
                extra={"employee_id": str(self.employee.id)},
            )
            return

        # Process results
        valid_ids = {str(g.id) for g in sent_goals}
        for result in evaluation.results:
            if result.goal_id not in valid_ids:
                continue
            if result.is_complete and result.confidence >= 0.7:
                try:
                    from uuid import UUID

                    goal_uuid = UUID(result.goal_id)
                    await self.goals.complete_goal(goal_uuid)
                    logger.info(
                        "Completed non-numeric goal per LLM evaluation: %s (confidence=%.2f)",
                        result.reasoning[:60],
                        result.confidence,
                        extra={"employee_id": str(self.employee.id)},
                    )

                    # Emit achievement hook
                    matched = [g for g in non_numeric if str(g.id) == result.goal_id]
                    if matched and hasattr(self, "_hooks"):
                        await self._hooks.emit(
                            HOOK_GOAL_ACHIEVED,
                            {
                                "goal_id": result.goal_id,
                                "description": getattr(matched[0], "description", ""),
                                "reasoning": result.reasoning,
                            },
                        )
                except Exception:
                    logger.warning(
                        "Failed to complete non-numeric goal %s",
                        result.goal_id,
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )

    async def _check_goal_achievement(
        self,
        goal: Any,
        progress: dict[str, Any],
    ) -> None:
        """
        Check if a goal's target has been met and complete it if so.

        For "maintain" goals (ongoing targets), the goal stays active.
        For achievement goals, calls complete_goal() with retry logic.
        If retries are exhausted, marks the goal as completion_pending
        so subsequent cycles will reattempt completion.

        Args:
            goal: The goal to check
            progress: The newly updated progress data
        """
        target = getattr(goal, "target", {}) or {}
        metric = target.get("metric", "")
        target_value = target.get("value")

        if not metric or target_value is None:
            return

        current_value = progress.get(metric)
        if current_value is None:
            return

        try:
            achieved = float(current_value) >= float(target_value)
        except (ValueError, TypeError):
            logger.warning(
                "Non-numeric goal target or progress: metric=%s current=%r target=%r",
                metric,
                current_value,
                target_value,
                extra={"employee_id": str(self.employee.id), "goal_id": str(goal.id)},
            )
            return

        if not achieved:
            return

        goal_type = getattr(goal, "goal_type", "")

        if goal_type in ("maintain", "maintenance"):
            # Ongoing goals stay active — log that target is met
            logger.info(
                "Maintain goal target met: %s=%s (target=%s)",
                metric,
                current_value,
                target_value,
                extra={
                    "employee_id": str(self.employee.id),
                    "goal_id": str(goal.id),
                    "goal_type": goal_type,
                },
            )
            return

        # Achievement/one-time goals — mark completed with retry
        await self._complete_goal_with_retry(goal, progress, metric, current_value, target_value)

    async def _complete_goal_with_retry(
        self,
        goal: Any,
        progress: dict[str, Any],
        metric: str,
        current_value: Any,
        target_value: Any,
        max_attempts: int = 3,
    ) -> None:
        """Complete an achievement goal with retry and completion_pending fallback.

        Args:
            goal: The goal to complete
            progress: Progress data to pass to complete_goal
            metric: The metric name (for logging)
            current_value: Current metric value (for logging)
            target_value: Target metric value (for logging)
            max_attempts: Maximum retry attempts with exponential backoff
        """
        # Strip internal flag before persisting final progress
        clean_progress = {k: v for k, v in progress.items() if k != "_completion_pending"}

        for attempt in range(max_attempts):
            try:
                await self.goals.complete_goal(goal.id, clean_progress)
            except Exception as e:
                if attempt < max_attempts - 1:
                    delay = 0.1 * (2**attempt)  # 0.1s, 0.2s, 0.4s
                    logger.warning(
                        "Retrying goal completion (attempt %d/%d) for %s: %s",
                        attempt + 1,
                        max_attempts,
                        goal.id,
                        e,
                        extra={"employee_id": str(self.employee.id), "goal_id": str(goal.id)},
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Goal completion failed after %d attempts for %s: %s — marking completion_pending",
                        max_attempts,
                        goal.id,
                        e,
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id), "goal_id": str(goal.id)},
                    )
                    # Mark as completion_pending so subsequent cycles reattempt
                    try:
                        await self.goals.update_goal_progress(
                            goal.id, {"_completion_pending": True}
                        )
                    except Exception as fallback_err:
                        logger.error(
                            "Failed to mark goal %s as completion_pending "
                            "after completion failure: %s",
                            goal.id,
                            fallback_err,
                            exc_info=True,
                            extra={
                                "employee_id": str(self.employee.id),
                                "goal_id": str(goal.id),
                            },
                        )
            else:
                # complete_goal succeeded — log and emit hook outside retry scope
                logger.info(
                    "Goal completed: %s (metric %s=%s reached target %s)",
                    goal.description,
                    metric,
                    current_value,
                    target_value,
                    extra={
                        "employee_id": str(self.employee.id),
                        "goal_id": str(goal.id),
                    },
                )
                await self._hooks.emit(
                    HOOK_GOAL_ACHIEVED,
                    employee_id=self.employee.id,
                    goal_id=goal.id,
                    goal_description=getattr(goal, "description", ""),
                    metric=metric,
                    current_value=current_value,
                    target_value=target_value,
                    goal_type=getattr(goal, "goal_type", ""),
                )
                break
