# empla — Architecture

> **Last Updated:** 2026-03-20
> **Status:** Reflects current codebase (post Phase 3B)

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
│  Procedural memory influences planning              │
└─────────────────────────┬───────────────────────────┘
                          ▼
┌─ GOAL MANAGEMENT ───────────────────────────────────┐
│  LLM-driven progress evaluation (batched)           │
│  Goal TTL for opportunity/problem goals             │
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
│  insights stored + read back into planning          │
└─────────────────────────────────────────────────────┘
```

**Loop module structure** (`empla/core/loop/`):
- `execution.py` — Orchestrator (inherits all mixins)
- `perception.py` — Environment scanning via LLM tools
- `planning.py` — Strategic reasoning, situation analysis
- `goal_management.py` — Progress evaluation, achievement
- `intention_execution.py` — Agentic tool calling
- `reflection.py` — Learning, procedural memory, deep reflection
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

Both inherit from `DigitalEmployee` base class. Employee behavior is defined by:
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
- `/auth/` — placeholder (TODO: real JWT)

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
| Testing | pytest (787 tests) |
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
├── employees/              # Employee types (SalesAE, CSM)
│   ├── base.py             # DigitalEmployee base class
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

## What's NOT Built Yet

See `TODO.md` for the full roadmap. Key items:

- **Prometheus metrics** — TODO markers in loop code, health monitor exists
- **Production auth** — placeholder JWT, no real authentication
- **LLM failover** — primary + fallback models
- **Adaptive cycle frequency** — currently fixed interval
- **Playbook system** — codified tool sequences
- **Event-driven triggers** — react to changes instead of polling
- **Multi-employee coordination** — handoff protocols
- **empla-native workspace** — contacts/pipeline/tasks as first-class data

## Design Decisions

1. **BDI over task queues** — Employees reason about goals, not execute task lists
2. **Direct connectors over adapters** — HubSpot/Calendar call APIs directly via httpx. No premature abstraction.
3. **Taint-based trust boundary** — Structured data (CRM) passes freely. Role restrictions activate only after processing untrusted content (email).
4. **Mixin pattern for loop** — Execution loop split into 7 focused modules via Python mixins. Orchestrator is 715 lines.
5. **Single tenant per process** — Runner spawns one process per employee. Module-level state is safe.
6. **PostgreSQL for everything** — Relational + JSONB + pgvector. No separate vector DB, graph DB, or cache until proven necessary.

## Future Vision

The original founding vision (Oct 2025) is preserved in `docs/design/future-vision.md`.
It contains aspirational concepts like WebRTC meeting participation, knowledge graphs,
A2A protocol, behavioral cloning, and marketplace — ideas worth revisiting as the
platform matures.
