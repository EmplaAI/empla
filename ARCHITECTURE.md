# empla — Architecture

> **Last Updated:** 2026-04-11
> **Status:** Reflects current codebase (post Phase 4)

---

## What empla IS

empla is an **operating system for autonomous digital employees**. Each employee:
- Has **goals** and works toward them proactively (BDI architecture)
- **Perceives** its environment via tool calls (CRM, email, calendar)
- **Plans** strategies, **executes** intentions, **learns** from outcomes
- Runs as a **persistent process** with a continuous BDI loop

## System Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                         EMPLA SYSTEM                            │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │  Dashboard    │   │  FastAPI     │   │  Runner          │   │
│  │  (React)      │──▶│  API         │   │  (1 per employee)│   │
│  │  BDI tabs     │   │  /api/v1/    │   │  Loads MCP +     │   │
│  └──────────────┘   └──────┬───────┘   │  OAuth tokens    │   │
│                            │           └────────┬─────────┘   │
│                            │                    │              │
│  ┌─────────────────────────┴────────────────────┘              │
│  │                                                              │
│  │  ┌──────────────────────────────────────────────┐           │
│  │  │    ProactiveExecutionLoop (orchestrator)      │           │
│  │  │  ┌────────────┐ ┌─────────┐ ┌──────────────┐│           │
│  │  │  │ Perception │ │Planning │ │IntentionExec ││           │
│  │  │  │ (LLM+tools)│ │(LLM)   │ │(LLM+tools)  ││           │
│  │  │  └────────────┘ └─────────┘ └──────────────┘│           │
│  │  │  ┌────────────┐ ┌─────────┐ ┌──────────────┐│           │
│  │  │  │ Reflection │ │GoalMgmt │ │ MemoryOps    ││           │
│  │  │  │ (learning) │ │(eval)   │ │ (4 types)    ││           │
│  │  │  └────────────┘ └─────────┘ └──────────────┘│           │
│  │  └──────────────────────┬───────────────────────┘           │
│  │                         │                                    │
│  │  ┌──────────────────────┴───────────────────────┐           │
│  │  │            Trust Boundary                     │           │
│  │  │  (taint-based, global deny, role restrictions)│           │
│  │  └──────────────────────┬───────────────────────┘           │
│  │                         │                                    │
│  │  ┌──────────────────────┴───────────────────────┐           │
│  │  │            ToolRouter                         │           │
│  │  │  ├── @tool registry (native tools)            │           │
│  │  │  ├── MCP bridge (external MCP servers)        │           │
│  │  │  ├── IntegrationRouter (email, etc.)          │           │
│  │  │  ├── Health monitor (per-integration)         │           │
│  │  │  └── 30s timeout wrapper                      │           │
│  │  │                                               │           │
│  │  │  Connectors:                                  │           │
│  │  │  ├── HubSpot CRM (API v3 via httpx)           │           │
│  │  │  ├── Google Calendar (API v3 via httpx)        │           │
│  │  │  ├── Email (Gmail/Microsoft via adapter)       │           │
│  │  │  └── MCP servers (user-configured)             │           │
│  │  └──────────────────────────────────────────────┘           │
│  │                                                              │
│  │  ┌──────────────────────────────────────────────┐           │
│  │  │         PostgreSQL 17                         │           │
│  │  │  employees, beliefs, goals, intentions        │           │
│  │  │  memory (episodic, semantic, procedural,      │           │
│  │  │          working)                             │           │
│  │  │  activity, integrations, OAuth credentials    │           │
│  │  └──────────────────────────────────────────────┘           │
│  │                                                              │
│  │  ┌──────────────────────────────────────────────┐           │
│  │  │         LLM Providers                         │           │
│  │  │  Anthropic (Claude) | OpenAI | Vertex AI      │           │
│  │  │  Azure OpenAI                                 │           │
│  │  └──────────────────────────────────────────────┘           │
│  │                                                              │
└──┴──────────────────────────────────────────────────────────────┘
```

## BDI Execution Loop

The core of empla. Each cycle:

```text
┌─ PERCEIVE ──────────────────────────────────────────┐
│  LLM selects tools based on goals → tool calls →    │
│  observations → batch belief extraction             │
│  Working memory stores observations for context     │
└─────────────────────────┬───────────────────────────┘
                          ▼
