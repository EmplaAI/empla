# LLM Routing Design

> **Status:** Active
> **Author:** Claude Code
> **Date:** 2026-03-05
> **Phase:** Phase 2 - LLM Integration

---

## Overview

empla runs a continuous BDI loop with multiple distinct LLM call types per cycle. Before routing, every call — regardless of whether it's a cheap belief extraction or a high-stakes strategic planning step — hit the same `primary_model`. The routing layer fixes this.

**The problem:**

| Call Site | Stakes | Tokens | Old Behavior |
|-----------|--------|--------|--------------|
| Belief extraction | Low (errors silently ignored) | ~2K | Full claude-sonnet-4 |
| Situation analysis | Medium | ~8K | Full claude-sonnet-4 |
| Plan generation | High | ~12K | Full claude-sonnet-4 |
| Agentic tool use | High + latency sensitive | ~6K/iter | Full claude-sonnet-4 |
| Deep reflection | Very low | ~4K | Full claude-sonnet-4 |

Paying $3/1M input tokens for belief extraction that tolerates errors is wasteful. Routing selects the cheapest model that meets the requirements of each call, without any LLM overhead for routing itself.

**What routing is NOT:**

- Not a load balancer (no session affinity, no round-robin)
- Not LLM-assisted (the router itself never calls an LLM)
- Not a caching layer
- Not a rate limiter

---

## Architecture

```
Call site (BDI phase)
        │
        │  task_context = TaskContext(
        │      task_type=TaskType.BELIEF_EXTRACTION,
        │      priority=observation.priority,
        │      requires_structured_output=True,
        │      quality_threshold=0.5,
        │  )
        ▼
LLMService.generate_structured(..., task_context=task_context)
        │
        ├─ task_context is None? ──▶ self.primary  (legacy path, unchanged)
        │
        └─ task_context provided + routing enabled?
                │
                ▼
          LLMRouter.route(task_context)
                │
                │  Evaluates 11 signals in <1ms
                │
                ▼
          RouterDecision
          { model_key: "gemini-3-flash-preview",
            tier: 1,
            reason: "task_type=belief_extraction→tier1",
            fallback_model_key: "gemini-2.0-flash" }
                │
                ▼
        _provider_pool["gemini-3-flash-preview"]
                │
                ▼
        LLMProviderBase.generate_structured(request)
```

The **provider pool** is a `dict[str, LLMProviderBase]` built at startup that holds one HTTP client per model. Providers are created lazily — models with no API key are silently skipped. The primary and fallback providers from `LLMConfig` are reused in the pool to avoid opening duplicate connections.

---

## Model Tiers

Models are grouped into four cost/capability tiers. The router works with tiers, not specific model names, so adding a new model only requires placing it in the right tier.

| Tier | Models | Input $/1M | Output $/1M | Default Use |
|------|--------|-----------|------------|-------------|
| **1 — Nano** | `gemini-3-flash-preview` | $0.10 | $0.40 | Belief extraction, reflection |
| **2 — Fast** | `gemini-2.0-flash`, `gpt-4o-mini` | $0.15 | $0.60 | Planning, goal management, agentic execution |
| **3 — Standard** | `gemini-1.5-pro`, `gpt-4o` | $1.25–$2.50 | $5–$10 | High-priority planning, long context (1M tokens) |
| **4 — Premium** | `claude-sonnet-4`, `claude-opus-4` | $3–$15 | $15–$75 | Quality threshold ≥ 0.9, max retry escalation |

Within a tier, model preference order is adjusted per-call based on capability signals (see Signal 4, 5, 6 in the selection algorithm below).

Three capability sets are maintained alongside the tier lists:

- **`LONG_CONTEXT_MODELS`** — models with ≥1M token context windows (`gemini-1.5-pro`)
- **`TOOL_CALL_PREFERRED`** — models with reliable function calling support
- **`STRUCTURED_OUTPUT_RELIABLE`** — models with reliable JSON/constrained output

---

## The 11 Routing Signals

Signals are evaluated in order. The first eight determine the **target tier**. Signal 9 normalizes the range. The final two act as constraints applied after tier selection.

### Signal 1: Task Type (Base Tier)

The BDI task type provides the starting tier. This is the primary signal.

```
BELIEF_EXTRACTION  → tier 1
REFLECTION         → tier 1
PLAN_GENERATION    → tier 2
GOAL_MANAGEMENT    → tier 2
AGENTIC_EXECUTION  → tier 2
SITUATION_ANALYSIS → tier 2
GENERAL            → tier 2
```

`TaskType.GENERAL` is the safe default for call sites not yet tagged.

---

### Signal 2: Priority Escalation

