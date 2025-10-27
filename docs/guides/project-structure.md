# empla Project Structure Reference

> **Purpose:** Official project organization guide - directories created as needed during implementation
> **Philosophy:** Create directories when implementing features, not speculatively
> **Research-Backed:** Based on analysis of 8 successful open source projects (Django, FastAPI, MLflow, PostHog, Prefect, Airflow, Langflow, Supabase)
> **Last Updated:** 2025-10-26

---

## Structure Decision Rationale

**Pattern Used: Python-First with Top-Level Package**

This follows the pattern of successful Python platforms like **MLflow**, **PostHog**, **Django**, and **FastAPI**:
- ✅ Simple imports: `import empla` (matches repository name)
- ✅ No extra nesting (not `src/empla/` or `backend/empla/`)
- ✅ Web UI as separate top-level directory (`web/`)
- ✅ Follows Python conventions and best practices
- ✅ Straightforward PyPI publishing
- ✅ Package discovery automatic

**Why NOT `src/empla/`?**
- Extra nesting with no clear benefit for empla's use case
- Less common in Python ecosystem (more common in Node.js)
- Import is still `import empla`, so why nest?

**Why NOT `backend/empla/`?**
- Requires PYTHONPATH manipulation (fragile)
- Complicates PyPI publishing
- Not standard Python convention
- No major Python project uses this pattern

---

## Complete Project Structure

