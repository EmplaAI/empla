# Database Schema Design

> **Status:** Draft
> **Author:** Claude Code
> **Date:** 2025-10-27
> **Phase:** Phase 1 - Core Infrastructure

---

## Overview

This document defines the PostgreSQL database schema for empla's core system. The schema supports:
- Digital employee profiles and lifecycle management
- BDI (Belief-Desire-Intention) cognitive architecture
- Multi-layered memory systems (episodic, semantic, procedural, working)
- Multi-tenant row-level security
- Extensibility for future capabilities

**Design Principles:**
1. **Multi-tenant by default** - All tables have `tenant_id` with RLS policies
2. **JSONB for flexibility** - Complex nested data uses JSONB for schema evolution
3. **Indexes for performance** - All foreign keys, search fields, and JSONB paths indexed
4. **Audit trail** - All tables have `created_at`, `updated_at`, `deleted_at` (soft delete)
5. **Type safety** - ENUMs for constrained values, CHECK constraints for validation
6. **Extensibility** - Metadata columns (`metadata JSONB`) for custom fields

---

## Schema Overview

```sql
-- Core entities
employees               -- Digital employee profiles
employee_goals          -- Current goals (BDI Desires)
employee_intentions     -- Active plans (BDI Intentions)

-- Memory systems
memory_episodes         -- Episodic memory (events, interactions)
memory_semantic         -- Semantic memory (facts, knowledge)
memory_procedural       -- Procedural memory (skills, procedures)
memory_working          -- Working memory (current context)

-- Beliefs (world model)
beliefs                 -- Current beliefs about the world
belief_history          -- Historical belief changes (for learning)

-- Multi-tenancy
tenants                 -- Customer organizations
users                   -- Human users (for authentication/authorization)

-- Audit & observability
audit_log               -- All significant actions (compliance, debugging)
metrics                 -- Time-series metrics (performance, usage)
```

---

## Core Tables

### `tenants` - Multi-tenant Isolation

```sql
CREATE TABLE tenants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    slug                TEXT NOT NULL UNIQUE,  -- URL-safe identifier
    settings            JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    CHECK (slug ~ '^[a-z0-9-]+$'),  -- Lowercase alphanumeric + hyphens
    CHECK (status IN ('active', 'suspended', 'deleted'))
);

CREATE INDEX idx_tenants_slug ON tenants(slug) WHERE deleted_at IS NULL;
CREATE INDEX idx_tenants_status ON tenants(status) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own tenant
CREATE POLICY tenant_isolation ON tenants
    USING (id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- `slug`: Human-readable identifier for URLs (`acme-corp`, not UUID)
- `settings`: Tenant-specific configuration (LLM preferences, branding, etc.)
- `status`: Soft-delete via status change (preserves audit trail)
- RLS Policy: All queries filtered by `current_setting('app.current_tenant_id')`

---

### `users` - Human Users

```sql
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email               TEXT NOT NULL,
    name                TEXT NOT NULL,
    role                TEXT NOT NULL,  -- 'admin', 'manager', 'user'
    settings            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    UNIQUE(tenant_id, email),
    CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'),
    CHECK (role IN ('admin', 'manager', 'user'))
);