High-priority calls deserve better reasoning. If `priority >= 8` and the task type would route to tier 1, escalate to tier 2 minimum.

```
priority=9, task=BELIEF_EXTRACTION → tier 1 → escalate → tier 2
priority=7, task=BELIEF_EXTRACTION → tier 1 (no change)
```

The threshold is 8. This lets routine belief extractions stay cheap while urgent ones get a capable model.

---

### Signal 3: Long Context

If `estimated_input_tokens > long_context_token_threshold` (default: 50,000), the call requires a long-context model. The current long-context model is `gemini-1.5-pro` (tier 3, 1M context window).

```
tokens=60_000 → tier max(current, 3), prefer LONG_CONTEXT_MODELS within tier
tokens=1_000  → no change
```

Within `_select_from_tier`, `LONG_CONTEXT_MODELS` are sorted to the front of the candidate list for this signal.

---

### Signal 4: Tool Use Required

Function calling (tool use) is not universally reliable across all models. Tier 1 (`gemini-3-flash-preview`) is not in `TOOL_CALL_PREFERRED`. If `requires_tool_use=True` and the current tier has no tool-capable models, escalate to tier 2.

```
requires_tool_use=True, tier=1 → tier 2 (tier 1 not in TOOL_CALL_PREFERRED)
requires_tool_use=True, tier=2 → no change (tier 2 has TOOL_CALL_PREFERRED models)
```

Within `_select_from_tier`, `TOOL_CALL_PREFERRED` models are sorted to the front for this signal.

---

### Signal 5: Structured Output Reliability

Two sub-signals are evaluated:

1. **Hard constraint:** `requires_structured_output=True` forces tier 2 minimum, since tier 1 (`gemini-3-flash-preview`) is not in `STRUCTURED_OUTPUT_RELIABLE`. Within `_select_from_tier`, `STRUCTURED_OUTPUT_RELIABLE` models are sorted to the front.

   ```
   requires_structured_output=True, tier=1 → tier 2 (hard constraint)
   requires_structured_output=True, tier=2 → no change
   ```

2. **Quality threshold upgrade:** `quality_threshold >= 0.9` escalates to tier 3 minimum for near-perfect fidelity.

   ```
   quality_threshold=0.9  → tier max(current, 3)
   quality_threshold=0.75 → no change
   ```

---

### Signal 6: Latency Sensitivity

`latency_sensitive=True` is a flag, not a tier modifier. No tier change occurs. The flag is logged to the routing decision reason string for SLA analysis. Agentic execution calls set this flag since they run in tight tool-call loops.

---

### Signal 7: Soft Budget Downgrade

Tracks accumulated LLM cost within the current BDI cycle. If `cycle_cost >= soft_budget * 0.7` (default threshold: $0.07 of $0.10), nudge down by 1 tier.

```
cycle_cost=$0.075, soft_budget=$0.10, tier=2 → tier 1
cycle_cost=$0.050, soft_budget=$0.10, tier=2 → no change
```