```
empla/
  ├── README.md                          # Compelling intro for HN
  ├── ARCHITECTURE.md                    # System architecture document
  ├── CLAUDE.md                          # Instructions for Claude Code
  ├── LICENSE                            # Apache 2.0
  ├── pyproject.toml                     # Project config
  ├── docker-compose.yml                 # Local development (DEFERRED - using native PostgreSQL)
  ├── .env.example                       # Environment template
  │
  ├── docs/                              # Documentation
  │   ├── getting-started.md
  │   ├── concepts/
  │   │   ├── autonomous-employees.md
  │   │   ├── bdi-architecture.md
  │   │   ├── memory-systems.md
  │   │   └── proactive-execution.md
  │   ├── guides/
  │   │   ├── creating-employee.md
  │   │   ├── adding-capabilities.md
  │   │   ├── deployment.md
  │   │   ├── local-development-setup.md
  │   │   ├── project-structure.md      # (this file)
  │   │   └── production.md
  │   ├── decisions/                     # Architecture Decision Records
  │   │   ├── template.md
  │   │   ├── 001-postgresql-primary-database.md
  │   │   ├── 002-python-fastapi-stack.md
  │   │   ├── 003-custom-bdi-architecture.md
  │   │   ├── 004-defer-agent-framework-decision.md
  │   │   ├── 005-pgvector-initial-vector-storage.md
  │   │   └── 006-proactive-loop-over-event-driven.md
  │   ├── design/                        # Feature design documents
  │   │   ├── template.md
  │   │   ├── database-schema.md         # (Phase 1)
  │   │   ├── core-models.md             # (Phase 1)
  │   │   ├── bdi-engine.md              # (Phase 1)
  │   │   └── memory-system.md           # (Phase 1)
  │   ├── api-reference/
  │   ├── examples/
  │   └── resources.md                   # Learning resources
  │
  ├── empla/                             # Main package
  │   ├── __init__.py
  │   │
  │   ├── core/                          # Autonomous core (Phase 1)
  │   │   ├── bdi/                       # Belief-Desire-Intention
  │   │   │   ├── __init__.py
  │   │   │   ├── beliefs.py
  │   │   │   ├── desires.py
  │   │   │   ├── intentions.py
  │   │   │   └── reasoning.py
  │   │   │
  │   │   ├── proactive/                 # Proactive execution
  │   │   │   ├── __init__.py
  │   │   │   ├── continuous_loop.py
  │   │   │   ├── event_monitor.py
  │   │   │   ├── triggers.py
  │   │   │   └── opportunity_detection.py
  │   │   │
  │   │   ├── memory/                    # Memory systems
  │   │   │   ├── __init__.py
  │   │   │   ├── working.py            # Short-term
  │   │   │   ├── episodic.py           # Experiential
  │   │   │   ├── semantic.py           # Knowledge
  │   │   │   ├── procedural.py         # Skills
  │   │   │   └── consolidation.py
  │   │   │
  │   │   ├── planning/                  # Strategic planning
  │   │   │   ├── __init__.py
  │   │   │   ├── strategic.py
  │   │   │   ├── tactical.py
  │   │   │   ├── immediate.py
  │   │   │   └── adaptation.py
  │   │   │
  │   │   ├── persona/                   # Personality (Phase 5)
  │   │   │   ├── __init__.py
  │   │   │   ├── personality.py
  │   │   │   ├── communication.py
  │   │   │   ├── decision_making.py
  │   │   │   └── behavior.py
  │   │   │
  │   │   ├── learning/                  # Learning system (Phase 4)
  │   │   │   ├── __init__.py
  │   │   │   ├── outcome_evaluation.py
  │   │   │   ├── skill_acquisition.py
  │   │   │   └── optimization.py
  │   │   │
  │   │   ├── config/                    # Configuration
  │   │   ├── db/                        # Database models
  │   │   └── auth/                      # Authentication
  │   │
  │   ├── capabilities/                  # Employee capabilities (Phase 2+)
  │   │   ├── __init__.py
  │   │   ├── base.py                   # Base capability
  │   │   │
  │   │   ├── email/                    # Email (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   ├── client.py
  │   │   │   ├── triage.py
  │   │   │   └── compose.py
  │   │   │
  │   │   ├── calendar/                 # Calendar (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   ├── scheduling.py
  │   │   │   └── optimization.py
  │   │   │
  │   │   ├── messaging/                # Slack, Teams (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   ├── slack.py
  │   │   │   └── teams.py
  │   │   │
  │   │   ├── meetings/                 # Advanced meetings (Phase 3)
  │   │   │   ├── __init__.py
  │   │   │   ├── webrtc_client.py
  │   │   │   ├── voice_synthesis.py
  │   │   │   ├── voice_recognition.py
  │   │   │   ├── avatar.py
  │   │   │   ├── screen_share.py
  │   │   │   ├── facilitation.py
  │   │   │   └── participation.py
  │   │   │
  │   │   ├── browser/                  # Browser automation (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   ├── playwright_client.py
  │   │   │   └── research.py
  │   │   │
  │   │   ├── computer_use/             # Anthropic computer use (Phase 3)
  │   │   │   ├── __init__.py
  │   │   │   └── controller.py
  │   │   │
  │   │   ├── documents/                # Document generation (Phase 2-3)
  │   │   │   ├── __init__.py
  │   │   │   ├── presentations.py
  │   │   │   ├── proposals.py
  │   │   │   ├── reports.py
  │   │   │   └── templates/
  │   │   │
  │   │   ├── research/                 # Research & analysis (Phase 3)
  │   │   │   ├── __init__.py
  │   │   │   ├── web_research.py
  │   │   │   ├── data_analysis.py
  │   │   │   └── synthesis.py
  │   │   │
  │   │   ├── crm/                      # CRM integration (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   ├── salesforce.py
  │   │   │   └── hubspot.py
  │   │   │
  │   │   └── relationship/             # Relationship mgmt (Phase 2)
  │   │       ├── __init__.py
  │   │       ├── outreach.py
  │   │       ├── follow_up.py
  │   │       └── nurturing.py
  │   │
  │   ├── integrations/                  # Integration framework (Phase 2+)
  │   │   ├── __init__.py
  │   │   ├── base.py
  │   │   ├── registry.py
  │   │   │
  │   │   ├── mcp/                      # MCP protocol (Phase 6)
  │   │   │   ├── __init__.py
  │   │   │   ├── server.py
  │   │   │   └── client.py
  │   │   │
  │   │   ├── oauth/                    # OAuth flows (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   └── flows.py
  │   │   │
  │   │   ├── microsoft/                # Microsoft 365 (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   ├── graph.py
  │   │   │   └── teams.py
  │   │   │
  │   │   ├── google/                   # Google Workspace (Phase 2)
  │   │   │   ├── __init__.py
  │   │   │   ├── gmail.py
  │   │   │   └── workspace.py
  │   │   │
  │   │   └── slack/                    # Slack (Phase 2)
  │   │       ├── __init__.py
  │   │       └── client.py
  │   │
  │   ├── knowledge/                     # Knowledge layer (Phase 4)
  │   │   ├── __init__.py
  │   │   │
  │   │   ├── graph/                    # Knowledge graph
  │   │   │   ├── __init__.py
  │   │   │   ├── neo4j_client.py       # (Deferred - PostgreSQL CTEs initially)
  │   │   │   ├── schema.py
  │   │   │   └── queries.py
  │   │   │
  │   │   ├── vector/                   # Vector DB
  │   │   │   ├── __init__.py
  │   │   │   └── qdrant_client.py      # (Deferred - pgvector initially)
  │   │   │
  │   │   ├── rag/                      # RAG system
  │   │   │   ├── __init__.py
  │   │   │   ├── agentic_rag.py
  │   │   │   └── retrieval.py
  │   │   │
  │   │   ├── ingest/                   # Data ingestion
  │   │   │   ├── __init__.py
  │   │   │   ├── pipeline.py
  │   │   │   └── processors/
  │   │   │
  │   │   └── embedding/                # Embeddings
  │   │       ├── __init__.py
  │   │       └── generator.py
  │   │
  │   ├── employees/                     # Digital employees (Phase 5+)
  │   │   ├── __init__.py
  │   │   ├── base.py                   # Base employee class
  │   │   ├── registry.py               # Employee catalog
  │   │   │
  │   │   ├── sales_ae/                 # Sales AE (Phase 5)
  │   │   │   ├── __init__.py
  │   │   │   ├── employee.py
  │   │   │   ├── persona.py
  │   │   │   ├── goals.py
  │   │   │   ├── strategies.py
  │   │   │   └── workflows/
  │   │   │
  │   │   ├── csm/                      # Customer Success (Phase 5)
  │   │   │   ├── __init__.py
  │   │   │   ├── employee.py
  │   │   │   ├── persona.py
  │   │   │   ├── goals.py
  │   │   │   └── strategies.py
  │   │   │
  │   │   ├── product_manager/          # Product Manager (Phase 5)
  │   │   │   ├── __init__.py
  │   │   │   ├── employee.py
  │   │   │   ├── persona.py
  │   │   │   └── strategies.py
  │   │   │
  │   │   ├── recruiter/                # Recruiter (Phase 5+)
  │   │   │   ├── __init__.py
  │   │   │   └── employee.py
  │   │   │
  │   │   └── executive_assistant/      # Executive Assistant (Phase 5+)
  │   │       ├── __init__.py
  │   │       └── employee.py
  │   │
  │   ├── api/                           # REST API (Phase 1)
  │   │   ├── __init__.py
  │   │   ├── main.py
  │   │   │
  │   │   └── v1/
  │   │       ├── __init__.py
  │   │       ├── router.py
  │   │       │
  │   │       ├── endpoints/
  │   │       │   ├── employees.py
  │   │       │   ├── tasks.py
  │   │       │   ├── goals.py
  │   │       │   ├── integrations.py
  │   │       │   ├── knowledge.py
  │   │       │   └── monitoring.py
  │   │       │
  │   │       └── dependencies.py
  │   │
  │   ├── cli/                           # CLI interface (Phase 1+)
  │   │   ├── __init__.py
  │   │   └── main.py
  │   │
  │   └── utils/                         # Utilities (Phase 1+)
  │       ├── __init__.py
  │       ├── logging.py
  │       └── helpers.py
  │
  ├── deployment/                        # Deployment configs (Phase 6+)
  │   ├── docker/
  │   │   ├── Dockerfile
  │   │   ├── Dockerfile.dev
  │   │   └── .dockerignore
  │   │
  │   ├── kubernetes/                    # K8s manifests
  │   │   ├── base/
  │   │   │   ├── deployment.yaml
  │   │   │   ├── service.yaml
  │   │   │   └── configmap.yaml
  │   │   └── overlays/
  │   │       ├── dev/
  │   │       ├── staging/
  │   │       └── production/
  │   │
  │   └── terraform/                     # IaC
  │       ├── modules/
  │       │   ├── network/
  │       │   ├── compute/
  │       │   └── database/
  │       ├── aws/
  │       ├── azure/
  │       └── gcp/
  │
  ├── examples/                          # Example implementations (Phase 2+)
  │   ├── quickstart/
  │   │   └── simple_employee.py
  │   ├── custom_employee/
  │   │   └── custom_sales_ae.py
  │   ├── custom_capability/
  │   │   └── custom_tool.py
  │   └── enterprise_deployment/
  │       └── multi_tenant_setup.py
  │
  ├── tests/                             # Test suite (Phase 1+)
  │   ├── unit/
  │   │   ├── test_bdi.py
  │   │   ├── test_memory.py
  │   │   ├── test_planning.py
  │   │   └── test_capabilities/
  │   ├── integration/
  │   │   ├── test_employees.py
  │   │   └── test_integrations/
  │   └── e2e/
  │       └── test_scenarios/
  │
  └── scripts/                           # Utility scripts (Phase 1+)
      ├── setup-local-db.sh              # Set up PostgreSQL + pgvector
      ├── dev.sh
      ├── migrate.sh
      ├── seed_knowledge.py
      └── deploy.sh
```

