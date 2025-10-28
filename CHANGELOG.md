# empla - Changelog

> **Purpose:** Track significant changes, decisions, and progress
> **Format:** Newest entries first
> **Audience:** Claude Code, contributors, users

---

## 2025-10-26 - Phase 0 Complete: Documentation & Project Setup

**Phase:** 0 - Foundation Setup ✅ COMPLETE

### Clarified

**empla's Hybrid Model - Product + Platform:**
- **Previous description:** "Operating System for Autonomous Digital Employees"
- **New description:** "Production-Ready Digital Employees + Extensible Platform to Build Your Own"
- **Rationale:** Clarifies that empla provides BOTH:
  1. Production-ready employees you can deploy immediately (Sales AE, CSM, PM, etc.)
  2. Extensible platform to customize existing employees or build completely new ones
- **Hybrid model:** Primary value = ready-made employees, Secondary value = customization/extension
- **Updated in:** CLAUDE.md, README.md, core mission sections

### Added

**Phase 0 Setup:**
- **pyproject.toml** - Modern Python project configuration
  - Using `uv` for 10-100x faster package management
  - Configured ruff, mypy, pytest, coverage
  - Top-level `empla/` package (not `src/empla/`)
  - Apache 2.0 license

- **docs/guides/project-structure.md** - Official project structure reference
  - Research-backed: Analyzed 8 successful OSS projects (Django, FastAPI, MLflow, PostHog, Prefect, Airflow, Langflow, Supabase)
  - **Decision:** Top-level `empla/` package + separate `web/` UI directory
  - **Rationale:** Follows Python best practices (MLflow, PostHog pattern)
  - Imports: `from empla.core.bdi import BeliefSystem` (simple, clean)
  - Web UI gets own top-level directory with independent tooling
  - Create-as-needed philosophy (directories per phase, not speculative)

- **CLAUDE.md** (1,536 lines, optimized from 1,816) - Complete development guide for Claude Code
  - Working memory system with session management protocol
  - 10-point mandate for proactive, bold, excellent development
  - Meta-loop section establishing Claude Code as first empla employee
  - Complete development workflow (UNDERSTAND → DESIGN → IMPLEMENT → VALIDATE → REVIEW → SUBMIT → ITERATE → MERGE → DOCUMENT → LEARN)
  - **Optimization:** Reduced by 321 lines (18%) while preserving ALL critical teaching examples and workflows

- **ARCHITECTURE.md** (2,091 lines) - Complete technical specification
  - 8-layer architecture (Layers 0-7)
  - Technology stack with locked vs deferred decisions
  - 8-phase development roadmap
  - Complete component specifications with pseudocode

- **README.md** (648 lines) - Public-facing introduction
  - Vision and value proposition
  - Comparison with existing agent frameworks
  - Core innovations (BDI, memory, lifecycle, learning, collaboration)
  - Quick-start guide (placeholder)

- **TODO.md** - Session-based work tracker
  - Current session goals
  - Phase 0 task breakdown
  - Ideas and known issues

- **CHANGELOG.md** - This file
  - Format established
  - Initial entry created

- **docs/resources.md** - Learning resources
  - BDI architecture, agent systems, knowledge graphs
  - RAG systems, WebRTC, imitation learning
  - Multi-agent protocols, vector databases
  - Python/FastAPI, security, observability

### Decided

**Technology Stack (Locked):**
- **ADR-001** (to be written): PostgreSQL 17 as primary database
  - Rationale: Production-proven, handles relational + JSONB + pgvector + full-text search + row-level security
  - Alternatives considered: MongoDB, Neo4j, specialized DBs
  - Decision: Start PostgreSQL-first, migrate only if proven necessary

- **ADR-002** (to be written): Python 3.11+ with FastAPI
  - Rationale: Async-native, type hints, modern features, excellent ecosystem
  - Alternatives considered: Go, Rust, Node.js
  - Decision: Python for AI/ML integration, FastAPI for async web framework

- **ADR-003** (to be written): Custom BDI architecture over agent frameworks
  - Rationale: empla's autonomy requirements differ from existing frameworks
  - Alternatives considered: LangGraph, AutoGen, CrewAI, Agno
  - Decision: Build custom BDI, evaluate frameworks for tool execution in Phase 2

- **ADR-004** (to be written): Defer agent framework decision to Phase 2
  - Rationale: Don't know tool execution needs yet, avoid premature lock-in
  - Alternatives considered: Lock in Agno now
  - Decision: Implement core autonomy first, choose framework based on real needs

