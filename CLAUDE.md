# CLAUDE.md - empla Development Guide

> **Purpose:** Build empla - Production-Ready Digital Employees + Extensible Platform
> **Architecture:** See `ARCHITECTURE.md` for system design and roadmap

---

## Mission

**empla** is NOT another AI agent framework, chatbot, or RPA tool.

**empla IS:**
- Production-ready digital employees (Sales AE, CSM, PM, etc.)
- Extensible platform to build custom employees
- Autonomous workers with goals who work proactively
- The future of how AI integrates into organizations

---

## Core Principles

### 1. Autonomy First
Employees work without instructions. Every feature should ask: "Does this increase autonomy?"

### 2. Goal-Oriented, Not Task-Oriented
Employees have goals, not task lists. They set priorities, form strategies, adapt when strategies fail. Always use BDI architecture (Beliefs-Desires-Intentions).

### 3. Proactive, Not Reactive
Employees identify and create work. Monitor continuously, detect opportunities, take initiative. The proactive loop should ALWAYS be running.

### 4. Learning and Adaptation
Every action has an outcome, every outcome updates beliefs and skills. Procedural memory captures what works. Never build static workflows.

### 5. Production-Ready from Day 1
This runs real businesses. Non-negotiables:
- Comprehensive error handling
- Logging at appropriate levels
- Input validation
- Type hints everywhere
- Tests (>80% coverage)
- Security (parameterized queries, no secrets in code)

### 6. Developer Experience
Make it easy to create employees. If it takes >50 lines for a basic employee, refactor.

---

## Technology Stack

**Locked (foundational):**
- Python 3.11+, AsyncIO
- FastAPI
- PostgreSQL 17 (relational + JSONB + pgvector)
- Pydantic v2, mypy
- pytest, ruff, uv

**Deferred (choose when needed):**
- Agent frameworks, vector DBs, caching - see ARCHITECTURE.md

---

## Development Workflow

### Implementing Features

1. **Understand**: Read ARCHITECTURE.md, check TODO.md for priorities
2. **Design**: For complex features, use `feature-dev:code-architect` agent
3. **Implement**: Follow empla patterns (see skills: empla-bdi, empla-capability)
4. **Test**: Run `uv run pytest`, aim for >80% coverage
5. **Review**: Use `pr-review-toolkit:code-reviewer` on your changes
6. **Commit**: Use `/commit` command
7. **PR**: Use `/commit-push-pr` or create manually

### Plugin Usage Reference

| Task | Plugin/Command |
|------|----------------|
| Design complex feature | `feature-dev:code-architect` |
| Review code quality | `pr-review-toolkit:code-reviewer` |
| Check test coverage | `pr-review-toolkit:pr-test-analyzer` |
| Find error handling issues | `pr-review-toolkit:silent-failure-hunter` |
| Review type design | `pr-review-toolkit:type-design-analyzer` |
| Create commit | `/commit` |
| Commit + push + PR | `/commit-push-pr` |
| Explore codebase | `Explore` agent (via Task tool) |

### Common Commands

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=empla

# Lint
uv run ruff check empla/

# Type check
uv run mypy empla/

# Format
uv run ruff format empla/

# Start services
docker-compose up -d

# Database migrations
uv run alembic upgrade head
```

---

## Code Patterns

### Python Style
- Type hints on all functions
- Pydantic for data models
- async/await for I/O operations
- Google-style docstrings
- Descriptive names over abbreviations

### Architecture Patterns
- Dependency injection for testability
- Composition over inheritance
- Strategy pattern for behaviors
- Interface-based design for extensibility

### Example: Employee Implementation

```python
class SalesEmployee(DigitalEmployee):
    """Autonomous Sales AE that pursues pipeline goals."""

    @property
    def default_goals(self) -> list[GoalConfig]:
        return [
            GoalConfig(
                goal_type="maintain",
                description="Maintain 3x pipeline coverage",
                priority=9,
                target={"metric": "pipeline_coverage", "value": 3.0}
            )
        ]

    async def on_start(self) -> None:
        # Custom initialization
        await self.beliefs.add("role", "sales_ae", confidence=1.0)
