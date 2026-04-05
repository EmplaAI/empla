# empla - Roadmap

> **Updated:** 2026-03-24
> **Strategy:** Production Foundation in progress. BDI loop complete (including
> GoalRecommendation, deep reflection → beliefs, non-numeric goal completion).
> JWT auth shipped. Next: dashboard metrics, test coverage push, then re-plan
> Phase 4 direction.
> **Reference:** `ARCHITECTURE.md`, `docs/designs/product-strategy-2026-03.md`

---

## Current State

Tests: 781 collected, ~52% coverage | Employees: SalesAE, CSM
Working: Complete BDI loop with GoalRecommendation, deep reflection belief
conversion, non-numeric goal LLM completion checks. Direct HubSpot CRM +
Google Calendar + Email connectors via httpx. Trust boundary (taint-based,
global deny, role restrictions). Integration health monitoring with BDI belief
generation. OAuth credential injection at startup. JWT authentication (HS256)
with production guards. Dashboard with BDI tabs (Goals, Intentions, Beliefs).
Execution loop split into 7 focused modules.

---

## Production Foundation (in progress)

Remaining items from the Production Foundation plan (CEO + Eng reviewed).

### ~~1. Dashboard metrics~~ (PR #71)

~~Persist cycle metrics to DB, expose via API.~~ Done — cycle duration,
success/failure, tool call deltas, tool latency. API endpoints for summary
and time-series history. React dashboard panel deferred.

### 2. Test coverage push (52% → 80%)

Write tests for untested paths across the codebase. Focus on: BDI loop
integration paths, API endpoints (TestClient), LLM service error handling,
integration connectors, and settings validation.

---

## Phase 4: TBD — Re-plan After Production Data

Direction to be decided after Production Foundation ships and we have metrics
data from real usage. Candidates (from CEO review):

- **Efficiency + Intelligence** — Playbook system, adaptive cycle frequency,
  event-driven triggers. Drops LLM cost from ~$65/day to ~$10-15/day.
- **Native Workspace** — empla-native contacts, pipeline, tasks. Competitive
  moat. Decouples from external APIs.
- **Hybrid** — cherry-pick from both based on production observations.

Run `/plan-ceo-review` after Production Foundation merges to decide.

---

## Phase 5: Production Resilience

- LLM failover — primary + fallback models, ProviderHealth tracking
- Context window compaction — token counting, auto-compaction
- Timeouts/watchdogs — per-call + per-cycle timeouts, loop detection
- Graceful shutdown & state persistence — save/resume BDI state
- Exponential loop backoff — cycle-level backoff on failure

---

## Backlog

- Password/OAuth verification on login — User model needs password field,
  bcrypt hashing, or OAuth/SAML flow. Required before multi-tenant production.
- Dashboard trust boundary controls — per-tenant settings for high-risk
  tool classification, global deny lists, and role restrictions
- Token revocation — jti claim, revocation list for compromised tokens
- Rate limiting on auth endpoints
- Observation prioritization — let perception LLM classify importance
- Structured world model — replace SPO belief triples with typed domain model
- Goal-task trees — hierarchical decomposition instead of flat goals + intentions
- Active hours gating — configurable work schedule
- Hot-reload config — update without restart
- Multi-employee coordination — handoff protocols, shared beliefs
- New employee types (PM) — prove platform extensibility
- Embedding-based procedure search — pgvector similarity
- Developer experience docs — guides for creating custom employees

---

## Completed

**Phase 1 — Foundation:** DB schema, BDI engine, Memory systems, Proactive
loop, LLM service

**Phase 2 — Platform:** BaseCapability + Registry, Email/Workspace/Compute
capabilities, SalesAE + CSM employees, BDI lifecycle hooks, Process
infrastructure + CLI, Simulation framework, String-based capability types,
OpenClaw research

**Phase 2.5 — Dashboard & Integrations:** Dashboard (employees, activity,
settings), OAuth integration framework (Google/Microsoft), platform OAuth
apps, admin CLI, MCP server management (CRUD, SSRF protection, encrypted
credentials, runtime bridge), centralized settings, Vertex AI tool calling,
unified tool architecture (@tool + ToolRouter)

**Phase 2.75 — Integration Router & Agentic Perception (PR #56):**
IntegrationRouter for tool-based integrations, agentic perception via LLM
tool calling, role catalog as single source of truth, test infrastructure
(calendar MCP server, seed scenarios, dev_e2e.sh), activity recorder for
dashboard feed

**Phase 3A — Platform Solidification (PR #58, #59):**
Removed old capabilities system, completed agentic execution, LLM-driven goal
evaluation + achievement hooks, procedural memory recording + maintenance +
plan influence

**Phase 3A.5 — E2E Validation (2026-03-17/18):**
Full E2E test with production code + test MCP servers (15 tests). Runner wires
MCP servers from DB. Vertex AI schema sanitization. Fixed DB constraint
mismatches. Dashboard BDI tabs. Goal/intention dedup. Belief extraction
prompt improvement.

**Phase 3B — Real-World Integrations (PRs #61-#67, 2026-03-19/20):**
Direct HubSpot CRM + Google Calendar + Email connectors via httpx. OAuth
credential injection at startup. LLM trust boundary (taint-based, global deny,
role restrictions). Integration health monitoring with BDI belief generation.
Execution loop refactored into 7 focused modules via mixin pattern.
ARCHITECTURE.md rewritten to reflect reality.

**Phase 3C — BDI Loop Completion (PR #68, 2026-03-24):**
GoalRecommendation wired into strategic planning (description-based fuzzy
matching). Deep reflection insights converted to typed beliefs
(strategy_effectiveness, known_failure_patterns, improvement_opportunities)
and procedural memory. Non-numeric goal LLM completion checks alongside TTL.
37 new tests.

**Production Foundation — JWT Auth (PR #69, 2026-03-24):**
Replaced stub user_id:tenant_id tokens with JWT (HS256). Production guards
(fail-fast on default/short secret in non-dev, algorithm locked to HMAC
family). Unified error messages prevent tenant enumeration. PyJWTError catch
for config errors. 27 new tests.

---

**Last Updated:** 2026-03-24
