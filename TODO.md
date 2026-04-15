# empla - Roadmap

> **Updated:** 2026-04-14
> **Strategy:** Phase 4 (Efficiency + Intelligence) shipped. Phase 5A complete:
> PR #77 (foundation), PR #78 (PM/SDR/Recruiter), PR #79 (memory API + 4-group
> tabs), PR #80 (tool catalog + trust boundary view + runner auth) shipped.
> Phase 5B in progress: PR #81 (webhook UI) + PR #82 (scheduler) + PR #83
> (settings + runner-restart) shipped — 3 more Phase 5B PRs remain.
> **Reference:** `ARCHITECTURE.md`, `DESIGN.md`, `docs/designs/phase5-platform-completeness.md`

---

## Current State

Tests: **1814 unit tests passing** (0 failing), ~70% coverage on unit test scope |
Employees: SalesAE, CSM, ProductManager, SDR, Recruiter (all 5 catalog roles implemented) |
Core features: Complete BDI loop, playbook system with autonomous discovery,
event-driven wake + scheduled actions, webhooks with credential-based routing,
LLM routing layer with cost tracking, cost panel + playbook viewer in dashboard.
Direct HubSpot CRM, Google Calendar, and Email connectors via httpx.
JWT auth, trust boundary, integration health monitoring.

---

## Phase 5 — Platform Completeness + Employee Polish (in progress)

Direction: "features first, make sure the employee works, everything is exposed,
people can create new employees." See `docs/designs/phase5-platform-completeness.md`
for the full plan. Reviewed by CEO + Eng + Design; scored 8/10 design completeness.

### Phase 5A — Core Completeness (4 PRs)

- **PR #77 — Foundation** ✓ SHIPPED 2026-04-11: docs housekeeping, critical cost
  metrics hotfix (execution.py:886 silent no-op bug from Phase 4), 16 pre-existing
  test failures fixed (LLM router + service tests), DESIGN.md creation, Button
  a11y fix (44×44px WCAG 2.5.5), reduced-motion support
- **PR #78** ✓ SHIPPED 2026-04-14: CatalogBackedEmployee refactor + PM, SDR,
  Recruiter classes. +101 unit tests, trust-boundary enum completeness fix.
  Deferred to follow-up: DRY draft_* refactor, deepcopy on frozen Personality,
  prioritize_backlog/prioritize_accounts dropping LLM output.
- **PR #79** ✓ SHIPPED 2026-04-14: Memory browsing API (4 paginated endpoints)
  + 4-group tab restructure (ACTIVITY/MIND/BUSINESS, OPERATIONS deferred to
  PR #80/#82). +40 unit tests. New idx_semantic_employee_confidence index.
  Working memory hard-capped at 200 items defensively. Deferred to follow-up:
  DRY pagination helper, type triplication (openapi-typescript), pager touch
  targets (pre-existing 28px pattern across all panels), validation enum-set
  duplication from model CHECK constraints, ProceduralMemoryPanel wiring
  (lands in PR #84 playbook editor).
- **PR #80** ✓ SHIPPED 2026-04-14: Tool catalog + per-employee tool health +
  trust boundary view + runner shared-secret auth (closes pre-existing /wake
  trust gap from PR #74). +53 unit tests. New OPERATIONS tab group completes
  the 4-group employee detail layout. Boil-the-lake review: 14 fixes applied
  including N+1 elimination, last_error redaction, generic DataPanel.

### Phase 5B — User Power + Visibility (6 PRs)

- **PR #81** ✓ SHIPPED 2026-04-14: Webhook UI + event feed + setup wizards.
  Token mgmt on existing Integration.oauth_config JSONB (no new table), 5-min
  grace-window rotation (freezegun test), events feed reuses AuditLog with
  widened actor_type CHECK + partial expression index on
  details->>'provider'. Dashboard /events route: token manager with inline
  Target URL, once-only token dialog with beforeunload guard, 15s-autorefresh
  event stream, HubSpot/Calendar/Gmail wizards. +19 unit tests. Boil-the-lake
  review: 12 fixes applied including PII scrub, SELECT FOR UPDATE on
  create/rotate/delete, create-409 on existing token, LIKE→JSONB filter fix,
  setState-during-render fix, downgrade fail-loud.
- **PR #82** ✓ SHIPPED 2026-04-15: Scheduler panel (read + cancel + tagged
  user-requested add). 3 new endpoints over existing WorkingMemory
  scheduled_action rows (no new table). Source-aware perception prefix
  (USER-REQUESTED vs SCHEDULED ACTION DUE). Cycle-top rollback + commit
  so API-written rows are visible through the loop's long-lived session.
  Dashboard SchedulerPanel wired as OPERATIONS sub-tab. +17 unit tests.
  Boil-the-lake review: 9 fixes incl. scheduled-action capacity
  protection, SQL-level GET filter, recurring cadence anchor,
  idempotent DELETE, pre-existing TTL-bug fix for delays > 1h.
- **PR #83** ✓ SHIPPED 2026-04-15: Real settings page (LLM, cost, cycle, trust
  read-only, notifications, sales) with runner-restart reload pattern. New
  `restarting` employee status (migration j5e6f7g8h9i0) + `restart_all_for_tenant`
  fans out stop+respawn so fresh Tenant.settings are read at process startup.
  Admin-only PUT, optimistic locking via expected_version, corrupt-JSONB backup,
  Pydantic `extra='forbid'` rejects unknown sections. Killed hubspot/tools.py:150
  hardcoded 100k quarterly target (runner-side integration init wire-up lands
  later). +22 unit tests. Boil-the-lake review: 9 fixes incl. admin role check,
  optimistic locking, stuck-restarting recovery, cycle floor raise.
  **Deferred to PR #86:** cost hard-stop enforcement (needs inbox for the "why
  did my employee pause?" message).
- **PR #84** — Playbook editor with optimistic locking (version column on
  ProceduralMemory, bumped by both API + autonomous promotion path)
