"""
Unit tests for LLMRouter.

Covers all 10 routing signals, backwards compatibility, and edge cases.
"""

from empla.llm.config import RoutingPolicy
from empla.llm.models import ModelTier, RouterDecision, TaskContext, TaskType
from empla.llm.router import LLMRouter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_MODELS_POOL: dict[str, object] = {
    key: object()
    for tier in [ModelTier.TIER_1, ModelTier.TIER_2, ModelTier.TIER_3, ModelTier.TIER_4]
    for key in tier
}


def make_router(
    pool: dict | None = None,
    soft_budget: float = 0.10,
    hard_budget: float = 0.50,
    long_ctx_threshold: int = 50_000,
    cb_threshold: int = 3,
    cb_cooldown: int = 120,
    clock: object = None,
) -> LLMRouter:
    policy = RoutingPolicy(
        enabled=True,
        soft_budget_usd=soft_budget,
        hard_budget_usd=hard_budget,
        long_context_token_threshold=long_ctx_threshold,
        circuit_breaker_failure_threshold=cb_threshold,
        circuit_breaker_cooldown_seconds=cb_cooldown,
    )
    kwargs: dict = {"policy": policy, "provider_pool": pool if pool is not None else ALL_MODELS_POOL}
    if clock is not None:
        kwargs["_clock"] = clock
    return LLMRouter(**kwargs)


# ---------------------------------------------------------------------------
# Signal 1: Task type base tier
# ---------------------------------------------------------------------------


def test_belief_extraction_routes_to_tier1():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION))
    assert decision.tier == 1
    assert decision.model_key in ModelTier.TIER_1


def test_reflection_routes_to_tier1():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.REFLECTION))
    assert decision.tier == 1


def test_plan_generation_routes_to_tier2():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.PLAN_GENERATION))
    assert decision.tier == 2


def test_agentic_execution_routes_to_tier2():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.AGENTIC_EXECUTION))
    assert decision.tier == 2


# ---------------------------------------------------------------------------
# Signal 2: Priority escalation
# ---------------------------------------------------------------------------


def test_high_priority_escalates_tier1_to_tier2():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION, priority=9))
    assert decision.tier >= 2
    assert "priority" in decision.reason


def test_normal_priority_does_not_escalate():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION, priority=5))
    assert decision.tier == 1


def test_priority_7_does_not_escalate_tier1():
    # Threshold is 8 — priority 7 should not escalate
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION, priority=7))
    assert decision.tier == 1


# ---------------------------------------------------------------------------
# Signal 3: Context length
# ---------------------------------------------------------------------------


def test_long_context_escalates_to_tier3():
    router = make_router()
    decision = router.route(TaskContext(estimated_input_tokens=60_000))
    assert decision.tier >= 3
    assert "long_context" in decision.reason


def test_long_context_prefers_long_context_models():
    router = make_router()
    decision = router.route(TaskContext(estimated_input_tokens=100_000))
    assert decision.model_key in ModelTier.LONG_CONTEXT_MODELS


def test_short_context_does_not_escalate():
    router = make_router()
    decision = router.route(
        TaskContext(task_type=TaskType.BELIEF_EXTRACTION, estimated_input_tokens=1_000)
    )
    assert decision.tier == 1


# ---------------------------------------------------------------------------
# Signal 4: Tool use required
# ---------------------------------------------------------------------------


def test_tool_use_escalates_if_tier1_lacks_support():
    # Tier 1 (gemini-3-flash-preview) is not in TOOL_CALL_PREFERRED
    router = make_router()
    decision = router.route(
        TaskContext(task_type=TaskType.BELIEF_EXTRACTION, requires_tool_use=True)
    )
    assert decision.tier >= 2


def test_tool_use_prefers_tool_supported_models():
    router = make_router()
    decision = router.route(TaskContext(requires_tool_use=True))
    assert decision.model_key in ModelTier.TOOL_CALL_PREFERRED


# ---------------------------------------------------------------------------
# Signal 5: Quality threshold / structured output
# ---------------------------------------------------------------------------


def test_high_quality_threshold_escalates_to_tier3():
    router = make_router()
    decision = router.route(TaskContext(quality_threshold=0.9))
    assert decision.tier >= 3
    assert "quality_threshold" in decision.reason


def test_moderate_quality_threshold_no_escalation():
    router = make_router()
    decision = router.route(
        TaskContext(task_type=TaskType.BELIEF_EXTRACTION, quality_threshold=0.5)
    )
    assert decision.tier == 1