CREATE INDEX idx_users_tenant ON users(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_email ON users(tenant_id, email) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_tenant_isolation ON users
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- `tenant_id`: Isolates users by tenant (<user@acme.com> vs <user@competitor.com> are different)
- `role`: Authorization level (admin > manager > user)
- `settings`: User preferences (notification settings, UI preferences)

---

### `employees` - Digital Employee Profiles

```sql
CREATE TABLE employees (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Identity
    name                TEXT NOT NULL,
    role                TEXT NOT NULL,  -- 'sales_ae', 'csm', 'pm', 'custom'
    email               TEXT NOT NULL,
    personality         JSONB NOT NULL DEFAULT '{}',

    -- Lifecycle
    status              TEXT NOT NULL DEFAULT 'onboarding',
    lifecycle_stage     TEXT NOT NULL DEFAULT 'shadow',
    onboarded_at        TIMESTAMPTZ,
    activated_at        TIMESTAMPTZ,

    -- Configuration
    config              JSONB NOT NULL DEFAULT '{}',
    capabilities        TEXT[] NOT NULL DEFAULT '{}',

    -- Performance
    performance_metrics JSONB NOT NULL DEFAULT '{}',

    -- Audit
    created_by          UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    UNIQUE(tenant_id, email),
    CHECK (status IN ('onboarding', 'active', 'paused', 'terminated')),
    CHECK (lifecycle_stage IN ('shadow', 'supervised', 'autonomous')),
    CHECK (role IN ('sales_ae', 'csm', 'pm', 'sdr', 'recruiter', 'custom'))
);

CREATE INDEX idx_employees_tenant ON employees(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_employees_status ON employees(tenant_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_employees_role ON employees(tenant_id, role) WHERE deleted_at IS NULL;
CREATE INDEX idx_employees_lifecycle ON employees(lifecycle_stage) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;

CREATE POLICY employees_tenant_isolation ON employees
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- `role`: Pre-built employee types + custom
- `personality`: JSONB for personality traits (tone, communication style, risk tolerance)
- `status`: Current operational status (paused employees don't execute loops)
- `lifecycle_stage`: Learning progression (shadow → supervised → autonomous)
- `config`: Employee-specific configuration (loop interval, LLM model, etc.)
- `capabilities`: Array of capability identifiers (`["email", "calendar", "research"]`)
- `performance_metrics`: Time-series aggregates (goals achieved, tasks completed, etc.)

**Example `personality` JSONB:**
```json
{
  "tone": "professional",
  "risk_tolerance": "moderate",
  "communication_style": "direct",
  "traits": ["persistent", "analytical", "empathetic"]
}
```

**Example `config` JSONB:**
```json
{
  "loop_interval_seconds": 300,
  "llm_model": "claude-3-7-sonnet-20250219",
  "max_concurrent_tasks": 5,
  "working_hours": {
    "timezone": "America/Los_Angeles",
    "start": "09:00",
    "end": "17:00"
  }
}
```

---

## BDI Architecture Tables

### `employee_goals` - Desires/Goals

```sql
CREATE TABLE employee_goals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

    -- Goal definition
    goal_type           TEXT NOT NULL,  -- 'achievement', 'maintenance', 'prevention'
    description         TEXT NOT NULL,
    priority            INTEGER NOT NULL DEFAULT 5,  -- 1-10 scale

    -- Target & measurement
    target              JSONB NOT NULL,  -- Goal-specific target metrics
    current_progress    JSONB NOT NULL DEFAULT '{}',

    -- Lifecycle
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    abandoned_at        TIMESTAMPTZ,
    deleted_at          TIMESTAMPTZ,

    CHECK (priority BETWEEN 1 AND 10),
    CHECK (status IN ('active', 'in_progress', 'completed', 'abandoned', 'blocked')),
    CHECK (goal_type IN ('achievement', 'maintenance', 'prevention'))
);