`reset_cycle_budget(owner_id)` is called at the start of `_execute_bdi_phases()` to zero the counter for this employee each cycle. Passing an `owner_id` (e.g., the employee's UUID) ensures that concurrent loops scoped to different employees do not interfere with each other's budget tracking.

**Interaction with retry (signal 8):** The soft-budget downgrade is intentionally reversible by retry. If a call fails (tier 1 produced bad output), the retry escalates back up. A failure signal is stronger than a cost signal.

---

### Signal 8: Retry Escalation

When a call fails, `_get_fallback_provider` re-routes with `retry_count = original_retry_count + 1`. The router adds `retry_count` to the current tier.

```
retry_count=0 → no change
retry_count=1 → tier + 1 (try a better model)
retry_count=2 → tier + 2
```

Capped at tier 4. Applied **after** soft budget, so retries can recover from a soft-budget downgrade. Applied **before** hard budget (signal 10), so hard budget acts as a true ceiling.

---

### Signal 9: Tier Clamp

After signals 1–8, the tier is clamped to the valid range `[1, 4]`.

---

### Signal 10: Hard Budget (Absolute Ceiling)

If `cycle_cost >= hard_budget` (default: $0.50), force tier 1 regardless of everything else, including retry escalation. Applied **last** to ensure it truly overrides all other signals.

```
cycle_cost=$0.60, hard_budget=$0.50, tier=3 → tier 1 (hard override)
```

This prevents a runaway cycle from escalating to premium models after the budget is blown.

---

### Signal 11: Circuit Breaker + Final Model Selection

Once the target tier is determined, `_select_from_tier` picks the concrete model:

1. Walk tiers from `target_tier` upward (fall through if needed)
2. Within each tier, sort candidates by capability preference (long-context, tool-capable, structured-output-reliable)
3. Skip models not in the provider pool (no API key configured)
4. Skip models whose circuit breaker is tripped (≥ N failures within the cooldown window)
5. Return the first passing model

If all models are unavailable (all tripped or no pool), fall through to an emergency fallback across all tiers. If the pool is empty, return a sentinel string with `pool_empty` in the reason.

**Circuit breaker parameters (defaults):**

| Parameter | Default | Effect |
|-----------|---------|--------|
| `circuit_breaker_failure_threshold` | 3 | Trips after 3 failures |
| `circuit_breaker_cooldown_seconds` | 120 | Resets after 2 minutes |

The clock is injectable (`_clock: Callable[[], float]`) for deterministic testing.

---

## Signal Evaluation Summary

```
Input: TaskContext
       │
       ▼
[1] task_type → base_tier
       │
       ▼
[2] priority ≥ 8 and tier < 2 → tier = 2
       │
       ▼
[3] tokens > threshold → tier = max(tier, 3)
       │
       ▼
[4] requires_tool_use and tier-1 has no tool models → tier = max(tier, 2)
       │
       ▼
[5] quality_threshold ≥ 0.9 → tier = max(tier, 3)
       │
       ▼
[6] latency_sensitive → log only (no tier change)
       │
       ▼
[7] cycle_cost ≥ soft_budget * 0.7 and tier > 1 → tier -= 1
       │
       ▼
[8] retry_count > 0 → tier = min(tier + retry_count, 4)
       │
       ▼
[9] clamp to [1, 4]
       │
       ▼
[10] cycle_cost ≥ hard_budget → tier = 1  (absolute ceiling)
       │
       ▼
[11] _select_from_tier(tier, context) → model_key
       │
       └── for each tier from target upward:
               sort candidates by capability preference
               skip missing or circuit-broken models
               return first passing model
```

---

## TaskContext Reference

```python
@dataclass(slots=True)
class TaskContext:
    task_type: TaskType = TaskType.GENERAL
    priority: int = 5               # 1–10; ≥8 triggers priority escalation
    estimated_input_tokens: int = 0 # estimate; triggers long-context routing if >50K
    requires_tool_use: bool = False  # function calling needed
    requires_structured_output: bool = False  # structured JSON output needed
    latency_sensitive: bool = False  # logged; no tier change
    quality_threshold: float = 0.5  # 0.0–1.0; ≥0.9 triggers tier-3 escalation
    retry_count: int = 0             # set by LLMService on retry; escalates tier
```

`@dataclass(slots=True)` is used instead of Pydantic to avoid ~5–10x validation overhead on this hot-path type.

---

## Enabling Routing

Routing is **opt-in**. The default `LLMConfig` has `routing_policy=None`, which keeps the original single-model behavior.

```python
from empla.llm import LLMService
from empla.llm.config import LLMConfig, RoutingPolicy

config = LLMConfig(
    primary_model="gemini-2.0-flash",    # legacy path fallback
    fallback_model="claude-sonnet-4",    # legacy path fallback
    routing_policy=RoutingPolicy(        # enables routing
        enabled=True,
        soft_budget_usd=0.10,
        hard_budget_usd=0.50,
        long_context_token_threshold=50_000,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_cooldown_seconds=120,
    ),
    vertex_project_id="my-project",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

llm = LLMService(config)
```

**Budget constraint:** `soft_budget_usd` must be strictly less than `hard_budget_usd`. This is validated at construction time.

---

## Adding TaskContext to a Call Site

All four `generate_*` methods accept an optional `task_context` parameter. Existing call sites without `task_context` continue to use the primary provider unchanged.

```python
# Before: uses primary provider unconditionally
response, parsed = await llm_service.generate_structured(
    prompt=user_prompt,
    system=system_prompt,
    response_format=MyOutputModel,
    temperature=0.3,
)

# After: router selects model based on context
response, parsed = await llm_service.generate_structured(
    prompt=user_prompt,
    system=system_prompt,
    response_format=MyOutputModel,
    temperature=0.3,
    task_context=TaskContext(
        task_type=TaskType.BELIEF_EXTRACTION,
        priority=observation.priority,
        requires_structured_output=True,
        quality_threshold=0.5,
    ),
)
```

**Guidelines for setting fields:**

| Situation | Field to set |
|-----------|-------------|
| Output will be parsed as Pydantic model | `requires_structured_output=True` |
| Output correctness is critical | `quality_threshold=0.8–0.9` |
| Call is inside a real-time tool loop | `latency_sensitive=True` |
| Calling function-calling / tools | `requires_tool_use=True` |
| Prompt is likely > 50K tokens | `estimated_input_tokens=len(prompt)//4` |
| Called in response to high-priority event | `priority=observation.priority` |

---

## Current Call Sites

| File | Method | TaskType | Notes |
|------|--------|----------|-------|
| `empla/bdi/beliefs.py` | `extract_beliefs_from_observation` | `BELIEF_EXTRACTION` | `quality_threshold=0.5`, priority from observation |
| `empla/bdi/intentions.py` | `generate_plan_for_goal` | `PLAN_GENERATION` | `quality_threshold=0.7`, priority from goal |
| `empla/core/loop/execution.py` | `_analyze_situation_with_llm` | `SITUATION_ANALYSIS` | `priority=7`, `quality_threshold=0.8` |
| `empla/core/loop/execution.py` | `_execute_intention_with_tools` | `AGENTIC_EXECUTION` | `requires_tool_use=True`, `latency_sensitive=True`, retry tracked per LLM failure |
| `empla/core/loop/execution.py` | `_analyze_patterns_with_llm` | `REFLECTION` | `priority=3`, `quality_threshold=0.4` |

The budget reset happens at the top of `_execute_bdi_phases()`:
```python
if self.llm_service:
    self.llm_service.reset_cycle_budget()
```

---

## Observability

### Log Output

Every routing decision is logged at `DEBUG` level with structured fields:

```
Router selected model
  model_key=gemini-3-flash-preview
  tier=1
  reason=task_type=belief_extraction→tier1
  task_type=belief_extraction
  priority=5
  retry_count=0
  cycle_cost=0.0000
```

The `reason` string is a comma-separated trace of every signal that fired. Example with multiple signals:

```
reason=task_type=plan_generation→tier2, priority=9→tier2_min, retry=1→tier3,
       soft_budget=0.0820/0.1000→downgrade, ...
```

### `get_cost_summary()`

When routing is enabled, `LLMService.get_cost_summary()` includes a `routing` sub-dict:

```python
summary = llm.get_cost_summary()
# {
#   "total_cost": 0.042,
#   "requests_count": 28,
#   "average_cost_per_request": 0.0015,
#   "routing": {
#     "cycle_cost_usd": 0.0,           # resets each cycle
#     "soft_budget_usd": 0.10,
#     "hard_budget_usd": 0.50,
#     "circuit_breaker_tripped": {},   # empty = all healthy
#     "completion_counts": {           # calls that completed (success or failure)
#       "gemini-3-flash-preview": 18,
#       "gemini-2.0-flash": 8,
#       "gemini-1.5-pro": 2,
#     },
#     "success_counts": {
#       "gemini-3-flash-preview": 17,
#       "gemini-2.0-flash": 8,
#       "gemini-1.5-pro": 2,
#     },
#   }
# }
```

---

## Adding a New Model

1. **Add to `MODELS` in `empla/llm/config.py`** with correct provider, model ID, and pricing.

2. **Place in the right tier in `empla/llm/models.py`** (`ModelTier.TIER_1..4`):
   ```python
   TIER_2: tuple[str, ...] = ("gemini-2.0-flash", "gpt-4o-mini", "new-fast-model")
   ```

3. **Add to capability sets if applicable:**
   ```python
   TOOL_CALL_PREFERRED: frozenset[str] = frozenset({
       ...,
       "new-fast-model",
   })
   ```

4. The provider pool will pick it up automatically if the corresponding API key is configured. No other changes needed.

---

## Known Limitations

**`stream()` does not update router state.** Token counts are only available after a stream is fully consumed. `stream()` uses the router for model selection but does not call `record_success`, `record_failure`, or `record_cost`. Budget accounting is incomplete for streaming calls. Use `generate()` when accurate budget tracking matters.

**`estimated_input_tokens` is caller-supplied.** The router cannot measure actual token counts before the call (that would require another LLM call). Callers should provide a rough estimate: `len(prompt) // 4` is a reasonable approximation for English text.

**Circuit breaker is in-process only.** Failure counts are stored in memory and reset when the process restarts. A model that was flaky will start with a clean circuit breaker after a restart.

**Budget resets per cycle, not per wall-clock time.** A very long-running BDI cycle (e.g., a slow capability) will have its full budget available for the next cycle even if it was just seconds ago.

---

## File Map

```
empla/llm/
├── models.py          # TaskType, TaskContext, RouterDecision, ModelTier
├── config.py          # RoutingPolicy, LLMConfig (routing_policy field)
├── router.py          # LLMRouter (11 signals, circuit breaker, budget)
└── __init__.py        # LLMService (provider pool, routing integration)

tests/unit/

tests/unit/
└── test_llm_router.py # 37 unit tests — all 11 signals + edge cases
```
