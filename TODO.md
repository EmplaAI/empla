# empla - Roadmap

> **Updated:** 2026-03-16
> **Strategy:** The brain works. Now make it solid — clean up dead code,
> complete the agentic loop, wire goal achievement, activate learning.
> Platform solidification before new integrations.

---

## Current State

Tests: 799 passed, 61% full-codebase coverage | Employees: SalesAE, CSM
Working: BDI loop runs, LLM-driven perception (agentic tool checking), strategic
planning generates goals, agentic execution calls tools via ToolRouter, MCP bridge
connects external tool servers, activity recording feeds dashboard, goal
achievement detection, procedural memory recording + maintenance.
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

### 3. Wire goal achievement — PARTIAL

**Done:** Added `_check_goal_achievement()` to `execution.py` — compares
`progress[metric] >= target[value]` after each progress update and calls
`complete_goal()` for achievement goals. "Maintain" goals log success but
stay active. Added `GoalSystem.get_pursuing_goals()` to query both active
and in_progress goals (the old code only checked active goals, so goals
that transitioned to in_progress were never re-evaluated).

**Remaining:**
- The brittle substring matching in `_evaluate_goal_progress_from_beliefs`
  should be replaced with LLM-driven evaluation
- Goal achievement should emit a hook or create an activity record
- Integration tests verifying full goal lifecycle
  (active → in_progress → completed)

### 4. Activate learning (procedural memory → execution) — PARTIAL

**Done:** Fixed the signature mismatch in `_update_procedural_memory` —
now correctly calls `record_procedure(name=, steps=, outcome=, success=,
execution_time=, context=)`. Wired `reinforce_successful_procedures` and
`archive_poor_procedures` into `_maintain_memory_health()` during deep
reflection. Added procedural memory lookup in
`_generate_plans_for_unplanned_goals` — queries past successful procedures
and includes them in the LLM context when generating plans.

**Remaining:**
- Integration tests verifying procedures are recorded, retrieved, and
  influence planning
- Embedding-based similarity search for procedure retrieval (currently
  uses `find_procedures_for_situation` which does dict matching)

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

**Last Updated:** 2026-03-16
