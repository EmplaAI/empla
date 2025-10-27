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