- **PR #85** — Custom role builder with admin review gate (GenericEmployee for
  runtime resolution)
- **PR #86** — Inbox (employee→human messaging with structured content blocks)

**Total:** 10 PRs, ~7-9 days CC time. Phase 5 adds ~200 new tests across the
per-PR budgets (`#77=5`, `#78=60`, `#79=25`, `#80=10`, `#81=15`, `#82=12`,
`#83=15`, `#84=20`, `#85=20`, `#86=18`), bringing the target to ~1840 unit
tests passing from the current 1644 unit-test-only baseline. (Earlier 2091
target from the CEO plan was computed against a 1896 total-collection
baseline that mixed unit + integration + e2e; the honest unit-only delta is
~200.)

---

## Phase 6 — Production Resilience (deferred from Phase 5)

Direction to be decided after Phase 5 ships. Candidates from CEO review:

- LLM failover — primary + fallback models, ProviderHealth tracking
- Context window compaction — token counting, auto-compaction
- Timeouts/watchdogs — per-call + per-cycle timeouts, loop detection
- Graceful shutdown & state persistence — save/resume BDI state
- Exponential loop backoff — cycle-level backoff on failure
- Paused-employee event loss fix (bump HealthServer._pending_events maxlen=100
  or persist events to DB)

Alternative directions also in the backlog:
- **Native Workspace** — empla-owned contacts, pipeline, tasks (competitive moat)
- **"Hire One" production sprint** — deploy one real employee against a real
  pipeline to validate the full platform

---

## Backlog

- Password/OAuth verification on login — User model needs password field,
  bcrypt hashing, or OAuth/SAML flow. Required before multi-tenant production.
- Token revocation — jti claim, revocation list for compromised tokens
- Rate limiting on auth endpoints
- Observation prioritization — let perception LLM classify importance
- Structured world model — replace SPO belief triples with typed domain model
- Goal-task trees — hierarchical decomposition instead of flat goals + intentions
- Active hours gating — configurable work schedule
- Hot-reload config without DB roundtrip — in-memory pub/sub invalidation
  (alternative to the runner-restart pattern chosen in Phase 5)
- Multi-employee coordination — handoff protocols, shared beliefs
- Embedding-based procedure search — pgvector similarity
- Daily digest (tenant-level scheduler) — for inbox summaries
- Trust rule editing UI (needs trust language design review first)
- Custom webhook setup wizards for providers beyond HubSpot/Calendar/Gmail
- Developer experience docs — guides for creating custom employees

### Testing gaps surfaced in PR #77 review (deferred)

Specialist reviewers flagged these coverage improvements. Each is a small,
self-contained addition — bundle them into a follow-up "test hardening" PR:

