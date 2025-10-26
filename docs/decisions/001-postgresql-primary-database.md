# ADR-001: PostgreSQL as Primary Database

**Status:** Accepted

**Date:** 2025-10-26

**Deciders:** Navin (Founder), Claude Code (Architect)

**Tags:** database, infrastructure, technology-stack

---

## Context

empla requires a database that can handle multiple data types and query patterns:
- **Relational data:** Employee profiles, goals, tasks, performance metrics
- **Semi-structured data:** Beliefs, observations, memory records (varying schemas)
- **Vector data:** Memory embeddings for semantic search/retrieval
- **Full-text search:** Search across employee communications, documents, knowledge
- **Time-series data:** Employee activity logs, performance tracking over time
- **Multi-tenancy:** Strict data isolation between customers (row-level security)

We need to choose a primary database that can handle these diverse requirements while being:
- Production-proven and reliable
- Scalable to handle 1000+ employees per customer
- Maintainable by a small team
- Well-documented with strong ecosystem

The decision affects:
- Development complexity (number of database systems to maintain)
- Operational complexity (deployment, backups, monitoring)
- Performance characteristics
- Future migration costs if we choose wrong

---

## Decision

**Use PostgreSQL 17 as the primary database for all data storage needs.**

**Specific implementation:**
- PostgreSQL 17+ with the following extensions:
  - `pgvector` for vector similarity search (memory embeddings)
  - `pg_trgm` for full-text search and fuzzy matching
  - Row-Level Security (RLS) for multi-tenant data isolation
- JSONB columns for semi-structured data (beliefs, observations, configurations)
- Standard relational tables for structured data (employees, goals, tasks)
- Materialized views for performance optimization
- TimescaleDB extension (optional, evaluate if time-series queries become bottleneck)

---

## Rationale

### Key Reasons

1. **PostgreSQL Handles All Our Data Types:**
   - ✅ Relational: Native support with ACID guarantees
   - ✅ Semi-structured: JSONB with indexing, validation, and efficient queries
   - ✅ Vector: pgvector extension handles millions of vectors
   - ✅ Full-text: Built-in full-text search + pg_trgm for fuzzy matching
   - ✅ Time-series: Native partitioning + optional TimescaleDB
   - **One database instead of five**

2. **Production-Proven at Scale:**
   - Used by companies like Instagram, Uber, Reddit at massive scale
   - 30+ years of development, battle-tested reliability
   - Strong ACID guarantees, robust transaction support
   - Excellent performance for both OLTP and OLAP workloads

3. **Multi-Tenancy Built-In:**
   - Row-Level Security (RLS) provides database-enforced tenant isolation
   - No application-level filtering needed (security at DB layer)
   - Prevents accidental data leaks between customers
   - Simpler than maintaining separate databases per tenant

4. **Excellent Developer Experience:**
   - Rich ecosystem: SQLAlchemy, asyncpg, Pydantic integration
   - Comprehensive documentation
   - Strong typing and constraints (data validation at DB level)
   - Helpful error messages and query planning tools

5. **Operational Simplicity:**
   - Single database to deploy, backup, monitor, and maintain
   - Cloud-managed options (AWS RDS, Google Cloud SQL, Azure Database)
   - Well-understood operational patterns
   - Mature tooling for migrations, backups, replication

6. **Future Flexibility:**
   - If we hit limits, we can migrate specific use cases:
     - Vectors → Qdrant if pgvector insufficient (>10M vectors)
     - Graph queries → Neo4j if complex traversals needed
     - Time-series → Dedicated TSDB if needed
   - But start simple, migrate only when proven necessary

### Trade-offs Accepted

**What we're giving up:**
- ❌ Specialized vector database (Qdrant, Weaviate) might be faster for vector search at very large scale
- ❌ Specialized graph database (Neo4j) might be better for complex graph traversals
- ❌ Specialized time-series database (InfluxDB) might be more efficient for metrics

**Why we accept these trade-offs:**
- We don't know our actual scale yet (might never need specialized DBs)
- Operational complexity of managing 4-5 databases is HIGH
- PostgreSQL is "good enough" for millions of vectors, basic graphs, time-series
- Can migrate later with abstraction layer (not locked in)
- **Optimize for simplicity now, specialize only when proven necessary**

---

## Alternatives Considered

### Alternative 1: MongoDB (NoSQL Document Store)

**Pros:**
- Flexible schema (good for varying belief structures)
- Horizontal scaling built-in (sharding)
- Good for semi-structured data

**Cons:**
- Weak support for relational data (employee hierarchies, task dependencies)
- No native vector search (would need separate vector DB)
- No full-text search as robust as PostgreSQL
- Multi-tenancy requires application-level filtering (security risk)
- Less mature ACID guarantees (eventual consistency issues)

**Why rejected:** We have significant relational data (employee profiles, goals, tasks, relationships). MongoDB would force us into multiple databases anyway (MongoDB + vector DB + potentially others). PostgreSQL handles our use case better.

### Alternative 2: Neo4j (Graph Database)

**Pros:**
- Excellent for relationship-heavy data (org charts, knowledge graphs)
- Cypher query language is expressive for graph traversals
- Good visualization tools

**Cons:**
- Not designed for relational data (employee profiles, metrics)
- No vector search (would need separate vector DB)
- No time-series optimization
- More complex to operate than PostgreSQL
- Smaller ecosystem and community