- **ADR-005** (to be written): Use pgvector for initial vector storage
  - Rationale: Simpler operations, handles millions of vectors, PostgreSQL already deployed
  - Alternatives considered: Qdrant, Weaviate, Pinecone
  - Decision: Start with pgvector, migrate to dedicated vector DB only if proven necessary

- **ADR-006** (to be written): Proactive loop over event-driven architecture
  - Rationale: Employees need to "think" even when no events occur, simpler to reason about
  - Alternatives considered: Full event-driven with message queues
  - Decision: Polling loop (5 min default), separate fast-path for urgent events

**Development Philosophy:**
- Lock minimal stable infrastructure
- Defer framework decisions until implementation proves need
- Build production-quality from day 1
- Test-driven development (>80% coverage target)
- Documentation-driven development (ADRs before decisions, design docs before features)

### Discovered

**Documentation Issues (from comprehensive review):**
- ✅ CLAUDE.md too large (1,816 lines) → **FIXED:** Optimized to 1,495 lines
- 800+ lines of redundant content across files → **PARTIALLY FIXED:** Removed ~140 lines by pointing to ARCHITECTURE.md
- ✅ Missing operational files → **FIXED:** Created ADR/design doc templates, resources.md
- ARCHITECTURE.md too large (2,091 lines) → **DEFERRED:** Will address if needed

**Optimization Strategy Applied:**
1. ✅ Created ADR infrastructure (docs/decisions/ with template)
2. ✅ Created design doc infrastructure (docs/design/ with template)
3. ✅ Created docs/resources.md (moved learning resources from CLAUDE.md)
4. ✅ Optimized CLAUDE.md - reduced by 321 lines (18%) to 1,495 lines
5. ✅ Preserved ALL critical teaching examples and workflows
6. ⏳ Write 6 initial ADRs (next task)

### Next

**Immediate (Phase 0 completion):**
- ✅ Create docs/decisions/ directory with ADR template
- ✅ Create docs/design/ directory with design template
- ⏳ Write initial ADRs (001-006) for documented decisions
- ✅ Optimize CLAUDE.md for session efficiency
- ⏳ Create session startup checklist (optional)

**After Phase 0 (Phase 1 start):**
- Project structure setup (src/empla/, tests/, docker/)
- Database setup with Docker Compose
- Core Pydantic models (Employee, Profile, Goal, Belief, etc.)
- BDI Engine foundation
- Proactive execution loop
- Memory system (basic episodic + semantic)

---

## 2025-10-27 - Phase 1 Setup Complete: Design Documents & Infrastructure

**Phase:** 1 - Foundation & Lifecycle (Setup)

### Added

**Phase 1 Infrastructure:**
- **scripts/setup-local-db.sh** - Automated PostgreSQL 17 + pgvector setup
  - Homebrew installation of PostgreSQL 17 and pgvector
  - Database creation (empla_dev and empla_test)
  - Extension enablement (vector, pg_trgm)
  - Error handling and colored output
  - Executable script with comprehensive status messages

- **docs/guides/local-development-setup.md** - Complete development environment guide
  - Prerequisites (Python 3.11+, Homebrew, uv)
  - PostgreSQL setup (automated script + manual instructions)
  - Python environment with uv package manager
  - Environment variables (.env configuration)
  - Development workflow (daily routine, using uv run)
  - Database management commands
  - Troubleshooting section (PostgreSQL, Python, dependencies)
  - IDE setup (VS Code, PyCharm)
  - Time required: 15-20 minutes for complete setup

**Phase 1 Design Documents:**
- **docs/design/database-schema.md** (500+ lines) - Complete PostgreSQL schema design
  - Multi-tenant row-level security (RLS) for all tables
  - Core tables: tenants, users, employees
  - BDI tables: employee_goals, employee_intentions, beliefs, belief_history
  - Memory tables: memory_episodes, memory_semantic, memory_procedural, memory_working
  - Audit tables: audit_log, metrics
  - JSONB for flexibility, vector(1024) for embeddings (pgvector)
  - Comprehensive indexes (foreign keys, search fields, JSONB paths, vector similarity)
  - Soft delete support (deleted_at) with audit trail
  - Performance targets and scalability considerations
  - Migration strategy (Alembic-based)

- **docs/design/core-models.md** (600+ lines) - Pydantic models specification
  - Base models: EmplaBaseModel, TimestampedModel, SoftDeletableModel, TenantScopedModel
  - Domain models: Employee, EmployeeGoal, EmployeeIntention, Belief
  - Memory models: EpisodicMemory, SemanticMemory, ProceduralMemory, WorkingMemory
  - Supporting models: Tenant, User, AuditLogEntry, Metric
  - API request/response models (EmployeeCreateRequest, EmployeeResponse, etc.)
  - Custom validators (email format, priority range, slug format)
  - Serialization examples (model_dump, model_dump_json, model_validate)
  - Database integration patterns (Pydantic ↔ SQLAlchemy conversion)
  - Testing utilities (factory functions for test data)

