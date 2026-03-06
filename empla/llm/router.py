"""
empla.llm.router - Rule-based LLM routing layer.

Selects the most cost-effective model for each LLM call based on 10 signals:
task type, priority, context length, tool use, structured output quality,
latency sensitivity, soft budget, retry escalation, hard budget, and circuit breaker.

All routing decisions are made in <1ms with zero LLM overhead.

Signal evaluation order
-----------------------
1.  Task type         → base tier from TASK_TYPE_TIER_DEFAULTS
2.  Priority          → priority ≥ 8 escalates to tier 2 minimum
3.  Context length    → > threshold escalates to tier 3 (long-context model)
4.  Tool use          → escalates if current tier has no tool-capable models
5.  Structured output → quality_threshold ≥ 0.9 escalates to tier 3
6.  Latency flag      → logged for observability; no tier change
7.  Soft budget       → cycle_cost ≥ 70% of soft_budget → downgrade 1 tier
8.  Retry escalation  → +1 tier per retry_count; can recover from soft-budget
9.  Clamp to [1, 4]
10. Hard budget       → absolute ceiling: forces tier 1 if cycle_cost ≥ hard_budget
                        (applied after retry so retry cannot override the hard limit)
11. Circuit breaker   → skip models with ≥ N failures in cooldown window;
                        fall through to next tier if needed
"""

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from empla.llm.models import ModelTier, RouterDecision, TaskContext, TaskType

if TYPE_CHECKING:
    from empla.llm.config import RoutingPolicy
    from empla.llm.models import TokenUsage

logger = logging.getLogger(__name__)

# Maps each TaskType to its default minimum tier.
# Separate from config.TASK_TYPE_DEFAULTS (which maps TaskType → model key string).
TASK_TYPE_TIER_DEFAULTS: dict[str, int] = {
    TaskType.BELIEF_EXTRACTION: 1,
    TaskType.REFLECTION: 1,
    TaskType.PLAN_GENERATION: 2,
    TaskType.GOAL_MANAGEMENT: 2,
    TaskType.AGENTIC_EXECUTION: 2,
    TaskType.SITUATION_ANALYSIS: 2,
    TaskType.GENERAL: 2,
}