---

## Implementation Strategy by Phase

### Phase 1: Autonomous Core (Months 1-3) - **CURRENT**

**Create these directories:**
```bash
empla/
  core/{bdi,proactive,memory,planning,config,db,auth}/
  api/v1/endpoints/
  cli/
  utils/

tests/
  unit/{bdi,memory,planning,api}/
  integration/database/
  e2e/

scripts/
```

**Deliverables:**
- BDI (Belief-Desire-Intention) engine
- Proactive execution loop
- Multi-type memory system
- Strategic planning system
- FastAPI foundation
- Database setup (PostgreSQL)
- Basic auth and multi-tenancy

### Phase 2: Basic Capabilities (Months 3-5)

**Create these directories:**
```bash
empla/
  capabilities/{base,email,calendar,messaging,browser,documents}/
  integrations/{base,microsoft,google,slack,oauth}/
```

**Deliverables:**
- Email, calendar, messaging capabilities
- Browser automation (Playwright)
- Basic integrations (Microsoft, Google, Slack)

### Phase 3: Advanced Capabilities (Months 5-7)

**Create these directories:**
```bash
empla/
  capabilities/{meetings,computer_use,research}/
```

**Deliverables:**
- WebRTC meeting participation
- Voice synthesis/recognition
- Anthropic computer use
- Advanced research capabilities

