# Architecture Review — 2026-03-18

> **Status:** Active Review
> **Context:** Full E2E test of BDI loop with Vertex AI + MCP servers revealed structural issues
> **Author:** Claude Code + Navin

---

## Executive Summary

The BDI loop runs end-to-end (proven with Vertex AI + real MCP tools). The architecture has the right shape but the implementation has grown organically with subsystems that don't connect, excessive LLM calls, and dead code. The main loop does too much LLM work for too little decision quality.

---

## What's Working

- Core BDI loop runs autonomously (perceive → believe → plan → execute → reflect)
- Employee created deals, scheduled calls, formed beliefs — all without instructions
- MCP bridge connects to external tools via stdio/HTTP
- Multi-tenancy is consistent (tenant_id everywhere)
- 843 tests, type hints everywhere, clean async patterns
- Activity recording feeds the dashboard in real-time

---

## Critical Issues (ranked by impact)

### 1. LLM Call Explosion (Cost & Latency)

A single BDI cycle makes **4 to 38 LLM calls**. Worst offender: belief extraction — one LLM call per observation. With 5 perception iterations × 3 tool results = 15 serial LLM calls just to restate what structured tool data already says.

| Phase | LLM Calls | Notes |
|-------|-----------|-------|
| Perception | 1–5 | generate_with_tools per iteration |
| Belief extraction | 1–N | One per observation (!) |
| Goal evaluation | 0–1 | If beliefs changed |
| Strategic planning | 1–6 | Situation analysis + plan per goal |
| Intention execution | 1–10 | Agentic tool calling |
| Deep reflection | 0–1 | Pattern analysis |
| **Total** | **4–38** | |

**Fix:** Batch observations into single extraction call. Direct tool-to-belief mapping for structured data. Reserve LLM for unstructured content.

### 2. Generated Plans Are Ignored

`generate_plan_for_goal()` produces detailed `PlanGenerationResult` with steps and dependencies. Stored in `EmployeeIntention.plan` JSONB. But `_execute_intention_with_tools()` **never reads the plan** — only passes `intention.description` to the LLM, which reinvents the approach from scratch.

**Fix:** Feed plan steps into execution prompt. Or drop plan generation and let execution LLM plan-and-execute in one shot.

### 3. Dead Subsystems

| Subsystem | Status |
|-----------|--------|
| Working Memory | Implemented, DB-backed, **never read or written in BDI cycle** |
| Semantic Memory | Implemented, DB-backed, **never read or written in BDI cycle** |
| Deep reflection insights | Written to episodic memory, **never read back** |
| `GoalRecommendation` model | Defined in execution.py, **never used** |
| Belief decay | `decay_beliefs()` implemented, **never called** |

### 4. Goals That Can Never Complete

Opportunity/problem goals from situation analysis use `target={"type": "opportunity", "description": "..."}`. Goal evaluation only checks goals with `target.metric` + `target.value` (numeric). These goals sit active forever, crowding the top-5 limit for plan generation.

### 5. No Transaction Boundaries

All subsystems share one `AsyncSession`. No `session.commit()` in `_execute_bdi_phases()`. Crash mid-cycle = all writes lost. Activity recording needed an explicit commit hack to work.

### 6. Observation Quality Is Uniform

Every tool result becomes an observation with hardcoded `priority=5` and `requires_action=False`. Classification by substring match on tool name never triggers. System can't distinguish critical pipeline drops from routine calendar reads.

---

## Recommendations

### Sprint 1: LLM Call Reduction & Dead Code Cleanup (~2 days with Claude Code)

1. **Batch belief extraction** — single LLM call for all observations
2. **Feed plan into execution** — pass `intention.plan` steps to execution LLM
3. **Call belief decay** — add `decay_beliefs()` to cycle
4. **Wire `GoalRecommendation`** — let strategic planning abandon/reprioritize
5. **Add commits at phase boundaries**
6. **Wire working memory** — use during perception and execution for context
7. **Wire semantic memory** — use for knowledge accumulation across cycles
8. **Delete or mark unused code** (if not wiring it)

### Sprint 2: Smarter Perception & Goals (~2 days with Claude Code)

9. **Direct tool-to-belief mapping** — structured results skip LLM extraction
10. **Fix opportunity/problem goals** — add TTL or LLM-based completion check
11. **Observation prioritization** — let perception LLM classify importance
12. **Adaptive cycle frequency** — wait longer if nothing changed

### Sprint 3: Playbooks & Events (~3 days with Claude Code)

13. **Playbook system** — codified tool call sequences the LLM selects/parameterizes
14. **Event-driven triggers** — react to changes instead of polling
15. **Read back deep reflection insights** — close the learning loop

### Future: Structural Rethink

16. **Structured world model** instead of SPO triples
17. **Goal-task trees** instead of flat goals + flat intentions
18. **Production resilience** — LLM failover, context compaction, watchdogs

---

## Metrics to Track

- LLM calls per cycle (target: <8, current: 4–38)
- Cycle wall-clock time (target: <30s, current: 60–120s)
- Unique goals (should not grow unbounded)
- Belief count (should plateau with decay)
- Intention success rate
- Cost per cycle (LLM tokens)
