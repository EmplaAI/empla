# ADR-002: Python 3.11+ and FastAPI as Core Stack

**Status:** Accepted

**Date:** 2025-10-26

**Deciders:** Navin (Founder), Claude Code (Architect)

**Tags:** technology-stack, programming-language, web-framework

---

## Context

empla requires a technology stack that supports:
- **Async I/O:** Handling hundreds of concurrent employee operations efficiently
- **Type safety:** Catching bugs at development time, not production
- **AI/ML integration:** Seamless integration with LLMs, embeddings, RAG systems
- **Web APIs:** REST/WebSocket endpoints for employee management and monitoring
- **Developer productivity:** Fast iteration, good tooling, clear abstractions
- **Production readiness:** Mature ecosystem, proven at scale, strong community

The language and framework choice affects:
- Development velocity and iteration speed
- Ability to hire/onboard contributors
- Integration with AI/ML libraries and tools
- Performance characteristics
- Long-term maintainability

We need to choose a stack that balances productivity (for rapid development) with production quality (for reliability at scale).

---

## Decision

**Use Python 3.11+ with FastAPI as the core technology stack.**

**Specific implementation:**
- **Language:** Python 3.11+ (for performance improvements and modern features)
- **Web framework:** FastAPI (async-native, type-safe, auto-generated docs)
- **Type checking:** Pydantic v2 for data validation, mypy for static type checking
- **Async runtime:** AsyncIO (Python's built-in async framework)
- **Data models:** Pydantic BaseModel for all data structures
- **API docs:** Auto-generated OpenAPI/Swagger via FastAPI

---

## Rationale

### Key Reasons

1. **Python Dominates AI/ML Ecosystem:**
   - ✅ LangChain, LlamaIndex, Anthropic SDK all in Python
   - ✅ Embedding models (sentence-transformers) in Python
   - ✅ Vector database clients (pgvector, Qdrant) have excellent Python support
   - ✅ RAG frameworks, agent tools, prompt engineering - all Python-first
   - **AI/ML integration is seamless, not a constant battle**

2. **FastAPI is Async-Native:**
   - ✅ Built on AsyncIO from the ground up (not bolted on)
   - ✅ Handles hundreds of concurrent requests efficiently
   - ✅ Perfect for long-running employee operations (don't block)
   - ✅ WebSocket support for real-time employee status updates
   - **Critical for managing many autonomous employees concurrently**

3. **Type Safety from Day 1:**
   - ✅ Pydantic v2 enforces data validation at runtime
   - ✅ mypy catches type errors at development time
   - ✅ FastAPI uses types for automatic request/response validation
   - ✅ IDEs provide excellent autocomplete and error detection
   - **Prevents entire classes of bugs before they reach production**

4. **Excellent Developer Experience:**
   - ✅ Auto-generated API documentation (OpenAPI/Swagger)
   - ✅ Interactive API testing built-in (Swagger UI)
   - ✅ Clear error messages and stack traces
   - ✅ Minimal boilerplate code
   - ✅ Extensive ecosystem of libraries and tools
   - **Fast iteration and easy debugging**

5. **Production-Ready:**
   - ✅ Used by companies like Microsoft, Uber, Netflix at scale
   - ✅ Battle-tested in production environments
   - ✅ Excellent performance (comparable to Node.js/Go for I/O-bound tasks)
   - ✅ Strong community and long-term support
   - **Not a risky bet - proven at enterprise scale**

6. **Python 3.11+ Performance Improvements:**
   - ✅ 10-60% faster than Python 3.10 (CPython optimizations)
   - ✅ Better error messages (PEP 657)
   - ✅ Task groups for structured concurrency
   - ✅ TypedDict improvements for type safety
   - **Modern Python is fast enough for our needs**

### Trade-offs Accepted

**What we're giving up:**
- ❌ Lower-level performance (Rust/Go would be faster for CPU-bound tasks)
- ❌ Smaller binary size (Go/Rust compile to smaller binaries)
- ❌ Stronger compile-time guarantees (Rust's borrow checker)

**Why we accept these trade-offs:**
- empla is **I/O-bound**, not CPU-bound (waiting on LLMs, databases, APIs)
- Python's async I/O handles this efficiently
- We can optimize hot paths with Rust/Cython if needed (but unlikely)
- **Developer productivity and AI/ML ecosystem > raw performance**

---

## Alternatives Considered

### Alternative 1: Go + Gin/Echo

**Pros:**
- Excellent concurrency (goroutines)
- Fast compilation and execution
- Small binary size
- Strong standard library

**Cons:**
- AI/ML ecosystem is weak (most libraries Python-only)
- Would need to write custom bindings for LangChain, LlamaIndex, etc.
- Less expressive for complex data models
- Smaller community for web development
- No auto-generated API docs like FastAPI

**Why rejected:** AI/ML integration would be painful. Anthropic SDK, LangChain, LlamaIndex are all Python-first. Building empla in Go means fighting the ecosystem constantly.

### Alternative 2: Rust + Axum/Actix

**Pros:**
- Maximum performance and memory safety
- Strong type system (borrow checker prevents bugs)
- Excellent for systems programming
- Growing ecosystem

**Cons:**
- Steep learning curve (slows development)
- AI/ML ecosystem is immature (most libraries Python-only)
- Longer compile times
- Smaller talent pool for hiring
- Over-engineering for I/O-bound workload

**Why rejected:** empla doesn't need Rust's performance (we're I/O-bound). The borrow checker slows rapid iteration. AI/ML ecosystem is Python-first. **Optimizing for the wrong thing** (memory safety over development velocity).

### Alternative 3: Node.js + Express/Nest.js

**Pros:**
- JavaScript everywhere (frontend + backend)
- Large ecosystem and community
- Good async I/O performance
- Easy to hire JavaScript developers

**Cons:**
- Weak AI/ML ecosystem (most libraries Python-only)
- Loose typing (TypeScript helps but not as strong as Python + Pydantic)
- Less mature for data science/ML workloads
- npm ecosystem has stability issues

**Why rejected:** Python dominates AI/ML. Anthropic SDK, LangChain, LlamaIndex all Python-first. TypeScript's types aren't as robust as Pydantic for runtime validation.

### Alternative 4: Python + Django

**Pros:**
- Mature framework with batteries included
- Excellent ORM (Django ORM)
- Built-in admin panel
- Large community

**Cons:**
- Not async-native (bolted-on async support)
- Heavier framework (more opinionated)
- Slower for API-only applications
- More boilerplate than FastAPI

**Why rejected:** Django is optimized for traditional web apps (HTML rendering). FastAPI is optimized for APIs. We don't need Django's template engine, admin panel, etc. FastAPI is lighter, faster, and async-native.

---

## Consequences

### Positive

- ✅ **Seamless AI/ML integration:** Anthropic SDK, LangChain, LlamaIndex work out of the box
- ✅ **Fast development velocity:** Clear syntax, minimal boilerplate, excellent tooling
- ✅ **Type safety:** Pydantic + mypy catch bugs early
- ✅ **Auto-generated docs:** FastAPI creates OpenAPI/Swagger automatically
- ✅ **Async-native:** Handles hundreds of concurrent employees efficiently
- ✅ **Large talent pool:** Easy to find Python developers
- ✅ **Production-proven:** Used at scale by major companies

### Negative

- ❌ **Not the fastest language:** Rust/Go would be faster for CPU-bound tasks
- ❌ **GIL limitations:** True parallelism requires multiprocessing (but async handles I/O well)
- ❌ **Deployment size:** Larger than compiled languages (but Docker mitigates this)

### Neutral

- ⚪ **Python version dependency:** Requires Python 3.11+ (but widely available)
- ⚪ **Type checking optional:** mypy is optional (but we'll enforce it)

---

## Implementation Notes

**Steps:**

1. **Phase 1 (Foundation):**
   - Set up Python 3.11+ environment with Poetry/uv for dependency management
   - Install FastAPI, Pydantic v2, mypy, ruff (linter/formatter)
   - Configure pre-commit hooks for type checking and formatting
   - Create base FastAPI application structure

2. **Phase 2 (Data Models):**
   - Define Pydantic models for all data structures (Employee, Goal, Belief, etc.)
   - Add validation rules and custom validators
   - Enable mypy strict mode for maximum type safety

3. **Phase 3 (APIs):**
   - Implement REST endpoints for employee management
   - Add WebSocket endpoints for real-time updates
   - Auto-generate OpenAPI documentation
   - Add request/response validation

4. **Phase 4 (Production):**
   - Configure uvicorn (ASGI server) for production
   - Add structured logging (JSON format)
   - Add metrics (Prometheus)
   - Deploy with Docker + Kubernetes

**Code Standards:**
```python
# All data models use Pydantic
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from uuid import UUID

class EmployeeProfile(BaseModel):
    """Employee profile data model."""

    id: UUID
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    role: EmployeeRole
    status: EmployeeStatus = EmployeeStatus.ONBOARDING
    created_at: datetime
    updated_at: datetime

# All API endpoints use FastAPI with type hints
from fastapi import FastAPI, HTTPException, status

app = FastAPI(
    title="empla API",
    description="Production-Ready Digital Employees + Platform",
    version="0.1.0"
)

@app.post("/employees", response_model=EmployeeProfile, status_code=status.HTTP_201_CREATED)
async def create_employee(
    name: str,
    role: EmployeeRole,
    config: Optional[EmployeeConfig] = None
) -> EmployeeProfile:
    """Create a new digital employee."""
    # Type safety enforced by FastAPI + Pydantic
    # Request/response validation automatic
    # OpenAPI docs auto-generated
```

**Timeline:**
- Decision made: 2025-10-26
- Implementation start: Phase 1 (next)
- First API deployment: Phase 1 completion

**Dependencies:**
- Python 3.11+ (install via pyenv or system package manager)
- FastAPI, Pydantic v2, mypy, ruff (install via Poetry/uv)
- uvicorn for ASGI server

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**
1. **Development velocity:** Shipping features rapidly without fighting the stack
2. **AI/ML integration:** Seamless integration with Anthropic, LangChain, LlamaIndex
3. **Type safety:** <5 type-related bugs in production (mypy catches them early)
4. **Performance:** API latency <100ms p95 for employee operations
5. **Developer satisfaction:** Contributors find the stack easy to work with

**Revisit Triggers:**

We should reconsider this decision if:
1. **Performance becomes bottleneck:** Python async can't handle load (unlikely for I/O-bound)
2. **AI/ML ecosystem shifts away from Python:** (extremely unlikely)
3. **Type safety insufficient:** Pydantic + mypy don't catch enough bugs (unlikely)
4. **Better alternatives emerge:** (monitor but Python/FastAPI are stable choices)

**Review date:** After Phase 2 completion (3 months from decision)

---

## References

- **FastAPI Documentation:** https://fastapi.tiangolo.com/
- **Pydantic V2 Documentation:** https://docs.pydantic.dev/
- **Python 3.11 Release Notes:** https://docs.python.org/3/whatsnew/3.11.html
- **AsyncIO Documentation:** https://docs.python.org/3/library/asyncio.html
- **Related ADRs:**
  - ADR-001: PostgreSQL as primary database
  - ADR-003: Custom BDI architecture over frameworks
- **Discussion:** Initial architecture planning session (2025-10-25)

---

**Created:** 2025-10-26
**Last Updated:** 2025-10-26
**Author:** Claude Code
**Approved By:** Navin (Founder)