### Phase 4: Knowledge & Learning (Months 7-9)

**Create these directories:**
```bash
empla/
  knowledge/{graph,vector,rag,ingest,embedding}/
  core/learning/
```

**Deliverables:**
- Knowledge graph (initially PostgreSQL CTEs, optionally Neo4j later)
- Vector search (pgvector, optionally Qdrant later)
- Agentic RAG system
- Learning system

### Phase 5: Persona & First Employees (Months 9-11)

**Create these directories:**
```bash
empla/
  core/persona/
  employees/{base,sales_ae,csm,product_manager}/
```

**Deliverables:**
- Persona system (Big Five personality)
- 3 fully autonomous employees (Sales AE, CSM, PM)

### Phase 6: Platform & Multi-Tenancy (Months 11-13)

**Create these directories:**
```bash
empla/
  integrations/mcp/
deployment/{docker,kubernetes,terraform}/
```

**Deliverables:**
- Production-ready multi-tenancy
- MCP server/client
- Deployment tooling

### Phase 7+: UI & Marketplace (Months 13-15+)

**Create these directories:**
```bash
empla/
  web/  # (or separate repo)
examples/{quickstart,custom_employee,custom_capability,enterprise}/
```

**Deliverables:**
- Web dashboard
- Employee marketplace
- Integration marketplace

---

## Key Principles

### 1. Create Directories As Needed, Not Speculatively

**DON'T:**
```bash
# Creating all directories upfront
mkdir -p empla/capabilities/meetings/webrtc/voice/synthesis/engines/elevenlabs
```

**DO:**
```bash
# Create when implementing Phase 3
mkdir -p empla/capabilities/meetings
# Add webrtc_client.py, voice_synthesis.py when needed
```

### 2. Package Name: `empla` (Not `src/empla`)

Following the structure you provided, the package is **`empla/`** directly (not nested in `src/`).

**Rationale:**
- Cleaner imports: `from empla.core.bdi import BeliefSystem`
- Standard Python practice for applications
- Matches examples you provided

### 3. Follow Phase Structure

Each phase has clear deliverables. Create directories for current phase, not future phases.

### 4. Document Evolution

When creating new directories or changing structure:
1. Update this document
2. Document rationale in CHANGELOG.md
3. If it's an architectural change, create an ADR

---

## References

- **ARCHITECTURE.md:** Complete system architecture (Layers 0-7)
- **Related ADRs:**
  - ADR-002: Python + FastAPI stack
  - ADR-003: Custom BDI architecture
- **Development Roadmap:** See ARCHITECTURE.md for 8-phase roadmap details

---

**Created:** 2025-10-26
**Author:** Claude Code
**Status:** Official reference - create directories as needed per phase