def test_requires_structured_output_prefers_reliable_models():
    router = make_router()
    decision = router.route(TaskContext(requires_structured_output=True))
    assert decision.model_key in ModelTier.STRUCTURED_OUTPUT_RELIABLE


# ---------------------------------------------------------------------------
# Signal 6: Latency sensitivity (logged but no tier change)
# ---------------------------------------------------------------------------


def test_latency_sensitive_flag_in_reason():
    router = make_router()
    decision = router.route(TaskContext(latency_sensitive=True))
    assert "latency_sensitive" in decision.reason


# ---------------------------------------------------------------------------
# Signal 7: Soft budget downgrade
# ---------------------------------------------------------------------------


def test_soft_budget_at_70pct_downgrades_tier():
    router = make_router(soft_budget=0.10)
    router._cycle_cost = 0.075  # 75% of 0.10
    decision = router.route(TaskContext(task_type=TaskType.PLAN_GENERATION))  # base tier 2
    assert decision.tier == 1  # downgraded from 2 to 1
    assert "soft_budget" in decision.reason


def test_soft_budget_below_70pct_no_downgrade():
    router = make_router(soft_budget=0.10)
    router._cycle_cost = 0.05  # 50% — below threshold
    decision = router.route(TaskContext(task_type=TaskType.PLAN_GENERATION))
    assert decision.tier == 2  # unchanged


# ---------------------------------------------------------------------------
# Signal 8: Retry escalation
# ---------------------------------------------------------------------------


def test_retry_escalates_tier():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION, retry_count=2))
    # Base tier 1 + 2 retries = tier 3
    assert decision.tier == 3
    assert "retry" in decision.reason


def test_retry_can_recover_soft_budget_downgrade():
    # Soft budget nudges tier 2 → 1; retry_count=1 escalates back to 2
    router = make_router(soft_budget=0.10)
    router._cycle_cost = 0.075
    decision = router.route(
        TaskContext(task_type=TaskType.PLAN_GENERATION, retry_count=1)
    )
    assert decision.tier == 2  # downgrade then recovery


def test_retry_capped_at_tier4():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.PLAN_GENERATION, retry_count=10))
    assert decision.tier == 4


# ---------------------------------------------------------------------------
# Signal 10 (final): Hard budget forces tier 1 — overrides retry
# ---------------------------------------------------------------------------


def test_hard_budget_exceeded_forces_tier1():
    router = make_router(hard_budget=0.50)
    router._cycle_cost = 0.60  # over hard budget
    decision = router.route(TaskContext(task_type=TaskType.PLAN_GENERATION, quality_threshold=0.9))
    assert decision.tier == 1
    assert "hard_budget" in decision.reason


def test_hard_budget_overrides_retry_escalation():
    """Hard budget is applied after retry, so it truly caps at tier 1."""
    router = make_router(hard_budget=0.50)
    router._cycle_cost = 0.60
    decision = router.route(
        TaskContext(task_type=TaskType.BELIEF_EXTRACTION, retry_count=5)
    )
    # Retry would push to tier 6 (clamped to 4), but hard budget resets to 1
    assert decision.tier == 1
    assert "hard_budget" in decision.reason


# ---------------------------------------------------------------------------
# Signal 11: Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_skips_model_after_failures():
    pool = {
        "gemini-2.0-flash": object(),
        "gpt-4o-mini": object(),
    }
    router = make_router(pool=pool, cb_threshold=3, cb_cooldown=120)
    for _ in range(3):
        router.record_failure("gemini-2.0-flash")

    decision = router.route(TaskContext(task_type=TaskType.PLAN_GENERATION))
    assert decision.model_key == "gpt-4o-mini"
    assert "cb_skip" in decision.reason


def test_circuit_breaker_clears_after_cooldown():
    """Use injectable clock to control time without mutating internal state."""
    fake_time = [0.0]

    def clock() -> float:
        return fake_time[0]

    router = make_router(cb_threshold=3, cb_cooldown=10, clock=clock)
    for _ in range(3):
        router.record_failure("gemini-2.0-flash")

    assert router._is_in_cooldown("gemini-2.0-flash")

    # Advance clock past the cooldown window
    fake_time[0] = 15.0
    assert not router._is_in_cooldown("gemini-2.0-flash")


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


def test_reset_cycle_budget():
    router = make_router()
    router._cycle_cost = 0.42
    router.reset_cycle_budget()
    assert router._cycle_cost == 0.0


