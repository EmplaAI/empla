# ADR-005: Use pgvector for Initial Vector Storage

**Status:** Accepted

**Date:** 2025-10-26

**Deciders:** Navin (Founder), Claude Code (Architect)

**Tags:** vector-database, memory, embeddings, storage

---

## Context

empla's memory systems require vector similarity search for:
- **Episodic memory retrieval:** "Find similar past situations"
- **Semantic memory search:** "Find relevant knowledge"
- **Procedural memory matching:** "Find similar workflows that worked before"
- **RAG for knowledge synthesis:** "Retrieve relevant documents to inform LLM"

Vectors are generated from:
- Employee observations and experiences (episodic)
- Knowledge base documents (semantic)
- Successful strategies and workflows (procedural)
- Conversations and interactions

Expected scale (Year 1):
- 100 customers × 10 employees × 1000 memories = **~1M vectors**
- Each vector: 1536 dimensions (OpenAI embedding model)
- Growth rate: ~100K vectors/month

The question: Use a dedicated vector database (Qdrant, Weaviate, Pinecone) or PostgreSQL's pgvector extension?

This decision affects:
- Operational complexity (number of databases to manage)
- Query performance for memory retrieval
- Cost (managed services vs. self-hosted)
- Migration effort if we outgrow initial choice

---

## Decision

**Use pgvector (PostgreSQL extension) for initial vector storage.**

**Do NOT** deploy a dedicated vector database (Qdrant, Weaviate, Pinecone) unless proven necessary.

**Specific implementation:**
- Install pgvector extension in PostgreSQL (same DB as ADR-001)
- Store vectors alongside relational data (employees, memories, metadata)
- Use HNSW index for fast similarity search
- Co-locate vectors with their metadata (no separate system)

**Migration trigger:**
- If we exceed **10M vectors** OR
- If p95 latency exceeds **100ms** for similarity search
- Then evaluate dedicated vector DB

---

## Rationale

### Key Reasons

1. **pgvector Handles Our Scale:**
   - Proven to handle **10M+ vectors** efficiently
   - HNSW indexing provides fast approximate nearest neighbor search
   - Our Year 1 scale: ~1M vectors (well within pgvector capacity)
   - **No need for specialized DB yet**

2. **Operational Simplicity:**
   - Same database as relational data (PostgreSQL from ADR-001)
   - No additional system to deploy, monitor, backup
   - No data sync issues between vector DB and main DB
   - **One database instead of two**

3. **Data Locality:**
   - Vectors stored alongside metadata (employee_id, timestamp, content)
   - Single query joins vectors + metadata (no cross-DB queries)
   - ACID transactions across vectors and relational data
   - **Simpler queries, better consistency**

4. **Cost Efficiency:**
   - No separate managed service fees (Pinecone, etc.)
   - No additional infrastructure costs
   - Already running PostgreSQL
   - **Saves $100-500/month on infrastructure**

