---
status: RESEARCH
created: 2026-03-25
source: Phase 4 architecture review — rule-based logic audit
---

# Rule-Based Logic → Agentic Decision Audit

## Principle

Code should enforce **safety boundaries** (never delete the database, max 50 tool
calls per cycle). Code should NOT make **business judgments** (this opportunity
deserves priority 6, expire this goal after 72 hours). The LLM already has context
(beliefs, goals, situation analysis) — it should make judgment calls, not hardcoded
thresholds.

## High Priority — Limits Agent Intelligence

### 1. Goal Creation Caps

**Files:** `planning.py:395` (`:3` opportunities), `planning.py:430` (`:2` problems)
**Current:** Code limits to 3 opportunities and 2 problems per planning cycle.
**Problem:** If the LLM identifies 10 critical opportunities, code silently drops 7.
**Fix:** Remove caps. The LLM's SituationAnalysis already contains the full list —
let the dedup logic (word overlap) be the only filter.

### 2. Goal Abandon/Adjust Caps

**Files:** `planning.py:530` (`:3` abandons), `planning.py:572` (`:3` adjustments)
**Current:** Code limits to 3 abandonments and 3 priority adjustments per cycle.
**Problem:** If the LLM recommends abandoning 5 stale goals, code only processes 3.
**Fix:** Remove caps. GoalRecommendation already has the LLM's full recommendation.

### 3. Hardcoded Priority for Opportunities/Problems

**Files:** `planning.py:407` (`priority=6`), `planning.py:443` (`priority=8`)
**Current:** Opportunities always get priority 6, problems always get priority 8.
**Problem:** "Close $1M deal" opportunity should be priority 10, not 6.
**Fix:** Include priority in SituationAnalysis structured output. Let the LLM set
priority per item based on impact assessment.

### 4. Hardcoded TTL for Opportunities/Problems

**Files:** `planning.py:411` (`max_age_hours: 72`), `planning.py:444` (`max_age_hours: 48`)
**Current:** Opportunities expire after 72h, problems after 48h.
**Problem:** "Quarterly budget review opportunity" should live for 30 days, not 3.
**Fix:** Let the LLM set TTL in SituationAnalysis based on time sensitivity.

### 5. Playbook Promotion/Demotion Thresholds

**Files:** `reflection.py:603-605` (promote: 3x/0.7), `reflection.py:571` (demote: 5x/0.5)
**Current:** Fixed thresholds for all employees.
**Problem:** An SDR might auto-promote at 3x/0.65; safety-critical work needs 20x/0.95.
**Fix:** Move thresholds to EmployeeConfig or LoopConfig. Per-role defaults in catalog.

## Medium Priority — Reduces Adaptability

### 6. Belief Promotion Threshold

**File:** `execution.py:595` (`>= 0.9`)
**Current:** Beliefs auto-promote to semantic memory at 90% confidence.
**Fix:** LLM decides during reflection which beliefs are worth long-term storage.

### 7. Strategic Planning Trigger

**File:** `planning.py:70,82` (importance > 0.7, confidence delta > 0.3, fixed predicates)
**Current:** Hardcoded predicates and thresholds trigger strategic planning.
**Fix:** Let a lightweight LLM check classify belief changes as "significant enough
to warrant replanning." More expensive but more accurate.

### 8. Strategy Effectiveness Classification

**File:** `reflection.py:463` (0.7/0.4 buckets)
**Current:** Three fixed buckets (effective/mixed/struggling).
**Fix:** LLM writes the assessment directly — it has the context to say "effective
despite low rate because we're in an exploration phase."

### 9. Memory Decay Policies

**File:** `reflection.py:649-682` (30 days, 0.95 decay, 0.8 reinforce, 0.2 archive)
**Current:** Fixed rates for all memory types and employees.
**Fix:** Configurable per memory type and per role. Quarterly-planning employees
need longer retention than daily-operational employees.

## Correctly Rule-Based (Keep As-Is)

- **Trust boundary** — rate limits (50 calls/cycle), deny lists, taint model → security
- **Data normalization** — belief types, intention types → schema consistency
- **Context budgets** — `[:20]` beliefs, `[:10]` subjects → token management
- **Safety valves** — max cycle duration, max perception iterations → runaway prevention
- **Paused/stopped status** — operational control loop → infrastructure

## Implementation Plan

### Phase 4A (this PR): Remove caps, let LLM set priority/TTL
1. Remove `[:3]`/`[:2]` caps on goal creation
2. Remove `[:3]` caps on abandon/adjust
3. Add priority and max_age_hours to SituationAnalysis structured output
4. Use LLM-provided values when creating opportunity/problem goals

### Phase 4B (follow-up): Configurable thresholds
5. Move playbook promotion/demotion thresholds to LoopConfig
6. Move memory decay policies to configurable per-role defaults
7. Move belief promotion threshold to configurable

### Phase 4C (future): Full agentic decisions
8. LLM-driven strategic planning trigger
9. LLM-driven belief promotion
10. LLM-driven strategy effectiveness assessment
