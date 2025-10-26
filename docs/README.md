# empla Documentation

This directory contains all technical documentation, architectural decisions, design documents, and guides for empla.

## Directory Structure

```
docs/
├── README.md                    # This file
├── decisions/                   # Architecture Decision Records (ADRs)
│   ├── template.md             # ADR template
│   └── NNN-title.md            # Individual ADRs (numbered sequentially)
├── design/                      # Feature design documents
│   ├── template.md             # Design doc template
│   └── feature-name.md         # Individual feature designs
├── api/                         # API documentation
│   └── [Coming in Phase 2]
└── guides/                      # How-to guides
    └── [Coming in Phase 6]
```

## Documentation Types

### 📋 Architecture Decision Records (ADRs)

**Location:** `docs/decisions/`

**Purpose:** Document significant architectural and technology decisions

**When to create:** Before making any major architectural choice

**Template:** See `docs/decisions/template.md`

**Naming Convention:** `NNN-short-title.md` (e.g., `001-postgresql-primary-database.md`)

**Status Values:**
- **Proposed:** Decision is under consideration
- **Accepted:** Decision has been made and approved
- **Deprecated:** Decision is no longer relevant
- **Superseded:** Replaced by another ADR (reference it)

**Example ADRs:**
- ADR-001: Why PostgreSQL as primary database
- ADR-002: Python + FastAPI stack choice
- ADR-003: BDI architecture decision
- ADR-004: Defer agent framework to Phase 2
- ADR-005: Use pgvector for initial vector storage
- ADR-006: Proactive loop over event-driven architecture

### 🎨 Design Documents

**Location:** `docs/design/`

**Purpose:** Pre-implementation design for complex features (>500 lines of code)

**When to create:** Before implementing any major feature or component

**Template:** See `docs/design/template.md`

**Naming Convention:** `feature-name.md` (e.g., `bdi-engine.md`, `memory-system.md`)

**Status Values:**
- **Draft:** Design is being written
- **In Progress:** Implementation has started
- **Implemented:** Feature is complete
- **Deprecated:** Feature is no longer used

**Required Sections:**
- Problem statement
- Solution approach
- API design (public + internal)
- Data models (DB schema + Pydantic)
- Implementation plan (phased)
- Testing strategy
- Migration path
- Security considerations

**Example Design Docs:**
- bdi-engine.md
- memory-system.md
- proactive-loop.md
- employee-lifecycle.md
- human-digital-interaction.md
- multi-agent-collaboration.md

### 📚 API Documentation

**Location:** `docs/api/`

**Purpose:** API reference for developers using empla

**When to create:** Phase 2+ (after core code exists)

**Content:**
- Employee API reference
- Capability APIs
- Integration APIs
- Webhook documentation
- Authentication & authorization

**Status:** Not created yet (Phase 2+)

### 📖 Guides

**Location:** `docs/guides/`

**Purpose:** Step-by-step how-to guides for common tasks

**When to create:** Phase 6+ (deployment and operations)

**Content:**
- Development setup guide
- Database setup guide
- Deployment guide (Docker, Kubernetes)
- Troubleshooting guide
- Performance tuning guide

**Status:** Not created yet (Phase 6+)

## Writing Guidelines

### ADR Guidelines

1. **Be concise but complete** - Include all context needed to understand the decision
2. **Document alternatives** - Show what options were considered and why rejected
3. **Include consequences** - Both positive and negative outcomes
4. **Add validation criteria** - How will we know if this was the right choice?
5. **Link to references** - Research, discussions, related ADRs

### Design Doc Guidelines

1. **Start with the problem** - Why does this feature exist?
2. **Show your work** - Include diagrams, examples, code snippets
3. **Think about edge cases** - Error handling, performance, security
4. **Plan for testing** - What tests will prove this works?
5. **Consider migration** - How does this deploy without breaking things?
6. **Write before coding** - Design docs should be written BEFORE implementation

### General Guidelines

- **Use Markdown** - All docs use GitHub-flavored Markdown
- **Include examples** - Code examples help understanding
- **Keep it updated** - Update docs when implementation changes
- **Link liberally** - Connect related docs, issues, PRs
- **Write for humans** - Assume reader doesn't have full context

## Document Lifecycle

### Creating a New ADR

1. Copy `docs/decisions/template.md`
2. Name it with next sequential number: `NNN-short-title.md`
3. Fill in all sections (delete template comments)
4. Set status to "Proposed"
5. Get feedback from team/stakeholders
6. Update status to "Accepted" when decision is made
7. Reference the ADR number in code comments where decision is implemented

### Creating a New Design Doc

1. Copy `docs/design/template.md`
2. Name it descriptively: `feature-name.md`
3. Fill in all sections (focus on Problem, Solution, API, Data Models)
4. Set status to "Draft"
5. Review with team before implementation
6. Update status to "In Progress" when coding starts
7. Update status to "Implemented" when complete
8. Keep doc updated if implementation diverges from design

## Finding Documentation

### By Topic

- **Architecture decisions:** Check `docs/decisions/`
- **Feature designs:** Check `docs/design/`
- **System overview:** Check `../ARCHITECTURE.md`
- **Development workflow:** Check `../CLAUDE.md`
- **Public intro:** Check `../README.md`
- **Current work:** Check `../TODO.md`
- **Recent changes:** Check `../CHANGELOG.md`

### By Status

Use `grep` to find documents by status:

```bash
# Find all accepted ADRs
grep -l "Status: Accepted" docs/decisions/*.md

# Find design docs in progress
grep -l "Status: In Progress" docs/design/*.md
```

### By Date

Use `ls` with time sorting:

```bash
# Most recently modified ADRs
ls -lt docs/decisions/*.md | head

# Oldest design docs
ls -ltr docs/design/*.md | head
```

## Contributing Documentation

When making a significant change:

1. **Update relevant docs** - Don't let docs drift from reality
2. **Create ADR if needed** - Major decisions need ADRs
3. **Update CHANGELOG.md** - Track what changed
4. **Link from code** - Add comments like "See ADR-XXX" or "See docs/design/feature.md"

## Questions?

If you're not sure whether something needs an ADR or design doc:

**Create an ADR if:**
- You're making an architectural choice
- You're selecting between technology options
- The decision will be hard to reverse
- Future developers will ask "why did we do it this way?"

**Create a design doc if:**
- The feature is >500 lines of code
- Multiple components are involved
- The approach is not obvious
- You need to think through the design before coding

**When in doubt:** Create the document. Over-documentation is better than under-documentation.

---

**Documentation Health:** ✅ Infrastructure established (templates created)
**Next Step:** Write initial ADRs for existing decisions
**Maintained By:** Claude Code (empla's first digital employee)