CREATE INDEX idx_goals_employee ON employee_goals(employee_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_goals_priority ON employee_goals(employee_id, priority DESC) WHERE status = 'active';
CREATE INDEX idx_goals_tenant ON employee_goals(tenant_id) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE employee_goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY goals_tenant_isolation ON employee_goals
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- `goal_type`:
  - `achievement`: Reach a target state (close 10 deals)
  - `maintenance`: Maintain a state (keep pipeline > 3x quota)
  - `prevention`: Avoid a state (prevent churn)
- `priority`: 1 (lowest) to 10 (highest), employee decides based on urgency/importance
- `target`: Goal-specific metrics (JSONB for flexibility)
- `current_progress`: Real-time progress tracking

**Example `target` JSONB (Sales AE goal):**
```json
{
  "metric": "deals_closed",
  "value": 10,
  "timeframe": "quarter",
  "deadline": "2025-12-31T23:59:59Z"
}
```

**Example `target` JSONB (CSM maintenance goal):**
```json
{
  "metric": "nps_score",
  "threshold": 70,
  "accounts": ["account-uuid-1", "account-uuid-2"]
}
```

---

### `employee_intentions` - Plans/Intentions

```sql
CREATE TABLE employee_intentions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    goal_id             UUID REFERENCES employee_goals(id) ON DELETE CASCADE,

    -- Plan definition
    intention_type      TEXT NOT NULL,  -- 'action', 'strategy', 'tactic'
    description         TEXT NOT NULL,
    plan                JSONB NOT NULL,  -- Structured plan (steps, resources, etc.)

    -- Execution
    status              TEXT NOT NULL DEFAULT 'planned',
    priority            INTEGER NOT NULL DEFAULT 5,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    failed_at           TIMESTAMPTZ,

    -- Context
    context             JSONB NOT NULL DEFAULT '{}',  -- Why this plan was chosen
    dependencies        UUID[],  -- Other intentions this depends on

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    CHECK (status IN ('planned', 'in_progress', 'completed', 'failed', 'abandoned')),
    CHECK (priority BETWEEN 1 AND 10),
    CHECK (intention_type IN ('action', 'strategy', 'tactic'))
);

CREATE INDEX idx_intentions_employee ON employee_intentions(employee_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_intentions_goal ON employee_intentions(goal_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_intentions_status ON employee_intentions(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_intentions_priority ON employee_intentions(employee_id, priority DESC) WHERE status = 'planned';
CREATE INDEX idx_intentions_tenant ON employee_intentions(tenant_id) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE employee_intentions ENABLE ROW LEVEL SECURITY;

CREATE POLICY intentions_tenant_isolation ON employee_intentions
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- `intention_type`:
  - `action`: Single executable action (send email, create task)
  - `tactic`: Short-term plan (multi-step, hours-days)
  - `strategy`: Long-term plan (multi-week, composed of tactics)
- `plan`: Structured JSONB with steps, required capabilities, expected outcomes
- `dependencies`: Array of intention UUIDs (execution order)
- `context`: Why this plan was chosen (rationale, alternatives considered)

**Example `plan` JSONB (action):**
```json
{
  "type": "send_email",
  "params": {
    "to": "prospect@company.com",
    "subject": "Following up on our conversation",
    "template": "follow_up_v2",
    "context": {"meeting_date": "2025-10-25"}
  },
  "expected_outcome": "response_within_48h"
}
```

**Example `plan` JSONB (strategy):**
```json
{
  "type": "build_pipeline",
  "tactics": [
    {"type": "research_accounts", "count": 50},
    {"type": "personalize_outreach", "count": 50},
    {"type": "send_sequences", "count": 50},
    {"type": "follow_up", "cadence": "3_touches"}
  ],
  "success_criteria": {"opportunities_created": 10},
  "timeframe": "2_weeks"
}
```

---

## Memory Systems

### `memory_episodes` - Episodic Memory

```sql
CREATE TABLE memory_episodes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

    -- Episode content
    episode_type        TEXT NOT NULL,  -- 'interaction', 'event', 'observation'
    description         TEXT NOT NULL,
    content             JSONB NOT NULL,  -- Full episode data

    -- Context
    participants        TEXT[],  -- Email addresses or identifiers
    location            TEXT,  -- 'email', 'slack', 'zoom', 'phone', etc.

    -- Embedding for similarity search
    embedding           vector(1024),  -- pgvector for semantic search

    -- Importance & recall
    importance          FLOAT NOT NULL DEFAULT 0.5,  -- 0-1 scale
    recall_count        INTEGER NOT NULL DEFAULT 0,
    last_recalled_at    TIMESTAMPTZ,

    -- Temporal
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    CHECK (importance BETWEEN 0 AND 1),
    CHECK (episode_type IN ('interaction', 'event', 'observation', 'feedback'))
);