```

---

## Anti-Patterns to Avoid

1. **Don't build chat interfaces** - Employees work autonomously
2. **Don't build simple schedulers** - Employees reason about when to act
3. **Don't build static workflows** - Use procedural memory
4. **Don't skip multi-tenancy** - tenant_id required everywhere
5. **Don't build without tests** - >80% coverage minimum
6. **Don't commit secrets** - Use environment variables

---

## Decision Framework

When faced with a design decision:

1. **Autonomy Test**: Does this increase employee autonomy?
2. **Scale Test**: Will this work with 100 employees? 1000 tenants?
3. **Learning Test**: Can the employee improve over time?
4. **Production Test**: Would you deploy this to run a real business?

If uncertain, choose the option that increases autonomy most.

---

## Project Structure

```
empla/
├── empla/
│   ├── bdi/              # BDI engine (beliefs, goals, intentions)
│   ├── capabilities/     # Capability framework (email, calendar, etc.)
│   ├── core/
│   │   ├── loop/         # Proactive execution loop
│   │   └── memory/       # Memory systems (episodic, semantic, procedural)
│   ├── employees/        # Employee implementations (SalesAE, CSM, etc.)
│   ├── llm/              # LLM providers (Anthropic, OpenAI, Vertex)
│   ├── models/           # Database models
│   └── api/              # FastAPI endpoints
├── tests/
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   ├── e2e/              # End-to-end tests
│   └── simulation/       # Simulation framework for autonomous testing
├── ARCHITECTURE.md       # Detailed system architecture
├── TODO.md               # Current priorities
└── CHANGELOG.md          # Change history
```

---

## Testing Strategy

### Test Types
- **Unit tests**: Business logic, data transformations
- **Integration tests**: Component interactions, database operations
- **E2E tests**: Complete workflows, autonomous behaviors
- **Simulation tests**: Test autonomous behavior with simulated environment

### Running Tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/unit/test_employees_base.py

# With coverage
uv run pytest --cov=empla --cov-report=html

# E2E tests only
uv run pytest tests/e2e/
```

### Test Patterns

Use the simulation framework for autonomous behavior:
```python
from tests.simulation import SimulatedEnvironment, SimulatedEmail

async def test_sales_ae_responds_to_low_pipeline():
    env = SimulatedEnvironment()
    env.set_pipeline_coverage(1.5)  # Below 3.0 target

    employee = SalesAE(config, capability_registry=env.registry)
    await employee.start(run_loop=False)
    await employee.run_once()

    # Employee should have formed intention to build pipeline
    assert employee.intentions.has_type("build_pipeline")
```

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `empla/employees/base.py` | Base DigitalEmployee class |
| `empla/bdi/beliefs.py` | BeliefSystem implementation |
| `empla/bdi/goals.py` | GoalSystem implementation |
| `empla/core/loop/execution.py` | Proactive execution loop |
| `empla/capabilities/base.py` | BaseCapability interface |
| `tests/simulation/` | Simulation framework for testing |

---

## Commit Message Format

```
type(scope): description

- Detail 1
- Detail 2

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

---

## When to Ask for Help

**Ask Navin:**
- Strategic decisions (major architecture changes)
- Requirements clarification
- Prioritization decisions
- External blockers

**Proceed autonomously:**
- Implementation details
- Testing strategies
- Code structure
- Bug fixes
- Documentation

---

## Success Criteria

- Employees work autonomously for extended periods
- They identify and pursue their own work
- They achieve measurable goals
- They improve over time
- New employee types are easy to create
- Tests pass with >80% coverage
- Code is clear and well-documented

---

## Resources

- `ARCHITECTURE.md` - Detailed system architecture and roadmap
- `TODO.md` - Current priorities and blockers
- `CHANGELOG.md` - Recent changes
- `docs/decisions/` - Architecture Decision Records
- `docs/resources.md` - Learning resources (BDI, RAG, multi-agent systems)