┌─ UPDATE BELIEFS ────────────────────────────────────┐
│  Observations → beliefs (batch LLM call)            │
│  Direct tool-to-belief for structured data          │
│  High-confidence beliefs → semantic memory          │
│  Belief decay removes stale beliefs                 │
└─────────────────────────┬───────────────────────────┘
                          ▼
┌─ STRATEGIC PLANNING ────────────────────────────────┐
│  (When triggered by significant belief changes)     │
│  Situation analysis → gap identification →          │
│  goal creation/abandonment → plan generation        │
│  GoalRecommendation: LLM-driven abandon/reprioritize│
│  Procedural memory influences planning              │
└─────────────────────────┬───────────────────────────┘
                          ▼
┌─ GOAL MANAGEMENT ───────────────────────────────────┐
│  LLM-driven progress evaluation (batched)           │
│  Goal TTL for opportunity/problem goals             │
│  LLM completion check for non-numeric goals         │
│  Achievement detection → hook emission              │
└─────────────────────────┬───────────────────────────┘
                          ▼
┌─ INTENTION EXECUTION ───────────────────────────────┐
│  Pick highest-priority intention → feed stored plan │
│  LLM agentic tool calling → tool results            │
│  Working memory tracks current focus                │
└─────────────────────────┬───────────────────────────┘
                          ▼