def test_record_cost_accumulates_cycle_budget():
    """record_cost must update _cycle_cost from actual token usage."""
    from unittest.mock import MagicMock

    router = make_router()
    # Simulate a usage of 10K input + 500 output tokens on gemini-2.0-flash
    # Pricing: $0.15/1M input, $0.60/1M output
    # Expected cost: (10_000/1_000_000)*0.15 + (500/1_000_000)*0.60 = 0.0015 + 0.0003 = 0.0018
    usage = MagicMock()
    usage.input_tokens = 10_000
    usage.output_tokens = 500
    usage.total_tokens = 10_500
    # Use real calculate_cost — pass the actual LLMModel
    from empla.llm.config import MODELS

    usage.calculate_cost = lambda model: (
        (usage.input_tokens / 1_000_000) * model.input_cost_per_1m
        + (usage.output_tokens / 1_000_000) * model.output_cost_per_1m
    )

    router.record_cost("gemini-2.0-flash", usage)
    assert abs(router._cycle_cost - 0.0018) < 1e-9


def test_get_budget_state():
    router = make_router()
    router._cycle_cost = 0.05
    state = router.get_budget_state()
    assert state["cycle_cost_usd"] == 0.05
    assert "soft_budget_usd" in state
    assert "hard_budget_usd" in state
    assert "completion_counts" in state


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_pool_returns_sentinel():
    router = make_router(pool={})
    decision = router.route(TaskContext())
    assert isinstance(decision.model_key, str)
    assert "pool_empty" in decision.reason or "emergency" in decision.reason


def test_all_tier_in_cooldown_falls_through_to_higher_tier():
    pool = {
        "gemini-3-flash-preview": object(),
        "gemini-2.0-flash": object(),
        "gemini-1.5-pro": object(),
    }
    router = make_router(pool=pool, cb_threshold=1)
    router.record_failure("gemini-3-flash-preview")
    router.record_failure("gemini-2.0-flash")

    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION))
    assert decision.model_key == "gemini-1.5-pro"
    assert decision.tier == 3


def test_single_model_pool_no_fallback():
    """When pool has only one model and it fails, _get_fallback_provider → None path."""
    pool = {"gemini-3-flash-preview": object()}
    router = make_router(pool=pool)
    # Trip the only model's circuit breaker
    router.record_failure("gemini-3-flash-preview")
    router.record_failure("gemini-3-flash-preview")
    router.record_failure("gemini-3-flash-preview")

    decision = router.route(TaskContext())
    # Falls back to emergency path — no options remain but still returns a string
    assert isinstance(decision.model_key, str)


def test_fallback_model_key_populated_and_valid():
    router = make_router()
    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION))
    assert decision.fallback_model_key is not None
    assert decision.fallback_model_key != decision.model_key


def test_fallback_model_key_excludes_circuit_broken_models():
    """_find_fallback must not suggest a circuit-broken model."""
    pool = {
        "gemini-3-flash-preview": object(),
        "gemini-2.0-flash": object(),
        "gemini-1.5-pro": object(),
    }
    router = make_router(pool=pool, cb_threshold=1)
    # Trip the first tier-2 model
    router.record_failure("gemini-2.0-flash")

    decision = router.route(TaskContext(task_type=TaskType.BELIEF_EXTRACTION))
    # fallback_model_key should not be the tripped model
    assert decision.fallback_model_key != "gemini-2.0-flash"


def test_router_decision_type():
    router = make_router()
    decision = router.route(TaskContext())
    assert isinstance(decision, RouterDecision)


def test_record_success_increments_counts():
    router = make_router()
    router.record_success("gemini-2.0-flash")
    router.record_success("gemini-2.0-flash")
    assert router._success_counts["gemini-2.0-flash"] == 2
    assert router._completion_counts["gemini-2.0-flash"] == 2


# ---------------------------------------------------------------------------
# RoutingPolicy validation
# ---------------------------------------------------------------------------


def test_routing_policy_rejects_inverted_budgets():
    """soft_budget_usd must be strictly less than hard_budget_usd."""
    import pytest

    with pytest.raises(ValueError, match="soft_budget_usd"):
        RoutingPolicy(soft_budget_usd=0.50, hard_budget_usd=0.10)


def test_routing_policy_rejects_equal_budgets():
    import pytest

    with pytest.raises(ValueError, match="soft_budget_usd"):
        RoutingPolicy(soft_budget_usd=0.50, hard_budget_usd=0.50)
