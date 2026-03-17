# empla - Roadmap

> **Updated:** 2026-03-17
> **Strategy:** The brain works. Now make it solid — clean up dead code,
> complete the agentic loop, wire goal achievement, activate learning.
> Platform solidification before new integrations.

---

## Current State

Tests: 780 passed, 57% full-codebase coverage | Employees: SalesAE, CSM
Working: BDI loop runs, LLM-driven perception (agentic tool checking), strategic
planning generates goals, agentic execution calls tools via ToolRouter, MCP bridge
connects external tool servers, activity recording feeds dashboard, LLM-driven goal
progress evaluation + achievement detection + hook emission, procedural memory
recording + maintenance + plan influence.
Dashboard: Employees, Activity, Integrations (OAuth + MCP servers), Settings

---

## Phase 3A: Platform Solidification

The immediate priority. Make what exists actually work end-to-end before
adding more integrations.

### 1. ~~Remove old capabilities system~~ DONE

Deleted `empla/capabilities/base.py`, `registry.py`, `email.py`,
`workspace.py`, `compute.py`. Moved `ActionResult` to
`empla/core/tools/base.py`. Removed `CapabilityRegistry`,
`_init_capabilities`, `capability_registry` param, and capability shutdown
from `employees/base.py`. Kept `default_capabilities` as role metadata.
Deleted 8 test files, updated remaining tests.

### 2. ~~Complete agentic execution~~ DONE

Removed rigid sequential step fallback (`_execute_plan_step`,
`_execute_step_via_tool_router`) from `execution.py`.
`_execute_intention_plan` now requires LLM + tools and returns clear errors
when either is missing. Updated tests.

### 3. ~~Wire goal achievement~~ DONE

Replaced brittle `_evaluate_goal_progress_from_beliefs` (substring matching)
with LLM-driven `_evaluate_goals_progress` that batches all pursuing goals
into a single `generate_structured` call. Heuristic fallback when LLM is
unavailable. Added `HOOK_GOAL_ACHIEVED` hook emitted on successful
`complete_goal()`. `ActivityRecorder` records `GOAL_ACHIEVED` events
(importance=1.0). Integration tests cover LLM evaluation, heuristic
fallback, achievement lifecycle, hook emission, and activity recording.

### 4. ~~Activate learning (procedural memory → execution)~~ DONE

Fixed signature mismatch in `_update_procedural_memory`. Wired
`reinforce_successful_procedures` and `archive_poor_procedures` into
`_maintain_memory_health()`. Procedural memory lookup in
`_generate_plans_for_unplanned_goals` queries past procedures and includes
them in LLM context. Integration tests cover procedure recording (success
+ failure), trigger conditions with goal context, per-tool result accuracy,
procedure lookup during planning, and memory maintenance (reinforcement +
archival).

---

## Phase 3B: Core Integrations

After the platform is solid, add the integrations that make employees
useful in the real world.

### 1. CRM adapter (HubSpot / Salesforce)

MCP server or native tool that gives employees read/write access to CRM
data — contacts, deals, pipeline stages. Required for SalesAE and CSM
to do real work.

### 2. Calendar adapter (Google Calendar)

Read/write calendar events. OAuth infrastructure already exists for Google.
Needed for scheduling meetings, checking availability, time-aware planning.

### 3. Gmail send completion

Gmail receive works (via MCP bridge). Send is declared but not implemented.
Complete the send path so employees can actually respond to emails.

---

## Backlog

- LLM failover — primary + fallback models, ProviderHealth tracking
- Timeouts/watchdogs — per-call + per-cycle timeouts, loop detection
- Context window compaction — token counting, auto-compaction
- Employee health monitoring — HealthStatus model
- Graceful shutdown & state persistence — save/resume BDI state
- Exponential loop backoff — cycle-level backoff on failure
- Transcript pruning — compact idle transcripts
- Active hours gating — configurable work schedule
- Hot-reload config — update without restart
- Multi-employee coordination — handoff protocols, shared beliefs
- New employee types (PM) — prove platform extensibility
- Embedding-based procedure search — pgvector similarity for
  `find_procedures_for_situation` (currently dict-matching)
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

---

**Last Updated:** 2026-03-17