class LLMRouter:
    """
    Rule-based router that selects a model for each LLM call.

    The router evaluates 10 signals to determine the appropriate model tier,
    then resolves to a concrete model key from the provider pool.

    Usage:
        router = LLMRouter(policy, provider_pool)
        decision = router.route(task_context)
        provider = provider_pool[decision.model_key]
    """

    def __init__(
        self,
        policy: "RoutingPolicy",
        provider_pool: dict[str, Any],  # dict[str, LLMProviderBase]
        _clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self._provider_pool = provider_pool
        self._clock = _clock

        # Budget tracking (reset per BDI cycle)
        self._cycle_cost: float = 0.0

        # Circuit breaker: model_key -> list of failure timestamps
        self._failures: dict[str, list[float]] = defaultdict(list)

        # Completion counts for observability (incremented on success or failure callback)
        self._completion_counts: dict[str, int] = defaultdict(int)
        self._success_counts: dict[str, int] = defaultdict(int)

    # =========================================================================
    # Public API
    # =========================================================================

    def route(self, context: TaskContext) -> RouterDecision:
        """
        Select the best model for the given task context.

        Evaluates all 10 routing signals (see module docstring for order)
        and returns a RouterDecision with the selected model key and metadata.

        Args:
            context: Task context describing the LLM call

        Returns:
            RouterDecision with model_key, tier, and reason string
        """
        reasons: list[str] = []

        # --- Signal 1: Task type base tier ---
        tier = TASK_TYPE_TIER_DEFAULTS.get(context.task_type, 2)
        reasons.append(f"task_type={context.task_type.value}→tier{tier}")

        # --- Signal 2: Priority ---
        if context.priority >= 8 and tier < 2:
            tier = 2
            reasons.append(f"priority={context.priority}→tier2_min")

        # --- Signal 3: Context length (long context) ---
        if context.estimated_input_tokens > self.policy.long_context_token_threshold:
            # Force a long-context model — gemini-1.5-pro is tier 3
            tier = max(tier, 3)
            reasons.append(f"tokens={context.estimated_input_tokens}→long_context")

        # --- Signal 4: Tool use required ---
        if context.requires_tool_use:
            # Escalate if the current tier has no tool-capable models
            current_candidates = ModelTier.get_tier_models(tier)
            has_tool_support = any(m in ModelTier.TOOL_CALL_PREFERRED for m in current_candidates)
            if not has_tool_support:
                tier = max(tier, 2)
                reasons.append("tool_use→tier2_min")

        # --- Signal 5: Structured output reliability ---
        if context.quality_threshold >= 0.9:
            tier = max(tier, 3)
            reasons.append(f"quality_threshold={context.quality_threshold}→tier3_min")

        # --- Signal 6: Latency sensitivity ---
        # Latency-sensitive calls stay within their tier; no escalation.
        # Logged for observability only — callers can use this for SLA analysis.
        if context.latency_sensitive:
            reasons.append("latency_sensitive")

        # --- Signal 7: Soft budget ---
        # Nudges down by 1 tier when over 70% of the soft budget.
        # Note: retry escalation (signal 8) may partially or fully recover this
        # downgrade. This is intentional — a failure is a stronger signal than cost.
        if self._cycle_cost >= self.policy.soft_budget_usd * 0.7 and tier > 1:
            tier -= 1
            reasons.append(
                f"soft_budget={self._cycle_cost:.4f}/{self.policy.soft_budget_usd}→downgrade"
            )

        # --- Signal 8: Retry escalation ---
        # Applied after soft-budget so retries can recover the soft-budget downgrade.
        # Applied BEFORE hard-budget so hard-budget acts as an absolute ceiling.
        if context.retry_count > 0:
            new_tier = min(tier + context.retry_count, 4)
            if new_tier != tier:
                reasons.append(f"retry={context.retry_count}→tier{new_tier}")
            tier = new_tier

        # Clamp to valid range before applying hard budget ceiling
        tier = max(1, min(tier, 4))

        # --- Signal 10 (final): Hard budget absolute ceiling ---
        # Applied after retry so it truly overrides everything — retry cannot
        # escalate past the hard budget limit.
        if self._cycle_cost >= self.policy.hard_budget_usd:
            tier = 1
            reasons.append(
                f"hard_budget={self._cycle_cost:.4f}/{self.policy.hard_budget_usd}→force_tier1"
            )

        # --- Signal 11: Circuit breaker + model selection ---
        model_key, tier = self._select_from_tier(tier, context, reasons)

        reason_str = ", ".join(reasons)
        logger.debug(
            "Router selected model",
            extra={
                "model_key": model_key,
                "tier": tier,
                "reason": reason_str,
                "task_type": context.task_type.value,
                "priority": context.priority,
                "retry_count": context.retry_count,
                "cycle_cost": self._cycle_cost,
            },
        )

        # Populate fallback hint (next available model above primary)
        fallback_key = self._find_fallback(model_key, tier)

        return RouterDecision(
            model_key=model_key,
            tier=tier,
            reason=reason_str,
            fallback_model_key=fallback_key,
        )

    def record_success(self, model_key: str) -> None:
        """Record a successful call for circuit breaker and observability tracking."""
        self._success_counts[model_key] += 1
        self._completion_counts[model_key] += 1

    def record_failure(self, model_key: str) -> None:
        """Record a failed call for circuit breaker tracking."""
        now = self._clock()
        self._failures[model_key].append(now)
        self._completion_counts[model_key] += 1
        # Prune old failures outside the cooldown window to bound memory usage
        cutoff = now - self.policy.circuit_breaker_cooldown_seconds
        self._failures[model_key] = [t for t in self._failures[model_key] if t >= cutoff]

    def record_cost(self, model_key: str, usage: "TokenUsage") -> None:
        """
        Update the cycle budget with the cost of a completed call.

        Args:
            model_key: Key of the model that was used
            usage: Token usage from the LLM response
        """
        from empla.llm.config import MODELS

        model_config = MODELS.get(model_key)
        if model_config:
            cost = usage.calculate_cost(model_config)
            self._cycle_cost += cost

    def reset_cycle_budget(self) -> None:
        """Reset per-cycle cost counter. Call at the start of each BDI cycle."""
        self._cycle_cost = 0.0

    def get_budget_state(self) -> dict[str, Any]:
        """Return current budget and circuit breaker state for observability."""
        now = self._clock()
        cutoff = now - self.policy.circuit_breaker_cooldown_seconds
        tripped: dict[str, int] = {}
        for key, timestamps in self._failures.items():
            recent_count = sum(1 for t in timestamps if t >= cutoff)
            if recent_count >= self.policy.circuit_breaker_failure_threshold:
                tripped[key] = recent_count
        return {
            "cycle_cost_usd": self._cycle_cost,
            "soft_budget_usd": self.policy.soft_budget_usd,
            "hard_budget_usd": self.policy.hard_budget_usd,
            "circuit_breaker_tripped": tripped,
            "completion_counts": dict(self._completion_counts),
            "success_counts": dict(self._success_counts),
        }

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _is_in_cooldown(self, model_key: str) -> bool:
        """Return True if the model's circuit breaker is currently tripped."""
        now = self._clock()
        cutoff = now - self.policy.circuit_breaker_cooldown_seconds
        recent_count = sum(1 for t in self._failures[model_key] if t >= cutoff)
        return recent_count >= self.policy.circuit_breaker_failure_threshold

    def _select_from_tier(
        self,
        tier: int,
        context: TaskContext,
        reasons: list[str],
    ) -> tuple[str, int]:
        """
        Select a concrete model from the target tier.

        Falls through to a higher tier if:
        - The preferred model is not in the provider pool (no API key)
        - The model's circuit breaker is tripped

        Within a tier, model order is adjusted to prefer:
        - LONG_CONTEXT_MODELS when estimated_input_tokens is large
        - TOOL_CALL_PREFERRED when requires_tool_use is True
        - STRUCTURED_OUTPUT_RELIABLE when requires_structured_output is True

        Returns:
            (model_key, actual_tier)
        """
        for candidate_tier in range(tier, 5):
            models: list[str] = list(ModelTier.get_tier_models(candidate_tier))

            # Prefer long-context models within tier for large inputs
            if context.estimated_input_tokens > self.policy.long_context_token_threshold:
                long_ctx = [m for m in models if m in ModelTier.LONG_CONTEXT_MODELS]
                if long_ctx:
                    models = long_ctx + [m for m in models if m not in ModelTier.LONG_CONTEXT_MODELS]

            # Prefer tool-capable models within tier
            if context.requires_tool_use:
                tool_preferred = [m for m in models if m in ModelTier.TOOL_CALL_PREFERRED]
                if tool_preferred:
                    models = tool_preferred + [
                        m for m in models if m not in ModelTier.TOOL_CALL_PREFERRED
                    ]

            # Prefer structured-output-reliable models within tier
            if context.requires_structured_output:
                struct_preferred = [m for m in models if m in ModelTier.STRUCTURED_OUTPUT_RELIABLE]
                if struct_preferred:
                    models = struct_preferred + [
                        m for m in models if m not in ModelTier.STRUCTURED_OUTPUT_RELIABLE
                    ]

            for model_key in models:
                if model_key not in self._provider_pool:
                    continue
                if self._is_in_cooldown(model_key):
                    reasons.append(f"cb_skip={model_key}")
                    continue
                if candidate_tier != tier:
                    reasons.append(f"fallthrough→tier{candidate_tier}")
                return model_key, candidate_tier

        # All models unavailable — emergency fallback to whatever is in the pool
        for fallback_tier in range(1, 5):
            for model_key in ModelTier.get_tier_models(fallback_tier):
                if model_key in self._provider_pool:
                    reasons.append(f"emergency_fallback→{model_key}")
                    return model_key, fallback_tier

        # Pool is empty — return sentinel (caller must handle this gracefully)
        reasons.append("pool_empty")
        fallback = ModelTier.TIER_1[0] if ModelTier.TIER_1 else "gemini-3-flash-preview"
        return fallback, 1

    def _find_fallback(self, primary_key: str, primary_tier: int) -> str | None:
        """
        Find the next available, non-circuit-broken model above the primary.

        This is stored as a hint in RouterDecision. The actual fallback routing
        in LLMService re-routes via route() with retry_count+1 rather than
        using this hint directly.
        """
        # Look in higher tiers first
        for tier in range(primary_tier + 1, 5):
            for model_key in ModelTier.get_tier_models(tier):
                if (
                    model_key in self._provider_pool
                    and model_key != primary_key
                    and not self._is_in_cooldown(model_key)
                ):
                    return model_key
        # Try a different model within the same tier
        for model_key in ModelTier.get_tier_models(primary_tier):
            if (
                model_key in self._provider_pool
                and model_key != primary_key
                and not self._is_in_cooldown(model_key)
            ):
                return model_key
        return None
