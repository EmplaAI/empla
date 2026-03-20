# empla - Roadmap

> **Updated:** 2026-03-20
> **Strategy:** Phase 3B (Real-World Integrations) complete. BDI loop optimized,
> direct HubSpot/Calendar/Email connectors live, trust boundary + health monitoring
> active. Next: Prometheus metrics, test coverage push, production hardening.
> **Reference:** `ARCHITECTURE.md`, `docs/designs/real-integrations-2026-03.md`

---

## Current State

Tests: 787 collected, ~57% coverage | Employees: SalesAE, CSM
Working: Optimized BDI loop (batch beliefs, all memory wired, transaction boundaries).
Direct HubSpot CRM + Google Calendar + Email connectors via httpx. Trust boundary
(taint-based, global deny, role restrictions). Integration health monitoring with
BDI belief generation. OAuth credential injection at startup. Dashboard with BDI
tabs (Goals, Intentions, Beliefs). Execution loop split into 7 focused modules.

---

## Phase 3C: Loop Optimization & Subsystem Wiring (~3 days with Claude Code)

Architecture review items. Fix the loop before adding more integrations.

### Sprint 1: LLM Call Reduction & Dead Code (~1.5 days)

1. **Batch belief extraction** — single LLM call for all observations instead
   of one per observation. Biggest cost savings (eliminates 5–15 LLM calls/cycle).

2. **Feed plan into execution** — pass `intention.plan` steps to the execution
   LLM prompt. Currently generated plans are stored but ignored at execution time.

3. **Wire belief decay** — call `decay_beliefs()` at cycle start. Currently
   beliefs accumulate without bound.

4. **Wire `GoalRecommendation`** — let strategic planning abandon/reprioritize
   goals. Model exists but is never used. Goals only grow today.

5. **Add transaction boundaries** — commit at phase boundaries instead of
   relying on a single uncommitted session for the entire cycle.

6. **Fix opportunity/problem goals** — add TTL or LLM-based completion check.
   Currently these goals can never complete (no numeric target).

### Sprint 2: Wire Orphaned Subsystems (~1.5 days)

7. **Wire working memory** — use as LLM context window during perception and
   execution. Store current focus, recent tool results, active context.

8. **Wire semantic memory** — accumulate domain knowledge (company info, contact
   details, learned facts) across cycles. Feed into perception and planning prompts.

9. **Close deep reflection loop** — read back `deep_reflection` episodes and
   convert insights into beliefs or procedural memory adjustments.

10. **Direct tool-to-belief mapping** — structured tool results (CRM metrics,
    calendar events) should update beliefs without LLM intermediation. Reserve
    LLM extraction for unstructured content (emails, documents).

---

## Phase 3B: Core Integrations (~2 days with Claude Code)

After the loop is optimized, add integrations for real-world work.

### 1. CRM adapter (HubSpot / Salesforce)

MCP server or native tool for read/write CRM access — contacts, deals,
pipeline stages. Required for SalesAE and CSM to do real work.

### 2. Calendar adapter (Google Calendar)

Read/write calendar events. OAuth infrastructure exists for Google.

### 3. Gmail send completion

Receive works via MCP bridge. Complete the send path.

---

## Phase 4: Playbooks & Event-Driven (~3 days with Claude Code)

### 1. Playbook system

Codified tool call sequences (prospecting, pipeline review, lead response)
that the LLM selects and parameterizes instead of regenerating from scratch.
Evolution of procedural memory into executable recipes.

### 2. Event-driven triggers

React to new emails, CRM changes, calendar events instead of polling every
5 minutes. Proactive loop becomes fallback for "nothing happened."

### 3. Adaptive cycle frequency

If nothing changed, wait longer. If significant changes detected, cycle faster.
Currently fixed at `cycle_interval_seconds`.

---

## Phase 5: Production Resilience

- LLM failover — primary + fallback models, ProviderHealth tracking
- Context window compaction — token counting, auto-compaction
- Timeouts/watchdogs — per-call + per-cycle timeouts, loop detection
- Graceful shutdown & state persistence — save/resume BDI state
- Exponential loop backoff — cycle-level backoff on failure

---

## Backlog

- Dashboard trust boundary controls — per-tenant settings for high-risk
  tool classification, global deny lists, and role restrictions. Currently
  code-level config in `empla/core/tools/trust.py`. Build alongside the
  integrations dashboard (Phase 3B Step 5) as a "Trust & Security" panel.
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
mismatches (integrations, beliefs, procedural memory). Fixed intention
start/complete/fail UUID passing. Activity recorder commit fix. Dashboard:
is_running from DB status, roles trailing slash, BDI tabs (Goals, Intentions,
Beliefs endpoints + React hooks + UI). Goal/intention dedup. Belief extraction
prompt improvement. Architecture review.

---

**Last Updated:** 2026-03-20