- Per-owner LLM budget isolation test — `tests/unit/test_llm_router.py` has
  no test that `record_cost("gemini-2.0-flash", usage, owner_id="emp-A")`
  updates `_cycle_cost["emp-A"]` without affecting `_cycle_cost["emp-B"]`.
  If owner_id is silently ignored in a future refactor (always writes
  "default"), concurrent employees' budgets would cross-contaminate in
  production. Related: `reset_cycle_budget("emp-A")` should NOT reset "emp-B".
- Exception-swallowing branch test — `execution.py:946` `except Exception`
  in `_record_cycle_metrics` swallows errors silently at `logger.debug` level.
  No test covers this branch. If `record_cycle_metrics` starts raising
  (schema mismatch, constraint violation), metrics silently stop persisting
  again. Add test that patches `record_cycle_metrics` to raise, asserts
  `_record_cycle_metrics` does not propagate and `_previous_tool_stats`
  cache is NOT advanced.
- Restore no-fallback cost tracking test case — `test_llm_service_coverage.py`
  had a `test_no_fallback_model_config` test that was dropped during the
  `_track_cost → _track_cost_for_model` rename. The "fallback not configured,
  cost tracking still works for primary model" path is no longer covered.
- `_previous_tool_stats` autouse fixture — module-global dict in
  `empla/services/metrics.py` is not cleared between tests outside
  `test_metrics_service.py`. Add an `autouse=True` fixture that clears
  the dict to prevent future cross-test state leaks.
- Stricter regression test locks for sessionmaker — the current
  `test_record_cycle_metrics_ignores_sessionmaker_on_employee_row` test
  covers the exact `getattr(self.employee, "_sessionmaker")` regression.
  If a future refactor pulls sessionmaker from a third location (e.g.
  `self.employee.owner._sessionmaker`), the test wouldn't catch it. Add a
  positive assertion that `self._sessionmaker` is the SOLE source read.
- goal_type edge case tests for `find_procedures_for_situation` —
  `planning.py:723` uses `getattr(goal, "goal_type", "")`. No test verifies
  the empty-string fallback or unicode goal_types, which are valid per the
  "strings over enums for agent-facing interfaces" convention.
- `size="sm"` usage audit — DESIGN.md says `sm` is for "dense non-touch
  contexts" but `size="sm"` is used in non-dense primary actions
  (`routes/integrations.tsx:87` "Add Server" CTA, stats-cards retry buttons,
  settings.tsx "Manage Integrations" link). Either bump these to default
  size OR relax the DESIGN.md language to match actual usage.

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
tool calling, role catalog as single source of truth, test infrastructure,
activity recorder for dashboard feed

**Phase 3A — Platform Solidification (PR #58, #59):**
Removed old capabilities system, completed agentic execution, LLM-driven goal
evaluation + achievement hooks, procedural memory recording + maintenance +
plan influence

**Phase 3A.5 — E2E Validation (2026-03-17/18):**
Full E2E test with production code + test MCP servers. Runner wires MCP servers
from DB. Vertex AI schema sanitization. Dashboard BDI tabs. Goal/intention dedup.

**Phase 3B — Real-World Integrations (PRs #61-#67, 2026-03-19/20):**
Direct HubSpot CRM + Google Calendar + Email connectors via httpx. OAuth
credential injection at startup. LLM trust boundary (taint-based, global deny,
role restrictions). Integration health monitoring with BDI belief generation.
Execution loop refactored into 7 focused modules via mixin pattern.

**Phase 3C — BDI Loop Completion (PR #68, 2026-03-24):**
GoalRecommendation wired into strategic planning. Deep reflection insights
converted to typed beliefs and procedural memory. Non-numeric goal LLM
completion checks alongside TTL.

**Production Foundation — JWT Auth (PR #69, 2026-03-24):**
Replaced stub tokens with JWT (HS256). Production guards, unified error
messages, PyJWTError catch.

**Phase 3C.5 — Metrics & Coverage (PR #71, #72, 2026-03-24):**
Dashboard-native cycle metrics (persisted to Metric table). Test coverage
push. NOTE: cycle metrics had a latent bug where `_sessionmaker` was read
from the wrong object, causing silent no-op in production — fixed in PR #77.

**Phase 4 — Efficiency + Intelligence (PRs #73-#76, 2026-03-25 to 2026-04-10):**
Playbook system with autonomous discovery (#73). Event-driven wake + scheduled
actions (#74). Webhooks with credential-based routing (#75). Dashboard cost
panel + playbook viewer (#76). Also: LLM routing layer with rule-based model
selection (merged from ml-workflow branch).

---

**Last Updated:** 2026-04-11