5. **Good Enough Performance:**
   - pgvector with HNSW index: <10ms for 1M vectors
   - Adequate for memory retrieval (don't need <1ms latency)
   - Can optimize with better indexing if needed
   - **Optimize when proven necessary, not speculatively**

6. **Future Flexibility:**
   - If pgvector becomes bottleneck: migrate to Qdrant/Weaviate
   - Abstraction layer makes migration straightforward
   - Not locked in (can change when needed)
   - **Start simple, specialize when proven necessary**

### Trade-offs Accepted

**What we're giving up:**
- ❌ Optimized vector search performance (Qdrant would be faster at 100M+ vectors)
- ❌ Advanced vector features (hybrid search, multi-vector queries, etc.)
- ❌ Specialized monitoring and tooling for vector operations

**Why we accept these trade-offs:**
- We won't hit 10M vectors for 1-2 years
- Advanced features not needed yet (simple similarity search sufficient)
- PostgreSQL monitoring is mature (don't need vector-specific tools)
- **Optimize for simplicity now, performance when needed**

---

## Alternatives Considered

### Alternative 1: Qdrant (Open-Source Vector DB)

**Pros:**
- Optimized for vector search (faster than pgvector at scale)
- Advanced features (filters, hybrid search, multi-vectors)
- Good Rust-based performance
- Self-hosted (no vendor lock-in)

**Cons:**
- Additional system to deploy and manage
- Vectors separate from relational data (sync challenges)
- Overkill for 1M vectors (optimized for 100M+)
- Learning curve for new database
- **Premature optimization**

**Why rejected:** Qdrant is excellent but overkill for our scale. pgvector is good enough for 1M vectors. If we hit 10M+ vectors, we can migrate.

### Alternative 2: Weaviate (Vector DB with ML Models)

**Pros:**
- Built-in vectorization (don't need to generate embeddings)
- GraphQL API
- Good community

**Cons:**
- Additional system to manage
- Built-in vectorization not as good as specialized embedding models
- More complex than needed
- **Adds complexity without clear benefit**

**Why rejected:** Built-in vectorization is not better than OpenAI/Anthropic embeddings. Adds a system without clear value.

### Alternative 3: Pinecone (Managed Vector DB)

**Pros:**
- Fully managed (no ops burden)
- Scales automatically
- Good performance

**Cons:**
- Expensive ($70-500+/month)
- Vendor lock-in
- Overkill for 1M vectors
- **Costs more, provides less control**

**Why rejected:** Managed service costs add up quickly. pgvector is free (already running PostgreSQL). If we need managed, we can switch later.

### Alternative 4: ChromaDB (Lightweight Vector DB)

**Pros:**
- Very simple setup
- Good for small scale
- Python-native

**Cons:**
- Less mature than pgvector or Qdrant
- Performance unclear at scale
- Still requires separate system
- **Not clearly better than pgvector**

**Why rejected:** ChromaDB doesn't provide clear advantage over pgvector. pgvector is more mature and battle-tested.

---

## Consequences

### Positive

- ✅ **Operational simplicity:** One database instead of two
- ✅ **Data locality:** Vectors + metadata in same system
- ✅ **Cost savings:** No additional infrastructure or managed service fees
- ✅ **Adequate performance:** <10ms for 1M vectors with HNSW index
- ✅ **Easy migration path:** Can move to Qdrant if proven necessary

### Negative

- ❌ **Performance ceiling:** May hit limits at 10M+ vectors
- ❌ **Less specialized:** Dedicated vector DBs have more features
- ❌ **Migration cost:** If we outgrow pgvector, migration has some cost

### Neutral

- ⚪ **pgvector extension dependency:** Requires extension installation (but well-supported)

---

## Implementation Notes

**Phase 1 Setup:**

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create table with vector column
CREATE TABLE employee_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES employees(id),
    memory_type VARCHAR(50) NOT NULL,  -- episodic, semantic, procedural
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI embedding size
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Indexes
    CONSTRAINT valid_memory_type CHECK (memory_type IN ('episodic', 'semantic', 'procedural'))
);

-- Create HNSW index for fast similarity search
CREATE INDEX ON employee_memories USING hnsw (embedding vector_cosine_ops);

-- Index for filtering by employee and type
CREATE INDEX ON employee_memories(employee_id, memory_type);
```

**Query Example:**

```python
# Find similar memories for an employee
async def find_similar_memories(
    employee_id: UUID,
    query_embedding: List[float],
    memory_type: str,
    limit: int = 10
) -> List[Memory]:
    """Find memories similar to query embedding."""

    query = """
        SELECT id, content, metadata, created_at,
               embedding <=> $1::vector AS distance
        FROM employee_memories
        WHERE employee_id = $2
          AND memory_type = $3
        ORDER BY embedding <=> $1::vector
        LIMIT $4
    """

    results = await db.fetch(
        query,
        query_embedding,
        employee_id,
        memory_type,
        limit
    )

    return [Memory.from_row(row) for row in results]
```

**Performance Optimization:**

1. **HNSW Index Parameters:**
   - `m` (max connections): 16 (default, good for most cases)
   - `ef_construction`: 64 (higher = better index quality, slower build)
   - Tune based on actual performance

2. **Partitioning:**
   - If we exceed 5M memories, partition by employee_id
   - Each partition stays small and fast

3. **Monitoring:**
   - Track query latency (p50, p95, p99)
   - Track index size and memory usage
   - Set alerts: p95 > 100ms triggers investigation

**Migration Path (if needed):**

If we hit 10M vectors with >100ms latency:

1. **Evaluate alternatives:**
   - Qdrant (if self-hosted preferred)
   - Weaviate (if GraphQL preferred)
   - Pinecone (if managed service preferred)

2. **Implement abstraction layer:**
   ```python
   class VectorStore(Protocol):
       async def store(self, embedding: List[float], metadata: Dict) -> str: ...
       async def search(self, query: List[float], limit: int) -> List[Memory]: ...

   class PgVectorStore(VectorStore): ...
   class QdrantStore(VectorStore): ...
   ```

3. **Migrate incrementally:**
   - Deploy Qdrant alongside PostgreSQL
   - Write new vectors to both (dual-write)
   - Backfill old vectors to Qdrant
   - Switch reads to Qdrant
   - Remove PostgreSQL vectors

**Timeline:**
- Implementation: Phase 1
- Performance monitoring: Ongoing
- Re-evaluate: If we hit 10M vectors (Year 2-3) or 100ms latency

---

## Validation Criteria

**How will we know if this decision was correct?**

**Success Metrics:**
1. **Performance:** p95 latency <100ms for similarity search
2. **Scale:** Handles 1M vectors without degradation
3. **Operational simplicity:** No additional database operations burden
4. **Cost:** Zero additional infrastructure costs

**Revisit Triggers:**

We should reconsider this decision if:
1. **Scale exceeded:** >10M vectors in database
2. **Latency exceeded:** p95 latency >100ms consistently
3. **Feature needs:** Require advanced vector features (hybrid search, multi-vector, etc.)
4. **Query complexity:** Need complex vector operations pgvector doesn't support

**Review date:** When we hit 5M vectors (Year 1-2) or if latency issues arise

---

## References

- **pgvector Documentation:** https://github.com/pgvector/pgvector
- **HNSW Algorithm:** "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs" (Malkov & Yashunin, 2018)
- **pgvector Performance:** https://supabase.com/blog/pgvector-performance
- **Related ADRs:**
  - ADR-001: PostgreSQL as primary database
  - ADR-004: Defer agent framework decision
- **Discussion:** Initial architecture planning session (2025-10-25)

---

**Created:** 2025-10-26
**Last Updated:** 2025-10-26
**Author:** Claude Code
**Approved By:** Navin (Founder)