**Why rejected:** While we have some graph-like data (knowledge graphs, employee relationships), it's not our PRIMARY use case. PostgreSQL with recursive CTEs can handle our graph queries initially. If we prove we need complex graph traversals, we can add Neo4j later using PostgreSQL AGE extension as interim.

### Alternative 3: Qdrant/Weaviate (Specialized Vector DB)

**Pros:**
- Optimized for vector similarity search
- Fast at scale (100M+ vectors)
- Built-in filtering and metadata support

**Cons:**
- ONLY handles vectors, would need PostgreSQL anyway for other data
- Adds operational complexity (two databases to manage)
- Overkill for initial scale (we'll have <1M vectors for first year)

**Why rejected:** pgvector in PostgreSQL handles millions of vectors efficiently. We'd be adding a second database prematurely. If we prove we need >10M vectors with <10ms latency, we can migrate then.

### Alternative 4: Multi-Database Approach (Postgres + Neo4j + Qdrant)

**Pros:**
- "Best tool for each job"
- Optimal performance for each use case

**Cons:**
- HIGH operational complexity (3+ databases)
- Data consistency challenges (distributed transactions)
- More failure points
- Complex deployment and monitoring
- Over-engineering before we know our needs

**Why rejected:** Premature optimization. Start simple (PostgreSQL-only), add specialized databases ONLY when proven necessary with real usage data.

---

## Consequences

### Positive

- ✅ **Single database simplifies operations:** One system to deploy, backup, monitor, scale
- ✅ **Faster initial development:** No multi-database coordination, simpler data models
- ✅ **Strong data consistency:** ACID transactions across all data
- ✅ **Multi-tenant security built-in:** Row-Level Security at database level
- ✅ **Rich ecosystem:** Excellent tooling, libraries, community support
- ✅ **Future flexibility:** Can add specialized DBs later if proven necessary

### Negative

- ❌ **Potential performance limits:** If we hit >10M vectors or complex graph traversals, might need specialized DBs
- ❌ **Less optimal for some use cases:** Specialized DBs would be faster for their specific domains
- ❌ **Migration cost later:** If we need specialized DBs, migration has cost (but abstraction layer minimizes this)

### Neutral

- ⚪ **PostgreSQL learning curve:** Team needs PostgreSQL expertise (but well-documented, large community)
- ⚪ **Extension dependencies:** Relies on pgvector, pg_trgm extensions (but stable, widely used)

---

## Implementation Notes

**Steps:**

1. **Phase 1 (Foundation):**
   - Deploy PostgreSQL 17 with Docker for local development
   - Enable pgvector, pg_trgm extensions
   - Set up row-level security policies for multi-tenancy
   - Create initial schema (employees, profiles, goals, tasks)

2. **Phase 2 (Memory Systems):**
   - Add JSONB columns for beliefs, observations
   - Add vector columns for memory embeddings
   - Create indexes for efficient queries

3. **Phase 3 (Optimization):**
   - Profile query performance
   - Add materialized views for common queries
   - Optimize indexes based on actual usage

4. **Phase 4+ (Scale):**
   - Monitor vector search performance (if >10M vectors, evaluate Qdrant)
   - Monitor graph query performance (if complex traversals, evaluate Neo4j)
   - Migrate to specialized DBs ONLY if proven bottleneck

**Migration Path (if moving away from PostgreSQL):**

We'll use the **Repository Pattern** to abstract database access:
```python
class EmployeeRepository(Protocol):
    async def get_employee(self, id: UUID) -> Employee: ...
    async def save_employee(self, employee: Employee) -> None: ...

# Implementation can swap out
class PostgreSQLEmployeeRepository(EmployeeRepository): ...
class MultiDBEmployeeRepository(EmployeeRepository): ...  # Uses PostgreSQL + Neo4j + Qdrant
```

This allows us to migrate storage without changing application code.

**Timeline:**
- Decision made: 2025-10-26
- Implementation start: Phase 1 (next)
- First production deployment: Phase 1 completion

**Dependencies:**
- Requires PostgreSQL 17+ for best performance
- Requires pgvector extension (install via package manager)
- Cloud providers: AWS RDS, Google Cloud SQL, Azure Database all support PostgreSQL 17

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**
1. **Performance:** Query latency <100ms for 95th percentile
2. **Scale:** Handles 1000+ employees per customer without degradation
3. **Reliability:** >99.9% uptime, zero data loss
4. **Developer productivity:** Schema changes and queries are straightforward

**Revisit Triggers:**

We should reconsider this decision if:
1. **Vector search becomes bottleneck:** >10M vectors with >100ms latency
2. **Graph queries become complex:** Requires deeply nested recursive CTEs (>5 levels)
3. **Time-series queries slow:** Materialized views insufficient for analytics
4. **Multi-database abstraction is ready:** Repository pattern proven in production

**Review date:** After Phase 3 completion (6 months from decision)

---

## References

- **PostgreSQL Documentation:** https://www.postgresql.org/docs/17/
- **pgvector Extension:** https://github.com/pgvector/pgvector
- **Row-Level Security:** https://www.postgresql.org/docs/17/ddl-rowsecurity.html
- **Related ADRs:**
  - ADR-004: Defer agent framework decision to Phase 2
  - ADR-005: Use pgvector for initial vector storage
- **Discussion:** Initial architecture planning session (2025-10-25)

---

**Created:** 2025-10-26
**Last Updated:** 2025-10-26
**Author:** Claude Code
**Approved By:** Navin (Founder)
