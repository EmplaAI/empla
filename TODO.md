# empla - Current Work Tracker

> **Purpose:** Track current priorities, state, and progress
> **Updated:** 2026-02-20
> **Roadmap:** See `docs/research/openclaw-inspired-roadmap.md` for full consolidated roadmap

---

## Current State (2026-02-20)

**Test Results:** 561 passed, 67.33% coverage
**Employees:** SalesAE, CSM (deployable)
**Capabilities:** Email (simulation), Workspace (full implementation)
**LLM Service:** Multi-provider (Anthropic, OpenAI, Vertex)

### Recently Completed
- [x] CapabilityType enum → string constants migration (PR #35)
- [x] WorkspaceCapability — Digital Desk Phase 1 (PR #36)
  - 7 operations, path security, perception, simulation support
  - 72 unit tests, 8 integration tests, 85.75% coverage
- [x] OpenClaw analysis and consolidated roadmap

---

## Active Priorities

### P0 — This Sprint

1. [ ] **BDI Lifecycle Hooks** (Track C1)
   - Hook registry with register/emit
   - All BDI cycle phases emit hooks
   - Foundation for health monitoring, manifests, extensibility

2. [ ] **LLM Provider Failover** (Track B1)
   - FailoverConfig: primary + fallback models
   - ProviderHealth tracking with cooldowns
   - Error classification (auth, rate-limit, timeout, billing)

3. [ ] **Dual-Timeout Watchdog** (Track B2)
   - Per-LLM-call timeout (60s)
   - Per-cycle timeout (5 min)
   - Tool loop detection (Track B3)

4. [ ] **Exponential Loop Backoff** (Track B6)
   - Cycle-level backoff on failure (1s → 2s → 4s → ... → 5min max)
   - Reset on success, never permanently stop

### P1 — Next Sprint

5. [ ] **ComputeCapability** (Track A2)
   - Subprocess sandbox (dev), Docker sandbox (production)
   - Workspace mounted at /workspace
   - Module blocklist for code-level security

6. [ ] **Context Window Compaction** (Track B4)
   - Token counting, auto-compaction at 80% limit
   - Summary-based strategy

7. [ ] **Microsoft Graph + Gmail Email Integration** (Track D3)
   - OAuth2 flow, real fetch/send
   - Replace EmailCapability placeholders

8. [ ] **Employee Health Monitoring** (Track B5)
   - HealthStatus model
   - Loop, capability, LLM provider checks

9. [ ] **Graceful Shutdown and State Persistence** (Track B8)
   - Save BDI state on shutdown, resume on restart
   - Process infrastructure (SIGTERM/SIGKILL, health checks) done (PR #37)

10. [x] **Employee CLI Tool** (Track F1)
    - `empla employee start/stop/status/list` (PR #37)

11. [ ] **Real Observation Sources** (Track F2)
    - Connect real perception to ProactiveExecutionLoop

### P2 — Following Sprint

12. [ ] **BrowserCapability** (Track A3)
13. [ ] **Capability Manifests** (Track C2)
14. [ ] **Calendar Capability** (Track D4)
15. [ ] **Transcript Pruning** (Track C4)

### P3 — Future

16. [ ] **Slack/Teams Messaging** (Track D5)
17. [ ] **Hot-Reload Config** (Track C5)
18. [ ] **Product Manager Employee** (Track F3)
19. [ ] **Developer Experience — Guides & Docs** (Track F4)
20. [ ] **Active Hours Gating** (Track B7)
21. [ ] **Subagent System** — Employees spawn sub-agents for delegated tasks

---

## Completed Phases

### Phase 1 — Foundation (COMPLETE)
- [x] Database schema with Alembic migrations
- [x] Core Pydantic models
- [x] BDI Engine (BeliefSystem, GoalSystem, IntentionStack)
- [x] Memory Systems (Episodic, Semantic, Procedural, Working)
- [x] Proactive Execution Loop
- [x] LLM Service with multi-provider support

### Phase 2.1 — Capability Framework (COMPLETE)
- [x] BaseCapability with retry, error classification, PII-safe logging
- [x] CapabilityRegistry lifecycle management
- [x] Integration with ProactiveExecutionLoop

### Phase 2.2 — Email Capability (CORE COMPLETE)
- [x] EmailCapability with triage, composition, actions
- [x] 22 unit tests, 95.80% coverage
- [ ] Microsoft Graph API integration (P1)

### Phase 2.4 — Employees (COMPLETE)
- [x] Base DigitalEmployee class
- [x] SalesAE, CSM employees
- [x] E2E simulation framework

### Digital Desk Phase 1 — Workspace (COMPLETE)
- [x] WorkspaceCapability with 7 operations
- [x] Path security, perception, simulation support
- [x] 72 unit + 8 integration tests

---

**Last Updated:** 2026-02-20
**Full Roadmap:** `docs/research/openclaw-inspired-roadmap.md`
