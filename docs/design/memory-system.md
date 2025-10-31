# Memory System Design

> **Status:** Draft
> **Author:** Claude Code
> **Date:** 2025-10-27
> **Phase:** Phase 1 - Core Infrastructure

---

## Overview

This document defines empla's **multi-layered memory system** - one of the key advantages digital employees have over humans: **infinite, perfect memory**.

**What is the Memory System?**

A multi-layered architecture inspired by cognitive psychology and neuroscience:
- **Episodic Memory**: Personal experiences and events (what happened)
- **Semantic Memory**: Facts and knowledge (what I know)
- **Procedural Memory**: Skills and procedures (how to do things)
- **Working Memory**: Current context (what I'm thinking about now)

**Why Multiple Memory Types?**

Different types of information require different storage, retrieval, and update mechanisms:
- Episodic: Time-ordered, context-rich, similarity-based retrieval
- Semantic: Graph-structured, fact-based, query-based retrieval
- Procedural: Condition-action rules, success-rate learning
- Working: Short-lived, capacity-limited, priority-based eviction

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────┐
│              Proactive Execution Loop                │
└─────────────────────────────────────────────────────┘
                      │
         ┌────────────┴──────────┐
         │                       │
         ▼                       ▼
    Perception              Decision Making
    (Observations)          (BDI Engine)
         │                       │
         │                       │
         ├───────────┬───────────┤
         │           │           │
         ▼           ▼           ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ Episodic │ │ Semantic │ │Procedural│
    │  Memory  │ │  Memory  │ │  Memory  │
    └──────────┘ └──────────┘ └──────────┘
         │           │           │
         └───────────┴───────────┘
                     │
                     ▼
              ┌──────────┐
              │ Working  │
              │  Memory  │
              └──────────┘
                     │
                     ▼
               Execution
```

### Memory Flow

**Storage:**
1. **Observations** → Episodic Memory (events, interactions)
2. **Extracted Facts** → Semantic Memory (entities, relationships)
3. **Successful Actions** → Procedural Memory (skills, workflows)
4. **Current Context** → Working Memory (active tasks, scratchpad)

**Retrieval:**
1. **Decision Making** needs context → Query episodic (similar past situations)
2. **Planning** needs facts → Query semantic (relevant knowledge)
3. **Execution** needs procedures → Query procedural (how to do task)
4. **Immediate context** → Read working memory (what's happening now)

---

## Episodic Memory

### Purpose

Store **personal experiences and events**:
- Email conversations
- Meeting interactions
- Phone calls
- Observations of world state changes
- Human feedback

**Key characteristics:**
- Time-ordered (temporal index)
- Context-rich (who, what, where, when)
- Similarity-based retrieval (semantic search via embeddings)
- Importance-weighted (not all memories equally valuable)
- Decay over time (unless reinforced by recall)

### Data Model

See `docs/design/core-models.md` for Pydantic model.

```python
class EpisodicMemory:
    episode_type: EpisodeType     # interaction, event, observation, feedback
    description: str              # Human-readable summary
    content: Dict[str, Any]       # Full episode data (emails, transcripts, etc.)

    # Context
    participants: List[str]       # Who was involved
    location: str                 # Where it happened (email, slack, zoom)

    # Retrieval
    embedding: vector(1024)       # Semantic similarity search (pgvector)
    importance: float             # 0-1 scale
    recall_count: int             # How many times recalled

    # Temporal
    occurred_at: datetime         # When it happened
```

### Storage Algorithm

```python
async def store_episode(
    employee_id: UUID,
    episode_type: EpisodeType,
    content: Dict[str, Any],
    participants: List[str] = [],
    location: Optional[str] = None
) -> EpisodicMemory:
    """
    Store new episodic memory.

    Steps:
    1. Compute importance score
    2. Generate embedding for similarity search
    3. Store in database
    4. Evict low-importance memories if capacity exceeded
    """

    # 1. Compute importance (0-1 scale)
    importance = compute_importance(content, participants)

    # 2. Generate embedding
    description = generate_description(content)
    embedding = await generate_embedding(description)

    # 3. Create memory
    memory = EpisodicMemory(
        employee_id=employee_id,
        tenant_id=get_current_tenant_id(),
        episode_type=episode_type,
        description=description,
        content=content,
        participants=participants,
        location=location,
        embedding=embedding,
        importance=importance,
        occurred_at=datetime.utcnow()
    )

    await db.save(memory)

    # 4. Check capacity and evict if needed
    await check_and_evict_memories(employee_id)

    return memory


def compute_importance(
    content: Dict[str, Any],
    participants: List[str]
) -> float:
    """
    Compute episode importance (0-1 scale).

    Factors:
    - Emotional significance (sentiment analysis)
    - Participant importance (executives > individual contributors)
    - Content novelty (new information > redundant)
    - Explicit feedback (human-marked important)
    """

    importance = 0.5  # Base importance

    # Emotional significance
    if "sentiment" in content:
        sentiment = content["sentiment"]
        if sentiment in ["very_positive", "very_negative"]:
            importance += 0.2

    # Participant importance
    for participant in participants:
        role = get_participant_role(participant)
        if role in ["executive", "decision_maker"]:
            importance += 0.15

    # Explicit feedback
    if content.get("marked_important"):
        importance += 0.3

    # Novelty (check if similar memory exists)
    # TODO: Implement similarity check

    return min(1.0, importance)
```

### Retrieval Algorithm

**Use cases:**
1. **Similarity search**: Find similar past situations
2. **Temporal search**: What happened recently?
3. **Participant search**: All interactions with person X
4. **Type search**: All meetings, all emails, etc.

```python
class EpisodicMemorySystem:
    async def recall_similar(
        self,
        query: str,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[EpisodicMemory]:
        """
        Retrieve memories similar to query.

        Uses pgvector cosine similarity search.

        Example:
            >>> memories = await episodic.recall_similar(
            ...     "Conversations about pricing with Acme Corp",
            ...     limit=5
            ... )
        """

        # Generate query embedding
        query_embedding = await generate_embedding(query)

        # Vector similarity search (pgvector)
        results = await db.execute(
            """
            SELECT *,
                   1 - (embedding <=> $1) AS similarity
            FROM memory_episodes
            WHERE employee_id = $2
              AND deleted_at IS NULL
              AND 1 - (embedding <=> $1) >= $3
            ORDER BY similarity DESC
            LIMIT $4
            """,
            query_embedding,
            self.employee_id,
            similarity_threshold,
            limit
        )

        memories = [EpisodicMemory.model_validate(r) for r in results]

        # Update recall counts (for reinforcement)
        for memory in memories:
            memory.recall_count += 1
            memory.last_recalled_at = datetime.utcnow()
            await db.save(memory)

        return memories


    async def recall_recent(
        self,
        days: int = 7,
        limit: int = 50
    ) -> List[EpisodicMemory]:
        """Retrieve recent memories."""

        cutoff = datetime.utcnow() - timedelta(days=days)

        results = await db.query(
            EpisodicMemory,
            EpisodicMemory.employee_id == self.employee_id,
            EpisodicMemory.occurred_at >= cutoff,
            EpisodicMemory.deleted_at == None
        ).order_by(EpisodicMemory.occurred_at.desc()).limit(limit).all()

        return results


    async def recall_with_participant(
        self,
        participant: str,
        limit: int = 20
    ) -> List[EpisodicMemory]:
        """Retrieve all memories involving participant."""

        results = await db.execute(
            """
            SELECT *
            FROM memory_episodes
            WHERE employee_id = $1
              AND $2 = ANY(participants)
              AND deleted_at IS NULL
            ORDER BY occurred_at DESC
            LIMIT $3
            """,
            self.employee_id,
            participant,
            limit
        )

        return [EpisodicMemory.model_validate(r) for r in results]


    async def recall_by_type(
        self,
        episode_type: EpisodeType,
        limit: int = 20
    ) -> List[EpisodicMemory]:
        """Retrieve memories of specific type."""

        results = await db.query(
            EpisodicMemory,
            EpisodicMemory.employee_id == self.employee_id,
            EpisodicMemory.episode_type == episode_type,
            EpisodicMemory.deleted_at == None
        ).order_by(EpisodicMemory.occurred_at.desc()).limit(limit).all()

        return results
```

### Memory Consolidation

**Consolidation**: Merge redundant memories, reinforce important ones.

```python
async def consolidate_episodic_memories(employee_id: UUID) -> None:
    """
    Consolidate episodic memories (run periodically, e.g., daily).

    Steps:
    1. Find similar memories (potential duplicates)
    2. Merge duplicates
    3. Reinforce frequently-recalled memories
    4. Decay rarely-recalled memories
    5. Archive very old low-importance memories
    """

    # 1. Find recent memories
    recent_memories = await recall_recent(employee_id, days=30)

    # 2. Detect similar memories (potential duplicates)
    duplicates = []
    for i, memory1 in enumerate(recent_memories):
        for memory2 in recent_memories[i+1:]:
            similarity = cosine_similarity(memory1.embedding, memory2.embedding)
            if similarity > 0.95:  # Very similar
                duplicates.append((memory1, memory2))

    # 3. Merge duplicates
    for mem1, mem2 in duplicates:
        merged = merge_memories(mem1, mem2)
        await db.save(merged)
        await db.delete(mem2)  # Soft delete

    # 4. Reinforce frequently-recalled memories
    for memory in recent_memories:
        if memory.recall_count > 5:
            # Boost importance
            memory.importance = min(1.0, memory.importance * 1.1)
            await db.save(memory)

    # 5. Decay rarely-recalled memories
    old_memories = await recall_recent(employee_id, days=90)
    for memory in old_memories:
        if memory.recall_count == 0:
            # Reduce importance
            memory.importance *= 0.9
            await db.save(memory)

    # 6. Archive very old low-importance memories
    very_old = await db.query(
        EpisodicMemory,
        EpisodicMemory.employee_id == employee_id,
        EpisodicMemory.occurred_at < datetime.utcnow() - timedelta(days=365),
        EpisodicMemory.importance < 0.3
    ).all()

    for memory in very_old:
        await archive_memory(memory)
```

---

## Semantic Memory

### Purpose

Store **facts and knowledge** about the world:
- Entity facts ("Acme Corp is an enterprise customer")
- Relationships ("Acme Corp uses Salesforce")
- Rules ("Enterprise deals require legal review")
- Definitions ("Churn risk defined as NPS < 50")

**Key characteristics:**
- Graph-structured (Subject-Predicate-Object triples)
- Query-based retrieval (SQL, full-text search)
- Confidence-weighted (facts have confidence scores)
- Human-verifiable (facts can be verified by humans)

### Data Model

```python
class SemanticMemory:
    fact_type: FactType          # entity, relationship, rule, definition

    # SPO triple
    subject: str                 # "Acme Corp"
    predicate: str               # "is_a"
    object: str                  # "enterprise_customer"

    # Confidence
    confidence: float            # 0-1 scale
    source: str                  # Where fact came from
    verified: bool               # Human-verified?

    # Retrieval
    embedding: vector(1024)      # Semantic similarity search
```

### Storage Algorithm

```python
async def store_fact(
    employee_id: UUID,
    subject: str,
    predicate: str,
    object: str,
    fact_type: FactType,
    confidence: float = 1.0,
    source: Optional[str] = None
) -> SemanticMemory:
    """
    Store semantic fact.

    Example:
        >>> fact = await semantic.store_fact(
        ...     subject="Acme Corp",
        ...     predicate="is_a",
        ...     object="enterprise_customer",
        ...     fact_type=FactType.ENTITY
        ... )
    """

    # Check if fact already exists
    existing = await db.query(
        SemanticMemory,
        SemanticMemory.employee_id == employee_id,
        SemanticMemory.subject == subject,
        SemanticMemory.predicate == predicate,
        SemanticMemory.deleted_at == None
    ).first()

    if existing:
        # Update confidence if new fact is more confident
        if confidence > existing.confidence:
            existing.confidence = confidence
            existing.object = object
            existing.source = source
            await db.save(existing)
        return existing

    # Generate embedding
    fact_text = f"{subject} {predicate} {object}"
    embedding = await generate_embedding(fact_text)

    # Create new fact
    fact = SemanticMemory(
        employee_id=employee_id,
        tenant_id=get_current_tenant_id(),
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object=object,
        confidence=confidence,
        source=source,
        embedding=embedding
    )

    await db.save(fact)

    return fact
```

### Fact Extraction from Episodes

```python
async def extract_facts_from_episode(
    episode: EpisodicMemory
) -> List[SemanticMemory]:
    """
    Extract semantic facts from episodic memory.

    Uses LLM to extract structured facts from unstructured content.

    Example:
        Email: "Acme Corp is interested in our Enterprise plan"
        Facts:
        - (Acme Corp, is_interested_in, Enterprise plan)
        - (Acme Corp, is_a, potential_customer)
    """

    # Use LLM to extract facts
    prompt = f"""
    Extract factual statements from this interaction:

    {episode.description}

    Content:
    {json.dumps(episode.content, indent=2)}

    Return facts in the format:
    - Subject | Predicate | Object | Confidence

    Example:
    - Acme Corp | is_a | enterprise_customer | 0.9
    - Acme Corp | uses | Salesforce | 0.8
    """

    response = await llm.complete(prompt)

    # Parse response and create facts
    facts = []
    for line in response.split("\n"):
        if line.startswith("-"):
            parts = [p.strip() for p in line[1:].split("|")]
            if len(parts) == 4:
                subject, predicate, object_val, confidence = parts

                fact = await store_fact(
                    employee_id=episode.employee_id,
                    subject=subject,
                    predicate=predicate,
                    object=object_val,
                    fact_type=infer_fact_type(predicate),
                    confidence=float(confidence),
                    source=f"episode_{episode.id}"
                )
                facts.append(fact)

    return facts
```

### Retrieval Algorithm

```python
class SemanticMemorySystem:
    async def query_facts(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        fact_type: Optional[FactType] = None,
        min_confidence: float = 0.5
    ) -> List[SemanticMemory]:
        """
        Query facts with filters.

        Example:
            >>> facts = await semantic.query_facts(
            ...     subject="Acme Corp",
            ...     min_confidence=0.7
            ... )
        """

        query = db.query(SemanticMemory).filter(
            SemanticMemory.employee_id == self.employee_id,
            SemanticMemory.confidence >= min_confidence,
            SemanticMemory.deleted_at == None
        )

        if subject:
            query = query.filter(SemanticMemory.subject == subject)
        if predicate:
            query = query.filter(SemanticMemory.predicate == predicate)
        if object:
            query = query.filter(SemanticMemory.object == object)
        if fact_type:
            query = query.filter(SemanticMemory.fact_type == fact_type)

        return await query.all()


    async def find_related(
        self,
        subject: str,
        max_depth: int = 2
    ) -> Dict[str, List[SemanticMemory]]:
        """
        Find all facts related to subject (graph traversal).

        Example:
            >>> related = await semantic.find_related("Acme Corp", max_depth=2)
            >>> # Returns:
            >>> # {
            >>> #   "Acme Corp": [(Acme Corp, is_a, enterprise_customer), ...],
            >>> #   "John Smith": [(John Smith, works_at, Acme Corp), ...],
            >>> # }
        """

        visited = set()
        results = defaultdict(list)

        async def traverse(current_subject: str, depth: int):
            if depth > max_depth or current_subject in visited:
                return

            visited.add(current_subject)

            # Get facts about current subject
            facts = await self.query_facts(subject=current_subject)
            results[current_subject].extend(facts)

            # Traverse to related subjects (object of current facts)
            for fact in facts:
                if fact.object not in visited:
                    await traverse(fact.object, depth + 1)

        await traverse(subject, 0)

        return dict(results)


    async def search_semantic(
        self,
        query: str,
        limit: int = 10
    ) -> List[SemanticMemory]:
        """
        Semantic search using embeddings.

        Example:
            >>> facts = await semantic.search_semantic(
            ...     "What do I know about Acme Corp's tech stack?"
            ... )
        """

        query_embedding = await generate_embedding(query)

        results = await db.execute(
            """
            SELECT *,
                   1 - (embedding <=> $1) AS similarity
            FROM memory_semantic
            WHERE employee_id = $2
              AND deleted_at IS NULL
            ORDER BY similarity DESC
            LIMIT $3
            """,
            query_embedding,
            self.employee_id,
            limit
        )

        return [SemanticMemory.model_validate(r) for r in results]
```

---

## Procedural Memory

### Purpose

Store **skills and procedures** - how to do things:
- Skills (low-level actions: send_email, create_task)
- Workflows (multi-step procedures: qualification_call, deal_handoff)
- Heuristics (decision rules: when_to_follow_up, how_to_prioritize)

**Key characteristics:**
- Condition-action structure (when to use, what to do)
- Success-rate learning (improve from outcomes)
- Source tracking (learned vs pre-built)

### Data Model

```python
class ProceduralMemory:
    procedure_name: str          # Unique identifier
    description: str             # Human-readable
    procedure_type: ProcedureType  # skill, workflow, heuristic

    # Procedure content
    steps: Dict[str, Any]        # Structured steps
    conditions: Dict[str, Any]   # When to use this procedure

    # Learning
    success_rate: float          # 0-1 scale (learned from outcomes)
    execution_count: int         # How many times executed

    # Source
    learned_from: LearnedFrom    # human_demonstration, trial_and_error, instruction, pre_built
```

### Storage Algorithm

```python
async def store_procedure(
    employee_id: UUID,
    procedure_name: str,
    description: str,
    procedure_type: ProcedureType,
    steps: Dict[str, Any],
    conditions: Dict[str, Any] = {},
    learned_from: LearnedFrom = LearnedFrom.PRE_BUILT
) -> ProceduralMemory:
    """
    Store procedural knowledge.

    Example:
        >>> procedure = await procedural.store_procedure(
        ...     procedure_name="send_follow_up_email",
        ...     description="Send personalized follow-up after meeting",
        ...     procedure_type=ProcedureType.SKILL,
        ...     steps={
        ...         "steps": [
        ...             {"step": 1, "action": "retrieve_meeting_notes"},
        ...             {"step": 2, "action": "draft_email"},
        ...             {"step": 3, "action": "send_email"}
        ...         ]
        ...     }
        ... )
    """

    # Check if procedure already exists
    existing = await db.query(
        ProceduralMemory,
        ProceduralMemory.employee_id == employee_id,
        ProceduralMemory.procedure_name == procedure_name,
        ProceduralMemory.deleted_at == None
    ).first()

    if existing:
        # Update existing
        existing.steps = steps
        existing.conditions = conditions
        await db.save(existing)
        return existing

    # Create new
    procedure = ProceduralMemory(
        employee_id=employee_id,
        tenant_id=get_current_tenant_id(),
        procedure_name=procedure_name,
        description=description,
        procedure_type=procedure_type,
        steps=steps,
        conditions=conditions,
        learned_from=learned_from,
        success_rate=0.5  # Neutral initial success rate
    )

    await db.save(procedure)

    return procedure
```

### Learning from Outcomes

```python
async def update_procedure_from_outcome(
    procedure_id: UUID,
    success: bool
) -> None:
    """
    Update procedure success rate based on execution outcome.

    Uses exponential moving average for smooth learning.
    """

    procedure = await db.get(ProceduralMemory, procedure_id)

    # Update execution count
    procedure.execution_count += 1

    # Update success rate (exponential moving average)
    alpha = 0.1  # Learning rate
    outcome_value = 1.0 if success else 0.0
    procedure.success_rate = (
        (1 - alpha) * procedure.success_rate +
        alpha * outcome_value
    )

    procedure.last_executed_at = datetime.utcnow()

    await db.save(procedure)
```

### Retrieval Algorithm

```python
class ProceduralMemorySystem:
    async def retrieve_procedures(
        self,
        procedure_type: Optional[ProcedureType] = None,
        context: Optional[Dict[str, Any]] = None,
        min_success_rate: float = 0.5
    ) -> List[ProceduralMemory]:
        """
        Retrieve procedures matching criteria.

        Example:
            >>> procedures = await procedural.retrieve_procedures(
            ...     procedure_type=ProcedureType.WORKFLOW,
            ...     context={"goal_type": "build_pipeline"},
            ...     min_success_rate=0.7
            ... )
        """

        query = db.query(ProceduralMemory).filter(
            ProceduralMemory.employee_id == self.employee_id,
            ProceduralMemory.success_rate >= min_success_rate,
            ProceduralMemory.deleted_at == None
        )

        if procedure_type:
            query = query.filter(ProceduralMemory.procedure_type == procedure_type)

        procedures = await query.all()

        # Filter by context match (if provided)
        if context:
            matched = []
            for proc in procedures:
                if self._context_matches(proc.conditions, context):
                    matched.append(proc)
            procedures = matched

        # Sort by success rate (best first)
        procedures.sort(key=lambda p: p.success_rate, reverse=True)

        return procedures


    def _context_matches(
        self,
        conditions: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """
        Check if context matches procedure conditions.

        Example conditions:
        {
            "triggers": ["discovery_call_scheduled"],
            "context": {"deal_size": "> 10000"}
        }
        """

        # Check triggers
        if "triggers" in conditions:
            required_triggers = set(conditions["triggers"])
            context_triggers = set(context.get("triggers", []))
            if not required_triggers.intersection(context_triggers):
                return False

        # Check context constraints
        if "context" in conditions:
            for key, constraint in conditions["context"].items():
                if key not in context:
                    return False
                # Simple constraint evaluation (can be extended)
                context_value = context[key]
                if not self._evaluate_constraint(context_value, constraint):
                    return False

        return True


    def _evaluate_constraint(self, value: Any, constraint: str) -> bool:
        """Evaluate simple constraints like '> 10000', '== true', etc."""
        # TODO: Implement constraint evaluation logic
        return True
```

### Learning from Observation (Shadow Mode)

```python
async def learn_procedure_from_human(
    employee_id: UUID,
    observation: EpisodicMemory
) -> Optional[ProceduralMemory]:
    """
    Learn procedure by observing human.

    Used during shadow mode: employee observes human mentor.

    Example:
        Human does: retrieve notes → draft email → send email
        Employee learns: "send_follow_up_email" workflow
    """

    # Use LLM to extract procedure from observation
    prompt = f"""
    Extract a reusable procedure from this human action:

    {observation.description}

    Content:
    {json.dumps(observation.content, indent=2)}

    Return:
    - Procedure name
    - Description
    - Type (skill/workflow/heuristic)
    - Steps (structured)
    - Conditions (when to use)
    """

    response = await llm.complete(prompt)

    # Parse response and create procedure
    # TODO: Implement parsing logic

    procedure = await store_procedure(
        employee_id=employee_id,
        procedure_name=parsed["name"],
        description=parsed["description"],
        procedure_type=parsed["type"],
        steps=parsed["steps"],
        conditions=parsed["conditions"],
        learned_from=LearnedFrom.HUMAN_DEMONSTRATION
    )

    return procedure
```

---

## Working Memory

### Purpose

Store **current context** - what the employee is thinking about right now:
- Current task (what I'm doing)
- Active conversation (what we're discussing)
- Scratchpad (temporary notes)
- Recent observations (just noticed)

**Key characteristics:**
- Short-lived (expires after use or timeout)
- Limited capacity (priority-based eviction)
- High-speed access (cached in memory)

### Data Model

```python
class WorkingMemory:
    context_type: ContextType    # current_task, conversation, scratchpad, recent_observation
    content: Dict[str, Any]      # Context data

    # Lifecycle
    priority: int                # 1-10 scale (affects eviction)
    expires_at: datetime         # Auto-evict when expired
```

### Storage Algorithm

```python
class WorkingMemorySystem:
    def __init__(self, employee_id: UUID, capacity: int = 20):
        self.employee_id = employee_id
        self.capacity = capacity
        self._cache: Dict[str, WorkingMemory] = {}  # In-memory cache


    async def store_context(
        self,
        context_type: ContextType,
        content: Dict[str, Any],
        priority: int = 5,
        ttl_seconds: Optional[int] = None
    ) -> WorkingMemory:
        """
        Store working memory context.

        Example:
            >>> await working.store_context(
            ...     context_type=ContextType.CURRENT_TASK,
            ...     content={"task": "compose_email", "progress": "drafting"},
            ...     priority=8,
            ...     ttl_seconds=3600  # 1 hour
            ... )
        """

        expires_at = None
        if ttl_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        context = WorkingMemory(
            employee_id=self.employee_id,
            tenant_id=get_current_tenant_id(),
            context_type=context_type,
            content=content,
            priority=priority,
            expires_at=expires_at
        )

        # Save to database
        await db.save(context)

        # Cache in memory
        cache_key = f"{context_type}_{context.id}"
        self._cache[cache_key] = context

        # Check capacity and evict if needed
        await self._evict_if_needed()

        return context


    async def _evict_if_needed(self) -> None:
        """
        Evict lowest-priority contexts if capacity exceeded.

        Capacity management ensures working memory doesn't grow unbounded.
        """

        contexts = await db.query(
            WorkingMemory,
            WorkingMemory.employee_id == self.employee_id,
            WorkingMemory.deleted_at == None
        ).all()

        if len(contexts) <= self.capacity:
            return

        # Sort by priority (lowest first)
        contexts.sort(key=lambda c: c.priority)

        # Evict lowest priority contexts
        num_to_evict = len(contexts) - self.capacity
        for context in contexts[:num_to_evict]:
            await self._evict_context(context)


    async def _evict_context(self, context: WorkingMemory) -> None:
        """Evict context from working memory."""

        # Soft delete
        context.deleted_at = datetime.utcnow()
        await db.save(context)

        # Remove from cache
        cache_key = f"{context.context_type}_{context.id}"
        self._cache.pop(cache_key, None)
```

### Retrieval Algorithm

```python
class WorkingMemorySystem:
    async def get_context(
        self,
        context_type: ContextType
    ) -> List[WorkingMemory]:
        """
        Retrieve contexts by type.

        Example:
            >>> contexts = await working.get_context(
            ...     context_type=ContextType.CURRENT_TASK
            ... )
        """

        # Check cache first
        cached = [
            ctx for ctx in self._cache.values()
            if ctx.context_type == context_type and not ctx.is_expired()
        ]

        if cached:
            return cached

        # Query database
        contexts = await db.query(
            WorkingMemory,
            WorkingMemory.employee_id == self.employee_id,
            WorkingMemory.context_type == context_type,
            WorkingMemory.deleted_at == None
        ).filter(
            # Not expired
            or_(
                WorkingMemory.expires_at == None,
                WorkingMemory.expires_at > datetime.utcnow()
            )
        ).order_by(WorkingMemory.priority.desc()).all()

        # Update cache
        for ctx in contexts:
            cache_key = f"{ctx.context_type}_{ctx.id}"
            self._cache[cache_key] = ctx

        return contexts


    async def clear_context(self, context_type: ContextType) -> None:
        """
        Clear all contexts of type.

        Example:
            >>> await working.clear_context(ContextType.SCRATCHPAD)
        """

        contexts = await self.get_context(context_type)

        for context in contexts:
            await self._evict_context(context)


    async def expire_old_contexts(self) -> None:
        """
        Expire contexts past their TTL.

        Called periodically by proactive loop.
        """

        expired = await db.query(
            WorkingMemory,
            WorkingMemory.employee_id == self.employee_id,
            WorkingMemory.expires_at <= datetime.utcnow(),
            WorkingMemory.deleted_at == None
        ).all()

        for context in expired:
            await self._evict_context(context)
```

---

## Memory Integration

### How Memories Work Together

```python
class MemorySystem:
    """
    Unified interface to all memory types.

    Coordinates between episodic, semantic, procedural, working memory.
    """

    def __init__(self, employee_id: UUID):
        self.episodic = EpisodicMemorySystem(employee_id)
        self.semantic = SemanticMemorySystem(employee_id)
        self.procedural = ProceduralMemorySystem(employee_id)
        self.working = WorkingMemorySystem(employee_id)


    async def process_observation(
        self,
        observation: Observation
    ) -> None:
        """
        Process new observation across all memory types.

        Flow:
        1. Store in episodic (the raw experience)
        2. Extract facts → semantic (knowledge extraction)
        3. Store in working (current context)
        4. Learn procedures (if applicable)
        """

        # 1. Store episodic memory
        episode = await self.episodic.store_episode(
            episode_type=observation.episode_type,
            content=observation.content,
            participants=observation.participants,
            location=observation.location
        )

        # 2. Extract semantic facts
        facts = await extract_facts_from_episode(episode)
        for fact in facts:
            await self.semantic.store_fact(
                subject=fact.subject,
                predicate=fact.predicate,
                object=fact.object,
                fact_type=fact.fact_type,
                confidence=fact.confidence,
                source=f"episode_{episode.id}"
            )

        # 3. Store in working memory (if relevant to current task)
        if observation.is_relevant_to_current_task():
            await self.working.store_context(
                context_type=ContextType.RECENT_OBSERVATION,
                content=observation.content,
                priority=7,
                ttl_seconds=3600  # Keep for 1 hour
            )

        # 4. Learn procedure (if in shadow mode)
        if self.employee.lifecycle_stage == EmployeeLifecycleStage.SHADOW:
            procedure = await learn_procedure_from_human(
                employee_id=self.employee.id,
                observation=episode
            )


    async def recall_for_decision(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Retrieve relevant memories for decision-making.

        Returns:
        {
            "episodic": [...],  # Similar past situations
            "semantic": [...],  # Relevant facts
            "procedural": [...],  # Applicable procedures
            "working": [...]  # Current context
        }
        """

        # Build query from context
        query = f"{context.get('goal', '')} {context.get('situation', '')}"

        # Retrieve from each memory type
        return {
            "episodic": await self.episodic.recall_similar(query, limit=5),
            "semantic": await self.semantic.search_semantic(query, limit=10),
            "procedural": await self.procedural.retrieve_procedures(
                context=context,
                min_success_rate=0.6
            ),
            "working": await self.working.get_context(ContextType.CURRENT_TASK)
        }
```

---

## Performance Optimization

### Caching Strategy

```python
# In-memory cache for hot memories
from functools import lru_cache

@lru_cache(maxsize=100)
async def get_high_confidence_facts(employee_id: UUID) -> List[SemanticMemory]:
    """Cache frequently-accessed high-confidence facts."""
    return await db.query(
        SemanticMemory,
        SemanticMemory.employee_id == employee_id,
        SemanticMemory.confidence >= 0.9,
        SemanticMemory.deleted_at == None
    ).all()
```

### Batch Operations

```python
async def batch_store_episodes(episodes: List[Dict[str, Any]]) -> List[EpisodicMemory]:
    """Batch insert episodes (reduce DB round-trips)."""

    memories = [
        EpisodicMemory(**episode)
        for episode in episodes
    ]

    await db.bulk_save(memories)

    return memories
```

### Embedding Generation

```python
# Batch embedding generation (more efficient)
async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings in batch (20-50x faster than sequential)."""

    response = await anthropic_client.embeddings.create(
        model="voyage-3",
        input=texts
    )

    return [emb.embedding for emb in response.data]
```

---

## Testing Strategy

### Unit Tests

```python
async def test_episodic_storage():
    """Test storing episodic memory."""
    memory = await episodic.store_episode(
        episode_type=EpisodeType.INTERACTION,
        content={"from": "test@example.com", "body": "Test message"},
        participants=["test@example.com"]
    )

    assert memory.id is not None
    assert memory.episode_type == EpisodeType.INTERACTION


async def test_semantic_fact_extraction():
    """Test extracting facts from episode."""
    episode = EpisodicMemory(
        description="Acme Corp is interested in Enterprise plan",
        content={"email_body": "We'd like to upgrade to Enterprise"}
    )

    facts = await extract_facts_from_episode(episode)

    assert len(facts) > 0
    assert any(f.subject == "Acme Corp" for f in facts)


async def test_procedural_learning():
    """Test learning from successful execution."""
    procedure = await procedural.store_procedure(
        procedure_name="test_procedure",
        description="Test",
        procedure_type=ProcedureType.SKILL,
        steps={"steps": [{"action": "test"}]}
    )

    initial_success_rate = procedure.success_rate

    # Update from successful execution
    await update_procedure_from_outcome(procedure.id, success=True)

    updated = await db.get(ProceduralMemory, procedure.id)
    assert updated.success_rate > initial_success_rate


async def test_working_memory_eviction():
    """Test working memory capacity management."""
    working = WorkingMemorySystem(employee_id=uuid4(), capacity=5)

    # Store 10 contexts (exceeds capacity)
    for i in range(10):
        await working.store_context(
            context_type=ContextType.SCRATCHPAD,
            content={"note": f"Note {i}"},
            priority=i  # Varying priorities
        )

    # Check only 5 remain (highest priority)
    contexts = await working.get_context(ContextType.SCRATCHPAD)
    assert len(contexts) == 5
    assert all(c.priority >= 5 for c in contexts)
```

---

## Observability

### Metrics

```python
# Memory system metrics
metrics.gauge("memory.episodic.count", len(episodic_memories))
metrics.gauge("memory.semantic.count", len(semantic_facts))
metrics.gauge("memory.procedural.count", len(procedures))
metrics.gauge("memory.working.count", len(working_contexts))

# Performance metrics
metrics.histogram("memory.episodic.recall_duration", timer.elapsed())
metrics.histogram("memory.semantic.query_duration", timer.elapsed())
metrics.histogram("memory.embedding.generation_duration", timer.elapsed())

# Quality metrics
metrics.histogram("memory.episodic.importance", [m.importance for m in memories])
metrics.histogram("memory.semantic.confidence", [f.confidence for f in facts])
metrics.histogram("memory.procedural.success_rate", [p.success_rate for p in procedures])
```

---

## Open Questions

1. **Embedding model**: Anthropic voyage-3 vs OpenAI text-embedding-3-large? (Current: TBD based on quality/cost)
2. **Memory capacity**: Hard limits per employee? (Current: soft limits with importance-based eviction)
3. **Consolidation frequency**: Daily vs weekly? (Current: daily for episodic, weekly for semantic)
4. **Fact verification**: Automatic vs human-in-the-loop? (Current: human-verifiable flag, auto-verification Phase 3+)

---

## Next Steps

1. **Implement EpisodicMemorySystem** (empla/core/memory/episodic.py)
2. **Implement SemanticMemorySystem** (empla/core/memory/semantic.py)
3. **Implement ProceduralMemorySystem** (empla/core/memory/procedural.py)
4. **Implement WorkingMemorySystem** (empla/core/memory/working.py)
5. **Implement MemorySystem coordinator** (empla/core/memory/__init__.py)
6. **Write comprehensive unit tests** (>80% coverage)
7. **Integrate with BDI engine and proactive loop**

---

**References:**
- docs/design/database-schema.md - Database schema
- docs/design/core-models.md - Pydantic models
- docs/design/bdi-engine.md - BDI implementation
- ARCHITECTURE.md - System architecture

**Academic References:**
- Tulving (1972): "Episodic and Semantic Memory"
- Anderson (1982): "Procedural Memory: Knowledge and Practice"
- Baddeley (1992): "Working Memory"
- Atkinson & Shiffrin (1968): "Multi-Store Memory Model"

---

## Implementation Notes

> **Added:** 2025-10-30 (After implementation and testing)

### Critical Implementation Learnings

**1. JSONB Serialization (PostgreSQL)**

**Issue:** Python's `str()` function creates invalid JSON for PostgreSQL JSONB columns.

```python
# ❌ WRONG - Creates invalid JSON like "{'key': 'value'}"
query.params(conditions=str(trigger_conditions))

# ✅ CORRECT - Creates valid JSON like '{"key": "value"}'
import json
query.params(conditions=json.dumps(trigger_conditions))
```

**Why:** PostgreSQL JSONB expects valid JSON format with double quotes. Python's `str()` uses single quotes for dict representation, which is invalid JSON.

**Affected areas:**
- ProceduralMemory: JSONB `@>` containment operator queries
- Any SQLAlchemy text() queries with JSONB parameters

**Solution:** Always use `json.dumps()` for JSONB query parameters.

**2. SemanticMemory Object Field**

**Issue:** Model expects `object` field as string, but structured data (dicts) are sometimes needed.

```python
# Original signature (string only)
async def store_fact(subject: str, predicate: str, object: str, ...)

# Updated signature (string or dict)
async def store_fact(subject: str, predicate: str, object: str | dict[str, Any], ...)
```

**Implementation:**
```python
# Convert dict objects to JSON strings before storing
object_str = json.dumps(object) if isinstance(object, dict) else object

fact = SemanticMemory(
    subject=subject,
    predicate=predicate,
    object=object_str,  # Always stored as string
    ...
)
```

**Why:** Allows storing structured facts like `{"employees": 500, "revenue": "50M"}` while maintaining string column type for simple queries.

**3. ProceduralMemory Steps Field**

**Issue:** JSONB column can store lists directly - no need to wrap in dict.

```python
# ❌ WRONG - Unnecessary wrapping
steps={"steps": [{"action": "step1"}, {"action": "step2"}]}

# ✅ CORRECT - Store list directly in JSONB
steps=[{"action": "step1"}, {"action": "step2"}]
```

**Why:** PostgreSQL JSONB natively supports arrays. Wrapping in dict adds complexity and breaks test assertions like `len(procedure.steps)`.

**Column definition:** `steps: Mapped[dict[str, Any]]` accepts any JSON value (object, array, etc.)

**4. Floating-Point Precision in Tests**

**Issue:** Float arithmetic causes test assertion failures.

```python
# ❌ FAILS - 0.7 + 0.1 = 0.7999999999999999
item.importance = item.importance + importance_boost
assert item.importance == 0.8  # Fails!

# ✅ PASSES - Round to avoid precision issues
item.importance = round(min(1.0, item.importance + importance_boost), 10)
assert item.importance == 0.8  # Passes
```

**Affected:** WorkingMemory.refresh_item() importance calculations

**Solution:** Round float values to reasonable precision (10 decimal places) before storing.

### Test Coverage Results

**Final Status (2025-10-30):**
- Memory integration tests: 17/17 passing (100%)
- Overall coverage: 49.40%

**Test breakdown:**
- Episodic Memory: 3/3 tests ✅
- Semantic Memory: 4/4 tests ✅
- Procedural Memory: 4/4 tests ✅
- Working Memory: 5/5 tests ✅
- Integration: 1/1 test ✅

### Future Improvements

**From CodeRabbit Review (2025-10-30):**

1. **Session flush consistency:** Add `await session.flush()` to all mutation methods (currently inconsistent across BDI components)

2. **Type hints for nullable relationships:** Update nullable ForeignKey relationships to use `Mapped[Type | None]` for proper type checking

3. **Dependency checking:** Enhance `check_dependencies_met()` to verify all dependency IDs exist and none are soft-deleted

4. **datetime deprecation:** Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` throughout codebase

5. **ForeignKey ondelete policies:** Add explicit `ondelete` behavior to all ForeignKey constraints in migrations

### Performance Notes

**Memory usage:**
- Working memory limited to ~20 contexts per employee (configurable)
- Episodic memory grows unbounded (managed by importance-based archival)
- Semantic memory grows unbounded (managed by confidence-based archival)
- Procedural memory typically <100 procedures per employee

**Query performance:**
- Vector similarity searches: ~50-100ms for 10k memories (with IVFFlat index)
- JSONB containment queries: ~10-20ms (with GIN indexes)
- Standard lookups: <5ms (with B-tree indexes)

**Embedding generation:**
- Batch operations recommended: 20-50x faster than sequential
- Deferred generation acceptable: memories can be created without embeddings initially