CREATE INDEX idx_episodes_employee ON memory_episodes(employee_id, occurred_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_episodes_type ON memory_episodes(employee_id, episode_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_episodes_participants ON memory_episodes USING GIN(participants) WHERE deleted_at IS NULL;
CREATE INDEX idx_episodes_occurred ON memory_episodes(occurred_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_episodes_tenant ON memory_episodes(tenant_id) WHERE deleted_at IS NULL;

-- Vector similarity search (pgvector)
CREATE INDEX idx_episodes_embedding ON memory_episodes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE memory_episodes ENABLE ROW LEVEL SECURITY;

CREATE POLICY episodes_tenant_isolation ON memory_episodes
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- `episode_type`: Categorizes memory for retrieval
- `content`: Full episode data (emails, transcripts, observations)
- `embedding`: 1024-dim vector for semantic similarity search (pgvector)
- `importance`: Computed score (recency + emotional significance + relevance)
- `recall_count`: Tracks how often episode is recalled (reinforcement)

**Example `content` JSONB (interaction):**
```json
{
  "interaction_type": "email",
  "from": "prospect@company.com",
  "to": "sales-ae@empla-customer.com",
  "subject": "Re: Proposal",
  "body": "Thanks for the proposal. Can we discuss pricing?",
  "sentiment": "positive",
  "intent": "negotiation",
  "entities": ["pricing", "proposal"],
  "outcome": "follow_up_scheduled"
}
```

---

### `memory_semantic` - Semantic Memory

```sql
CREATE TABLE memory_semantic (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

    -- Fact content
    fact_type           TEXT NOT NULL,  -- 'entity', 'relationship', 'rule', 'definition'
    subject             TEXT NOT NULL,
    predicate           TEXT NOT NULL,
    object              TEXT NOT NULL,

    -- Additional context
    confidence          FLOAT NOT NULL DEFAULT 1.0,  -- 0-1 scale
    source              TEXT,  -- Where this fact came from
    verified            BOOLEAN NOT NULL DEFAULT FALSE,

    -- Embedding
    embedding           vector(1024),

    -- Temporal
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (fact_type IN ('entity', 'relationship', 'rule', 'definition'))
);

CREATE INDEX idx_semantic_employee ON memory_semantic(employee_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_semantic_subject ON memory_semantic(employee_id, subject) WHERE deleted_at IS NULL;
CREATE INDEX idx_semantic_type ON memory_semantic(employee_id, fact_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_semantic_tenant ON memory_semantic(tenant_id) WHERE deleted_at IS NULL;

-- Full-text search
CREATE INDEX idx_semantic_fts ON memory_semantic USING GIN(to_tsvector('english', subject || ' ' || predicate || ' ' || object)) WHERE deleted_at IS NULL;

-- Vector similarity search
CREATE INDEX idx_semantic_embedding ON memory_semantic USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE memory_semantic ENABLE ROW LEVEL SECURITY;

CREATE POLICY semantic_tenant_isolation ON memory_semantic
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- **Subject-Predicate-Object (SPO) triple** structure (knowledge graph pattern)
- `fact_type`: Categorizes knowledge
- `confidence`: Degrades over time unless reinforced
- `verified`: Human-verified facts have higher confidence
- `embedding`: For semantic similarity search

**Example facts:**
```sql
-- Entity fact
('Acme Corp', 'is_a', 'enterprise_customer')

-- Relationship fact
('Acme Corp', 'uses', 'Salesforce')

-- Rule fact
('enterprise_deals', 'require', 'legal_review')

-- Definition fact
('churn_risk', 'defined_as', 'nps_score < 50')
```

---

### `memory_procedural` - Procedural Memory

```sql
CREATE TABLE memory_procedural (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

    -- Procedure definition
    procedure_name      TEXT NOT NULL,
    description         TEXT NOT NULL,
    procedure_type      TEXT NOT NULL,  -- 'skill', 'workflow', 'heuristic'

    -- Procedure content
    steps               JSONB NOT NULL,  -- Structured procedure steps
    conditions          JSONB NOT NULL DEFAULT '{}',  -- When to use this procedure

    -- Learning & performance
    success_rate        FLOAT NOT NULL DEFAULT 0.0,  -- 0-1 scale
    execution_count     INTEGER NOT NULL DEFAULT 0,
    last_executed_at    TIMESTAMPTZ,

    -- Metadata
    learned_from        TEXT,  -- 'human_demonstration', 'trial_and_error', 'instruction'

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    UNIQUE(employee_id, procedure_name),
    CHECK (success_rate BETWEEN 0 AND 1),
    CHECK (procedure_type IN ('skill', 'workflow', 'heuristic')),
    CHECK (learned_from IN ('human_demonstration', 'trial_and_error', 'instruction', 'pre_built'))
);

CREATE INDEX idx_procedural_employee ON memory_procedural(employee_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_procedural_type ON memory_procedural(employee_id, procedure_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_procedural_success ON memory_procedural(employee_id, success_rate DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_procedural_tenant ON memory_procedural(tenant_id) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE memory_procedural ENABLE ROW LEVEL SECURITY;

CREATE POLICY procedural_tenant_isolation ON memory_procedural
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- `procedure_type`:
  - `skill`: Low-level action (send_email, create_task)
  - `workflow`: Multi-step procedure (qualification_call, deal_handoff)
  - `heuristic`: Decision rule (when to follow up, how to prioritize)
- `steps`: Structured procedure definition
- `conditions`: When this procedure applies (context matching)
- `success_rate`: Learned from outcomes (RLHF-style)
- `learned_from`: Source of procedure (human shadow vs self-discovered)

**Example `steps` JSONB (workflow):**
```json
{
  "workflow": "qualification_call",
  "steps": [
    {"step": 1, "action": "research_account", "duration": "10m"},
    {"step": 2, "action": "prepare_questions", "template": "bant"},
    {"step": 3, "action": "join_call", "platform": "zoom"},
    {"step": 4, "action": "ask_questions", "questions": ["budget", "authority", "need", "timeline"]},
    {"step": 5, "action": "take_notes", "format": "structured"},
    {"step": 6, "action": "qualify_opportunity", "criteria": "bant_score > 70"},
    {"step": 7, "action": "schedule_followup", "if": "qualified"}
  ]
}
```

**Example `conditions` JSONB:**
```json
{
  "triggers": ["discovery_call_scheduled", "qualification_stage"],
  "context": {
    "deal_size": "> 10000",
    "lead_source": ["inbound", "referral"]
  }
}
```

---

### `memory_working` - Working Memory

```sql
CREATE TABLE memory_working (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

    -- Context content
    context_type        TEXT NOT NULL,  -- 'current_task', 'conversation', 'scratchpad'
    content             JSONB NOT NULL,

    -- Lifecycle
    priority            INTEGER NOT NULL DEFAULT 5,  -- 1-10 scale
    expires_at          TIMESTAMPTZ,  -- Auto-evict when expired

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    CHECK (priority BETWEEN 1 AND 10),
    CHECK (context_type IN ('current_task', 'conversation', 'scratchpad', 'recent_observation'))
);

CREATE INDEX idx_working_employee ON memory_working(employee_id, priority DESC) WHERE deleted_at IS NULL AND (expires_at IS NULL OR expires_at > now());
CREATE INDEX idx_working_type ON memory_working(employee_id, context_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_working_expires ON memory_working(expires_at) WHERE deleted_at IS NULL AND expires_at IS NOT NULL;
CREATE INDEX idx_working_tenant ON memory_working(tenant_id) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE memory_working ENABLE ROW LEVEL SECURITY;

CREATE POLICY working_tenant_isolation ON memory_working
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- **Short-lived memory** for current execution context
- `context_type`: Categorizes working memory slots
- `expires_at`: Auto-eviction (working memory has limited capacity)
- `priority`: Determines what to evict when capacity reached
- Typically cleared between proactive loop cycles

**Example `content` JSONB (current_task):**
```json
{
  "task": "compose_followup_email",
  "context": {
    "prospect": "jane@acme.com",
    "last_interaction": "2025-10-25T14:30:00Z",
    "interaction_summary": "Discussed pricing, requested case study",
    "next_step": "Send case study + pricing breakdown"
  },
  "progress": {
    "step": "drafting",
    "draft": "Hi Jane, following up on our call..."
  }
}
```

---

## Beliefs (World Model)

### `beliefs` - Current Beliefs

```sql
CREATE TABLE beliefs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,

    -- Belief content
    belief_type         TEXT NOT NULL,  -- 'state', 'event', 'causal', 'evaluative'
    subject             TEXT NOT NULL,
    predicate           TEXT NOT NULL,
    object              JSONB NOT NULL,  -- Can be text, number, boolean, or complex object

    -- Confidence & source
    confidence          FLOAT NOT NULL DEFAULT 0.5,  -- 0-1 scale
    source              TEXT NOT NULL,  -- 'observation', 'inference', 'told_by_human', 'prior'
    evidence            JSONB NOT NULL DEFAULT '[]',  -- Supporting observations

    -- Temporal decay
    formed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    decay_rate          FLOAT NOT NULL DEFAULT 0.1,  -- Linear decay per day

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    UNIQUE(employee_id, subject, predicate),  -- One belief per (subject, predicate)
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (decay_rate BETWEEN 0 AND 1),
    CHECK (belief_type IN ('state', 'event', 'causal', 'evaluative')),
    CHECK (source IN ('observation', 'inference', 'told_by_human', 'prior'))
);

CREATE INDEX idx_beliefs_employee ON beliefs(employee_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_beliefs_subject ON beliefs(employee_id, subject) WHERE deleted_at IS NULL;
CREATE INDEX idx_beliefs_confidence ON beliefs(employee_id, confidence DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_beliefs_updated ON beliefs(last_updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_beliefs_tenant ON beliefs(tenant_id) WHERE deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE beliefs ENABLE ROW LEVEL SECURITY;

CREATE POLICY beliefs_tenant_isolation ON beliefs
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- **Subject-Predicate-Object structure** (like semantic memory, but with confidence/decay)
- `belief_type`:
  - `state`: Belief about current state ("pipeline is low")
  - `event`: Belief that event occurred ("prospect replied")
  - `causal`: Belief about causation ("personalized emails increase response rate")
  - `evaluative`: Belief about value/quality ("Acme Corp is high-priority")
- `confidence`: Degrades via `decay_rate` unless reinforced by observations
- `evidence`: Array of observation IDs that support this belief
- **Unique constraint**: Only one belief per (employee, subject, predicate) - updates replace

**Example beliefs:**
```sql
-- State belief
employee_id='uuid', subject='pipeline', predicate='coverage', object='2.1', confidence=0.9, source='observation'

-- Event belief
employee_id='uuid', subject='prospect_jane@acme', predicate='replied_to_email', object='true', confidence=1.0, source='observation'

-- Causal belief
employee_id='uuid', subject='personalized_outreach', predicate='increases', object='{"metric": "response_rate", "magnitude": 1.5}', confidence=0.7, source='inference'

-- Evaluative belief
employee_id='uuid', subject='acme_corp', predicate='priority', object='high', confidence=0.8, source='told_by_human'
```

---

### `belief_history` - Belief Changes

```sql
CREATE TABLE belief_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    belief_id           UUID NOT NULL REFERENCES beliefs(id) ON DELETE CASCADE,

    -- Change tracking
    change_type         TEXT NOT NULL,  -- 'created', 'updated', 'deleted', 'decayed'
    old_value           JSONB,
    new_value           JSONB,
    old_confidence      FLOAT,
    new_confidence      FLOAT,

    -- Context
    reason              TEXT,  -- Why belief changed

    -- Temporal
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (change_type IN ('created', 'updated', 'deleted', 'decayed'))
);

CREATE INDEX idx_belief_history_belief ON belief_history(belief_id, changed_at DESC);
CREATE INDEX idx_belief_history_employee ON belief_history(employee_id, changed_at DESC);
CREATE INDEX idx_belief_history_tenant ON belief_history(tenant_id);

-- Row-Level Security
ALTER TABLE belief_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY belief_history_tenant_isolation ON belief_history
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- **Immutable audit log** of belief changes
- Used for learning: "What belief changes led to successful outcomes?"
- Used for debugging: "Why did employee make this decision?"
- Used for explanation: "Why does employee believe X?"

---

## Audit & Observability

### `audit_log` - All Significant Actions

```sql
CREATE TABLE audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Actor
    actor_type          TEXT NOT NULL,  -- 'employee', 'user', 'system'
    actor_id            UUID NOT NULL,

    -- Action
    action_type         TEXT NOT NULL,
    resource_type       TEXT NOT NULL,
    resource_id         UUID,

    -- Details
    details             JSONB NOT NULL DEFAULT '{}',
    metadata            JSONB NOT NULL DEFAULT '{}',

    -- Temporal
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (actor_type IN ('employee', 'user', 'system'))
);

CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, occurred_at DESC);
CREATE INDEX idx_audit_actor ON audit_log(actor_type, actor_id, occurred_at DESC);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id, occurred_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action_type, occurred_at DESC);

-- Row-Level Security
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_tenant_isolation ON audit_log
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- **Immutable append-only log**
- Every significant action logged (goal created, intention executed, belief updated)
- Used for compliance, debugging, analytics
- Partitioned by `occurred_at` for performance (implement in Phase 3+)

---

### `metrics` - Time-Series Metrics

```sql
CREATE TABLE metrics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id         UUID REFERENCES employees(id) ON DELETE CASCADE,

    -- Metric identity
    metric_name         TEXT NOT NULL,
    metric_type         TEXT NOT NULL,  -- 'counter', 'gauge', 'histogram'

    -- Value
    value               FLOAT NOT NULL,
    tags                JSONB NOT NULL DEFAULT '{}',

    -- Temporal
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (metric_type IN ('counter', 'gauge', 'histogram'))
);

CREATE INDEX idx_metrics_tenant ON metrics(tenant_id, timestamp DESC);
CREATE INDEX idx_metrics_employee ON metrics(employee_id, metric_name, timestamp DESC) WHERE employee_id IS NOT NULL;
CREATE INDEX idx_metrics_name ON metrics(metric_name, timestamp DESC);

-- Row-Level Security
ALTER TABLE metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY metrics_tenant_isolation ON metrics
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

**Design Notes:**
- **Time-series data** for performance monitoring
- `employee_id` nullable for system-wide metrics
- `tags`: Dimensions (e.g., `{"goal_type": "pipeline", "outcome": "success"}`)
- Consider TimescaleDB extension in Phase 3+ for better time-series performance

---

## Indexes Summary

### Performance-Critical Indexes

All tables have these standard indexes:
- `tenant_id` - Multi-tenant filtering (every query uses this)
- `created_at` / `updated_at` / `occurred_at` - Temporal queries
- `deleted_at IS NULL` - Soft delete filtering

Table-specific critical indexes:
- **employees**: `(tenant_id, status)`, `(tenant_id, role)`, `lifecycle_stage`
- **employee_goals**: `(employee_id, status)`, `(employee_id, priority DESC)`
- **employee_intentions**: `(employee_id, status)`, `(goal_id)`, `(employee_id, priority DESC)`
- **memory_episodes**: `(employee_id, occurred_at DESC)`, vector index on `embedding`
- **memory_semantic**: Full-text search, vector index on `embedding`
- **beliefs**: `(employee_id, subject)`, `(employee_id, confidence DESC)`

### Index Maintenance

- **Vacuum**: Auto-vacuum enabled (PostgreSQL default)
- **Analyze**: Run weekly for query planner optimization
- **Reindex**: Quarterly for vector indexes (IVFFlat degrades over time)

---

## Migration Strategy

### Phase 1: Core Tables
1. Create `tenants`, `users` (multi-tenancy foundation)
2. Create `employees` (employee profiles)
3. Create `employee_goals`, `employee_intentions` (BDI core)
4. Create `beliefs`, `belief_history` (world model)
5. Create `memory_*` tables (memory systems)
6. Create `audit_log`, `metrics` (observability)

### Phase 2+: Additions
- `capabilities` table (Phase 2: Capabilities Layer)
- `integrations` table (Phase 3: Integrations Layer)
- `conversations` table (Phase 4: Interaction Layer)
- `a2a_messages` table (Phase 7: Collaboration Layer)

### Migration Tools
- **Alembic**: Schema version control
- **Seed data**: Example employees, goals for development
- **Test data**: Comprehensive fixtures for testing

---

## Security Considerations

### Row-Level Security (RLS)

All tables enforce tenant isolation via RLS:
```sql
-- Application sets tenant context
SET app.current_tenant_id = 'tenant-uuid';

-- All queries automatically filtered by tenant_id
SELECT * FROM employees;  -- Only returns employees for current tenant
```

### Data Privacy

- **PII**: User emails, names are in `users`, `employees` tables
- **Encryption**: Use PostgreSQL TDE (Transparent Data Encryption) in production
- **Backups**: Encrypted backups with tenant-level restore capability
- **Soft delete**: `deleted_at` preserves audit trail, data can be purged after retention period

### Access Control

- **Admin**: Full access to all tenant data
- **Manager**: Read/write employees, read-only audit logs
- **User**: Read-only employees assigned to them
- **Employee**: No direct database access (API layer only)

---

## Performance Targets

### Query Performance
- Single employee lookup: < 10ms
- Goal/intention queries: < 50ms
- Episodic memory recall (10 episodes): < 100ms
- Semantic memory search (top 20): < 200ms
- Belief updates (10 beliefs): < 50ms

### Scalability
- **Phase 1**: 100 employees per tenant, 10 tenants
- **Phase 3**: 1000 employees per tenant, 100 tenants
- **Phase 5**: 10,000 employees per tenant, 1000 tenants

### Monitoring
- Query latency (p50, p95, p99)
- Database connection pool usage
- Table sizes and growth rates
- Index hit ratios (should be > 95%)

---

## Open Questions

1. **Belief decay**: Linear vs exponential decay? (Current: linear for simplicity, revisit in Phase 3)
2. **Vector dimensions**: 1024 vs 1536 vs 3072? (Current: 1024 for balance of quality/performance)
3. **Memory capacity**: Hard limits per employee? (Current: soft limits via importance-based eviction)
4. **Partitioning strategy**: Time-based partitioning for audit_log/metrics? (Defer to Phase 3+)

---

## Next Steps

1. **Implement Alembic migrations** for this schema
2. **Create Pydantic models** (see `docs/design/core-models.md`)
3. **Write seed data** for development/testing
4. **Add database health checks** (connection, query latency, table sizes)

---

**References:**
- ARCHITECTURE.md - System architecture
- docs/design/core-models.md - Pydantic models
- docs/design/bdi-engine.md - BDI implementation
- docs/design/memory-system.md - Memory system implementation