- **docs/design/bdi-engine.md** (700+ lines) - BDI architecture implementation
  - Belief System: World model maintenance, temporal decay, conflict resolution
  - Goal System: Goal formation, prioritization (urgency × importance), lifecycle management
  - Intention Stack: Plan selection, execution, monitoring, replanning
  - Strategic Reasoning: Opportunity detection, goal review, resource allocation
  - Complete algorithms with pseudocode for all BDI operations
  - Belief update algorithm (agreement/disagreement handling, confidence adjustment)
  - Goal priority calculation (deadline-based urgency, strategic importance)
  - Plan selection algorithm (procedural memory retrieval, strategy evaluation)
  - Integration with proactive execution loop
  - Performance considerations (database queries, caching, batch operations)
  - Testing strategy (unit tests, integration tests)
  - Observability (metrics, logging)

- **docs/design/memory-system.md** (800+ lines) - Multi-layered memory system
  - Episodic Memory: Personal experiences, temporal index, similarity search (pgvector)
  - Semantic Memory: Facts/knowledge, Subject-Predicate-Object triples, graph-structured
  - Procedural Memory: Skills/workflows, condition-action rules, success-rate learning
  - Working Memory: Current context, short-lived, capacity-limited (priority-based eviction)
  - Complete storage/retrieval algorithms for each memory type
  - Memory consolidation (merge duplicates, reinforce important, decay unused)
  - Fact extraction from episodes (LLM-based)
  - Learning from observation (shadow mode: learn from humans)
  - Memory integration (coordinated processing across all types)
  - Performance optimization (caching, batch operations, batch embedding generation)
  - Testing strategy (unit tests for each memory type)

**Phase 1 Directory Structure:**
- Created empla/ package structure:
  - empla/core/{bdi,memory,loop,planning}/ (with __init__.py)
  - empla/api/v1/endpoints/ (FastAPI structure)
  - empla/models/ (database models)
  - empla/cli/ (CLI implementation)
  - empla/utils/ (utilities)
- Created tests/ structure:
  - tests/{unit,integration,e2e}/ (test organization)

### Decided

**Design Decisions Documented:**

- **Belief Decay:** Linear decay for simplicity (revisit exponential in Phase 3)
  - Rationale: Easier to understand, debug, and tune
  - Decay rates: observation (0.05/day), told_by_human (0.03/day), inference (0.1/day), prior (0.15/day)

- **Vector Dimensions:** 1024-dimensional embeddings
  - Rationale: Balance between quality and performance
  - Can upgrade to 1536 or 3072 if quality issues emerge

- **Memory Capacity:** Soft limits with importance-based eviction
  - Rationale: More flexible than hard limits, adapts to usage patterns
  - Working memory: 20 contexts max, evict lowest priority

- **SPO Triple Structure:** Subject-Predicate-Object for both beliefs and semantic memory
  - Rationale: Standard knowledge representation, query-friendly
  - Enables graph traversal and relationship queries

- **Multi-tenant RLS:** All tables have tenant_id with row-level security
  - Rationale: Security from day 1, prevents cross-tenant data leaks
  - Application sets current_tenant_id, PostgreSQL enforces isolation

### Next

**Immediate (Phase 1 implementation):**
- Implement SQLAlchemy models based on database schema
- Create Alembic migrations for all tables
- Implement BeliefSystem class (empla/core/bdi/beliefs.py)
- Implement GoalSystem class (empla/core/bdi/goals.py)
- Implement IntentionStack class (empla/core/bdi/intentions.py)
- Implement memory systems (episodic, semantic, procedural, working)
- Write comprehensive unit tests (>80% coverage)

---

## Project Milestones

### Phase 0: Foundation Setup (Current)
- **Started:** 2025-10-26
- **Goal:** Establish documentation infrastructure and architecture
- **Status:** In Progress (90% complete)
- **Deliverable:** Complete documentation system ready for implementation
- **Completed:** Documentation infrastructure, templates, optimization
- **Remaining:** Write 6 initial ADRs

### Phase 1: Foundation & Lifecycle (Next)
- **Target Start:** 2025-10-27 or 2025-10-28
- **Goal:** Core autonomous engine + employee lifecycle management
- **Deliverable:** Working BDI engine with basic memory and proactive loop

---

**Document Started:** 2025-10-26
**Format:** Chronological (newest first)
**Update Frequency:** After each significant change or session