┌─ REFLECTION ────────────────────────────────────────┐
│  Record execution episode → update procedural       │
│  memory → update effectiveness beliefs              │
│  Deep reflection (periodic): pattern analysis →     │
│  insights → typed beliefs + procedural memory       │
└─────────────────────────────────────────────────────┘
```

**Loop module structure** (`empla/core/loop/`):
- `execution.py` — Orchestrator (inherits all mixins)
- `perception.py` — Environment scanning via LLM tools
- `planning.py` — Strategic reasoning, situation analysis
- `goal_management.py` — Progress evaluation, achievement
- `intention_execution.py` — Agentic tool calling
- `reflection.py` — Learning, procedural memory, deep reflection
- `events.py` — `EventMonitoringSystem` for threshold / time-based / external triggers (used by the orchestrator, not a mixin)
- `protocols.py` — Protocol interfaces for BDI components
- `models.py` — Pydantic data models

## Key Subsystems

### Memory (4 types, all wired into loop)

| Type | Purpose | DB-backed | Used in |
|------|---------|-----------|---------|
| **Episodic** | Specific experiences, events | Yes | Recording + recall |
| **Semantic** | Facts, knowledge (promoted from beliefs) | Yes | Planning context |
| **Procedural** | Skills, what works/doesn't | Yes | Plan generation |
| **Working** | Short-term context, current focus | Yes | Perception + execution |

### Tool System

```text
ToolRouter
├── TrustBoundary (taint-based validation)
│   ├── Global deny list (destructive ops — always blocked)
│   ├── Rate limit (50 calls/cycle)
│   └── Role restrictions (activated after tainted by email/messages)
├── Timeout wrapper (30s default)
├── Health monitor (per-integration success/failure/latency)
├── ToolRegistry (@tool decorated functions)
├── MCP bridge (external MCP servers via stdio/HTTP)
└── IntegrationRouter (email, HubSpot, Calendar connectors)
```

### Connectors (direct API, no adapter abstraction)

| Connector | API | Tools |
|-----------|-----|-------|
| **HubSpot** | API v3 via httpx | 7: pipeline metrics, deals CRUD, contacts CRUD, search |
| **Google Calendar** | API v3 via httpx | 5: events CRUD, availability (FreeBusy) |
| **Email** | Gmail/Microsoft via adapter | 6: send, reply, forward, get unread, mark, archive |
| **MCP servers** | User-configured | Discovered at connection time |

### OAuth & Credentials

- `CredentialInjector` resolves tokens once at runner startup (not continuously refreshed during runtime)
- `TokenManager` encrypts/decrypts credentials (Fernet AES-128-CBC)
- Near-expiry tokens refreshed during startup resolution (5-minute buffer)
- stdio MCP servers receive `OAUTH_ACCESS_TOKEN` env var at startup
- HTTP MCP servers receive `Authorization: Bearer` header at startup
- Long-running processes may need restart for token renewal (TODO: in-loop refresh)

### Employee Types

| Type | Role | Status |
|------|------|--------|
| **SalesAE** | Pipeline building, prospecting, deal progression | Implemented |
| **CSM** | Customer success, health monitoring, onboarding | Implemented |
| **ProductManager** | Backlog prioritization, release notes | Implemented |
| **SDR** | Lead qualification, outbound prospecting | Implemented |
| **Recruiter** | Sourcing, screening, outreach | Implemented |

All inherit from `CatalogBackedEmployee` (a `DigitalEmployee` subclass) that
reads defaults from `ROLE_CATALOG` via a `role_code` class attribute and
templatizes startup/shutdown belief + episode recording. Employee behavior is
defined by:
- **Personality** (from role catalog)
- **Default goals** (from role catalog)
- **Identity** (name, role, personality → LLM system prompt)

### Dashboard

React app with tabs: Activity | Goals | Intentions | Beliefs
- Employee list with status
- BDI state visualization per employee
- Integration management (OAuth, MCP servers)
- Settings

### API

FastAPI at `/api/v1/`:
- `/employees/` — CRUD + control (start/stop/pause)
- `/bdi/{employee_id}/` — goals, intentions, beliefs
- `/activity/` — activity feed with filters
- `/integrations/` — OAuth + MCP server management
- `/roles/` — role catalog
- `/auth/` — JWT authentication (HS256, login + /me)

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+, AsyncIO |
| Web | FastAPI |
| Database | PostgreSQL 17 (relational + JSONB + pgvector) |
| ORM | SQLAlchemy 2.0, Alembic migrations |
| Validation | Pydantic v2 |
| LLM | Anthropic Claude, OpenAI, Vertex AI, Azure OpenAI |
| HTTP client | httpx (for HubSpot, Google Calendar) |
| MCP | Model Context Protocol (stdio + HTTP) |
| Frontend | React + TypeScript |
| Testing | pytest (1895 unit tests, ~70% unit coverage) |
| Linting | ruff |
| Type checking | mypy |
| Package manager | uv |

## Project Structure

```text
empla/
├── api/                    # FastAPI endpoints
│   └── v1/endpoints/       # employees, bdi, activity, integrations
├── bdi/                    # BDI engine
│   ├── beliefs.py          # BeliefSystem (LLM-driven extraction + decay)
│   ├── goals.py            # GoalSystem (progress, achievement, TTL)
│   └── intentions.py       # IntentionStack (plan generation, execution)
├── core/
│   ├── hooks.py            # BDI lifecycle hook registry
│   ├── loop/               # Proactive execution loop (7 modules)
│   ├── memory/             # 4 memory systems
│   ├── telemetry/          # BDI trajectory telemetry
│   └── tools/              # ToolRouter, trust boundary, health, MCP bridge
├── employees/              # Employee types (SalesAE, CSM, PM, SDR, Recruiter)
│   ├── base.py             # DigitalEmployee abstract base class
│   ├── catalog_backed.py   # CatalogBackedEmployee (shared startup template)
│   ├── catalog.py          # Role catalog (single source of truth)
│   └── identity.py         # LLM prompt identity
├── integrations/           # External service connectors
│   ├── hubspot/            # HubSpot CRM (direct httpx)
│   ├── google_calendar/    # Google Calendar (direct httpx)
│   ├── email/              # Gmail/Microsoft email
│   └── router.py           # IntegrationRouter pattern
├── llm/                    # LLM provider abstraction
├── models/                 # SQLAlchemy database models
├── runner/                 # Employee process entry point
├── services/               # Business services
│   ├── activity_recorder.py
│   ├── employee_manager.py
│   └── integrations/       # OAuth, tokens, MCP, credentials
└── settings.py             # Centralized settings (pydantic-settings)
```

## Phase 4 — Shipped (2026-03-25 to 2026-04-10)

Phase 4 (Efficiency + Intelligence) added four major subsystems:

- **Playbook system with autonomous discovery** (PR #73): procedures that
  demonstrate consistent success (3+ executions, 70%+ success rate) are
  automatically promoted to playbooks. During planning, available playbooks
  are presented as context options to the LLM, which decides whether to reuse,
  adapt, or ignore them. Playbook success feedback loop updates success_rate
  from execution outcomes. Auto-demotes playbooks with <50% success after 5+
  runs. Fields: `is_playbook`, `promoted_at` on `ProceduralMemory`.
- **Event-driven wake + scheduled actions** (PR #74): the loop uses
  `self._wake_event` (asyncio.Event) to interrupt inter-cycle sleep. Scheduled
  actions are stored as `WorkingMemory` items with `subtype="scheduled_action"`
  and injected as observations when due. Recurring actions re-schedule
  themselves. Also adds `_check_pending_events` for external event drain.
- **Webhooks with credential-based routing** (PR #75): public
  `/api/v1/webhooks/{provider}` endpoints authenticate via `X-Webhook-Token`
  (stored in `Integration.oauth_config["webhook_token"]`, constant-time
  comparison). Events are routed to employees with matching
  `IntegrationCredential` for the provider. Tenant-level credentials wake all
  active employees. HealthServer has a `/wake` endpoint that drains events
  into the loop's working memory.
- **Dashboard cost panel + playbook viewer** (PR #76): React panels for
  per-cycle cost visualization and playbook list with stats.

**Also shipped in the ml-workflow merge:**

- **LLM routing layer** (`empla/llm/router.py`): rule-based model selection
  across 11 signals (task type, priority, context length, retry escalation,
  circuit breaker, soft/hard budget, etc.). Per-owner budget tracking via
  `defaultdict[str, float]` keyed on `owner_id` (employee ID). Used by the
  `LLMService` when routing is enabled.

## What's NOT Built Yet

See `TODO.md` for the full roadmap. Phase 5 is the current work.

Key items still deferred:

- **LLM failover** — primary + fallback with ProviderHealth tracking (Phase 6)
- **Context window compaction** — token counting, auto-compaction (Phase 6)
- **Timeouts/watchdogs** — per-call + per-cycle limits (Phase 6)
- **Graceful shutdown & state persistence** (Phase 6)
- **Multi-employee coordination** — handoff protocols
- **empla-native workspace** — contacts/pipeline/tasks as first-class data
- **Password/OAuth verification on login** (still backlog)
- **Paused-employee event loss** — `HealthServer._pending_events` deque has
  maxlen=100, events while paused can drop. Pre-existing, noted in Phase 5 TODOs.

## Design Decisions

1. **BDI over task queues** — Employees reason about goals, not execute task lists
2. **Direct connectors over adapters** — HubSpot/Calendar call APIs directly via httpx. No premature abstraction.
3. **Taint-based trust boundary** — Structured data (CRM) passes freely. Role restrictions activate only after processing untrusted content (email).
4. **Mixin pattern for loop** — Execution loop split into modules via Python mixins (`perception.py`, `planning.py`, `goal_management.py`, `intention_execution.py`, `reflection.py`). Orchestrator (`execution.py`) is ~960 lines. `events.py` is a separate subsystem consumed by the orchestrator, not a mixin.
5. **Single tenant per process** — Runner spawns one process per employee. Module-level state is safe.
6. **PostgreSQL for everything** — Relational + JSONB + pgvector. No separate vector DB, graph DB, or cache until proven necessary.

## Future Vision

The original founding vision (Oct 2025) is preserved in `docs/design/future-vision.md`.
It contains aspirational concepts like WebRTC meeting participation, knowledge graphs,
A2A protocol, behavioral cloning, and marketplace — ideas worth revisiting as the
platform matures.
