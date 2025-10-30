"""
empla.core.memory.semantic - Semantic Memory System

Semantic Memory stores general knowledge and facts:
- Facts about people, companies, products (SPO triples)
- Domain knowledge (sales processes, industry info)
- Extracted knowledge from episodic memories
- Relationships between entities

Key characteristics:
- Graph-structured (entities and relationships)
- Context-independent (facts remain true across time)
- Query-based retrieval (SPARQL-like queries)
- Similarity-based search (semantic embeddings)
- Confidence-weighted (facts have certainty scores)
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.memory import SemanticMemory


class SemanticMemorySystem:
    """
    Semantic Memory System - General knowledge and facts.

    Manages an employee's semantic knowledge - facts, relationships,
    and domain knowledge stored as Subject-Predicate-Object triples
    with embeddings for similarity search.

    Example:
        >>> semantic = SemanticMemorySystem(session, employee_id, tenant_id)
        >>> fact = await semantic.store_fact(
        ...     subject="Acme Corp",
        ...     predicate="industry",
        ...     object="manufacturing",
        ...     confidence=0.95,
        ...     source_type="observation",
        ...     source_id=episodic_memory_id
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ):
        """
        Initialize SemanticMemorySystem.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this knowledge belongs to
            tenant_id: Tenant ID for multi-tenancy
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id

    async def store_fact(
        self,
        subject: str,
        predicate: str,
        object: str | dict[str, Any],
        confidence: float = 0.8,
        fact_type: str = "entity",
        source: str | None = None,
        verified: bool = False,
        source_type: str | None = None,
        source_id: UUID | None = None,
        context: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> SemanticMemory:
        """
        Store a new fact (SPO triple).

        Args:
            subject: Subject entity (e.g., "Acme Corp", "John Smith")
            predicate: Relationship/property (e.g., "industry", "role", "prefers")
            object: Object value (string or structured dict)
            confidence: Confidence in this fact (0-1 scale)
            source_type: Where this fact came from (observation, extraction, inference, user_input)
            source_id: UUID of source (episodic memory, belief, etc.)
            context: Additional context for this fact
            embedding: Pre-computed embedding (if None, needs generation)

        Returns:
            Created SemanticMemory

        Example:
            >>> # Simple fact
            >>> fact = await semantic.store_fact(
            ...     subject="Acme Corp",
            ...     predicate="industry",
            ...     object="manufacturing",
            ...     confidence=0.95
            ... )
            >>>
            >>> # Structured fact
            >>> fact = await semantic.store_fact(
            ...     subject="John Smith",
            ...     predicate="contact_preferences",
            ...     object={
            ...         "preferred_time": "mornings",
            ...         "preferred_channel": "email",
            ...         "timezone": "EST"
            ...     },
            ...     confidence=0.85,
            ...     source_type="extraction",
            ...     source_id=episodic_memory_id
            ... )
        """
        # Convert dict objects to JSON strings for storage
        object_str = json.dumps(object) if isinstance(object, dict) else object

        # Check if fact already exists (same subject+predicate)
        existing = await self.get_fact(subject, predicate)

        if existing:
            # Update existing fact
            existing.object = object_str
            existing.confidence = confidence
            existing.access_count += 1
            existing.last_accessed_at = datetime.now(UTC)
            existing.updated_at = datetime.now(UTC)

            if source_type:
                existing.source_type = source_type
            if source_id:
                existing.source_id = source_id
            if context:
                existing.context = context
            if embedding:
                existing.embedding = embedding

            await self.session.flush()
            return existing

        # Create new fact
        fact = SemanticMemory(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            fact_type=fact_type,
            subject=subject,
            predicate=predicate,
            object=object_str,
            confidence=confidence,
            source=source,
            verified=verified,
            source_type=source_type,
            source_id=source_id,
            context=context or {},
            embedding=embedding,
        )

        self.session.add(fact)
        await self.session.flush()

        return fact

    async def get_fact(
        self,
        subject: str,
        predicate: str,
    ) -> SemanticMemory | None:
        """
        Get a specific fact by subject and predicate.

        Args:
            subject: Subject entity
            predicate: Relationship/property

        Returns:
            SemanticMemory if found, None otherwise

        Example:
            >>> fact = await semantic.get_fact("Acme Corp", "industry")
            >>> if fact:
            ...     print(f"{fact.subject} {fact.predicate} {fact.object}")
        """
        result = await self.session.execute(
            select(SemanticMemory).where(
                SemanticMemory.employee_id == self.employee_id,
                SemanticMemory.tenant_id == self.tenant_id,
                SemanticMemory.subject == subject,
                SemanticMemory.predicate == predicate,
                SemanticMemory.deleted_at.is_(None),
            )
        )
        fact = result.scalar_one_or_none()

        if fact:
            # Update access tracking
            fact.access_count += 1
            fact.last_accessed_at = datetime.now(UTC)
            await self.session.flush()

        return fact

    async def query_facts(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        limit: int = 50,
    ) -> list[SemanticMemory]:
        """
        Query facts by subject and/or predicate.

        Args:
            subject: Filter by subject (None = all subjects)
            predicate: Filter by predicate (None = all predicates)
            limit: Maximum number of facts to return

        Returns:
            List of matching SemanticMemories, ordered by confidence

        Example:
            >>> # Get all facts about Acme Corp
            >>> facts = await semantic.query_facts(subject="Acme Corp")
            >>>
            >>> # Get all "industry" facts
            >>> facts = await semantic.query_facts(predicate="industry")
            >>>
            >>> # Get specific fact
            >>> facts = await semantic.query_facts(
            ...     subject="Acme Corp",
            ...     predicate="industry"
            ... )
        """
        query = select(SemanticMemory).where(
            SemanticMemory.employee_id == self.employee_id,
            SemanticMemory.tenant_id == self.tenant_id,
            SemanticMemory.deleted_at.is_(None),
        )

        if subject:
            query = query.where(SemanticMemory.subject == subject)

        if predicate:
            query = query.where(SemanticMemory.predicate == predicate)

        result = await self.session.execute(
            query.order_by(SemanticMemory.confidence.desc()).limit(limit)
        )

        facts = list(result.scalars().all())

        # Update access tracking
        now = datetime.now(UTC)
        for fact in facts:
            fact.access_count += 1
            fact.last_accessed_at = now

        await self.session.flush()

        return facts

    async def search_similar_facts(
        self,
        query_embedding: list[float],
        limit: int = 10,
        similarity_threshold: float = 0.7,
        subject: str | None = None,
        predicate: str | None = None,
    ) -> list[SemanticMemory]:
        """
        Search for facts similar to query embedding.

        Uses pgvector cosine similarity search to find semantically
        similar facts. Can optionally filter by subject/predicate.

        Args:
            query_embedding: Vector embedding of query
            limit: Maximum number of facts to return
            similarity_threshold: Minimum similarity score (0-1)
            subject: Optional subject filter
            predicate: Optional predicate filter

        Returns:
            List of similar SemanticMemories, sorted by similarity

        Example:
            >>> # Generate embedding for question
            >>> query_emb = await generate_embedding(
            ...     "What industries do my prospects work in?"
            ... )
            >>> # Search for relevant facts
            >>> facts = await semantic.search_similar_facts(
            ...     query_embedding=query_emb,
            ...     predicate="industry",
            ...     limit=10
            ... )
        """
        # Build query with similarity search
        query = select(SemanticMemory).where(
            SemanticMemory.employee_id == self.employee_id,
            SemanticMemory.tenant_id == self.tenant_id,
            SemanticMemory.deleted_at.is_(None),
            SemanticMemory.embedding.is_not(None),
            text("1 - (embedding <=> :query_emb) >= :threshold"),
        )

        # Apply optional filters
        if subject:
            query = query.where(SemanticMemory.subject == subject)

        if predicate:
            query = query.where(SemanticMemory.predicate == predicate)

        result = await self.session.execute(
            query.params(
                query_emb=str(query_embedding),
                threshold=similarity_threshold,
            )
            .order_by(text("embedding <=> :query_emb"))
            .limit(limit)
        )

        facts = list(result.scalars().all())

        # Update access tracking
        now = datetime.now(UTC)
        for fact in facts:
            fact.access_count += 1
            fact.last_accessed_at = now

        await self.session.flush()

        return facts

    async def get_related_facts(
        self,
        entity: str,
        max_depth: int = 2,
        limit_per_level: int = 20,
    ) -> dict[str, list[SemanticMemory]]:
        """
        Get facts related to an entity through graph traversal.

        Performs breadth-first traversal of the knowledge graph starting
        from the given entity. Returns facts organized by depth level.

        Args:
            entity: Starting entity (subject)
            max_depth: Maximum traversal depth (1 = direct facts only)
            limit_per_level: Max facts per depth level

        Returns:
            Dictionary mapping depth level to list of facts
            Example: {
                "0": [facts about entity],
                "1": [facts about entities mentioned in depth-0 facts],
                "2": [facts about entities mentioned in depth-1 facts]
            }

        Example:
            >>> # Get all facts related to Acme Corp (2 levels deep)
            >>> related = await semantic.get_related_facts(
            ...     entity="Acme Corp",
            ...     max_depth=2,
            ...     limit_per_level=10
            ... )
            >>> # related["0"] = direct facts about Acme Corp
            >>> # related["1"] = facts about CEO, industry, etc.
            >>> # related["2"] = facts about entities in level 1
        """
        result: dict[str, list[SemanticMemory]] = {}
        visited_entities = {entity}
        current_level = [entity]

        for depth in range(max_depth + 1):
            depth_facts: list[SemanticMemory] = []

            # Get facts for all entities at this level
            for subject_entity in current_level:
                facts = await self.query_facts(
                    subject=subject_entity,
                    limit=limit_per_level,
                )
                depth_facts.extend(facts)

            result[str(depth)] = depth_facts

            # Extract new entities for next level (from object values)
            if depth < max_depth:
                next_level = set()
                for fact in depth_facts:
                    # If object is a string and looks like an entity, add it
                    if isinstance(fact.object, str) and len(fact.object) > 0:
                        # Only add if not visited yet
                        if fact.object not in visited_entities:
                            next_level.add(fact.object)
                            visited_entities.add(fact.object)

                current_level = list(next_level)

                # Stop if no new entities found
                if not current_level:
                    break

        return result

    async def update_fact_confidence(
        self,
        subject: str,
        predicate: str,
        new_confidence: float,
    ) -> SemanticMemory | None:
        """
        Update confidence score for a fact.

        Args:
            subject: Subject entity
            predicate: Relationship/property
            new_confidence: New confidence score (0-1)

        Returns:
            Updated SemanticMemory, or None if not found

        Example:
            >>> # Reduce confidence in outdated fact
            >>> fact = await semantic.update_fact_confidence(
            ...     subject="Acme Corp",
            ...     predicate="deal_stage",
            ...     new_confidence=0.5
            ... )
        """
        fact = await self.get_fact(subject, predicate)

        if not fact:
            return None

        fact.confidence = max(0.0, min(1.0, new_confidence))  # Clamp to [0, 1]
        fact.updated_at = datetime.now(UTC)

        await self.session.flush()
        return fact

    async def decay_old_facts(
        self,
        min_days_old: int = 180,
        confidence_decay: float = 0.9,
    ) -> int:
        """
        Decay confidence of old facts that haven't been accessed.

        Facts that are old and rarely accessed likely become less relevant.
        This helps manage knowledge freshness.

        Args:
            min_days_old: Minimum age in days to qualify for decay
            confidence_decay: Multiplier for confidence (default 0.9 = -10%)

        Returns:
            Number of facts decayed

        Example:
            >>> # Decay facts older than 6 months
            >>> count = await semantic.decay_old_facts(
            ...     min_days_old=180,
            ...     confidence_decay=0.85
            ... )
        """
        cutoff = datetime.now(UTC) - timedelta(days=min_days_old)

        result = await self.session.execute(
            select(SemanticMemory).where(
                SemanticMemory.employee_id == self.employee_id,
                SemanticMemory.tenant_id == self.tenant_id,
                SemanticMemory.created_at < cutoff,
                SemanticMemory.access_count < 5,  # Rarely accessed
                SemanticMemory.deleted_at.is_(None),
            )
        )

        facts = list(result.scalars().all())
        count = 0

        for fact in facts:
            fact.confidence *= confidence_decay
            count += 1

        await self.session.flush()
        return count

    async def archive_low_confidence_facts(
        self,
        max_confidence: float = 0.3,
        min_days_old: int = 90,
    ) -> int:
        """
        Archive (soft delete) low-confidence old facts.

        Prevents the knowledge base from growing with uncertain information.

        Args:
            max_confidence: Maximum confidence to qualify for archival
            min_days_old: Minimum age in days to qualify for archival

        Returns:
            Number of facts archived

        Example:
            >>> # Archive low-confidence facts older than 3 months
            >>> count = await semantic.archive_low_confidence_facts(
            ...     max_confidence=0.3,
            ...     min_days_old=90
            ... )
        """
        cutoff = datetime.now(UTC) - timedelta(days=min_days_old)
        now = datetime.now(UTC)

        result = await self.session.execute(
            select(SemanticMemory).where(
                SemanticMemory.employee_id == self.employee_id,
                SemanticMemory.tenant_id == self.tenant_id,
                SemanticMemory.confidence < max_confidence,
                SemanticMemory.created_at < cutoff,
                SemanticMemory.deleted_at.is_(None),
            )
        )

        facts = list(result.scalars().all())
        count = 0

        for fact in facts:
            fact.deleted_at = now
            count += 1

        await self.session.flush()
        return count

    async def reinforce_frequently_accessed(
        self,
        min_access_count: int = 10,
        confidence_boost: float = 1.1,
    ) -> int:
        """
        Reinforce frequently-accessed facts by boosting confidence.

        Facts that are accessed often are likely important and accurate.

        Args:
            min_access_count: Minimum accesses to qualify for reinforcement
            confidence_boost: Multiplier for confidence (default 1.1 = +10%)

        Returns:
            Number of facts reinforced

        Example:
            >>> # Boost confidence of frequently used facts
            >>> count = await semantic.reinforce_frequently_accessed(
            ...     min_access_count=10,
            ...     confidence_boost=1.15
            ... )
        """
        result = await self.session.execute(
            select(SemanticMemory).where(
                SemanticMemory.employee_id == self.employee_id,
                SemanticMemory.tenant_id == self.tenant_id,
                SemanticMemory.access_count >= min_access_count,
                SemanticMemory.deleted_at.is_(None),
            )
        )

        facts = list(result.scalars().all())
        count = 0

        for fact in facts:
            # Boost confidence but cap at 1.0
            fact.confidence = min(1.0, fact.confidence * confidence_boost)
            count += 1

        await self.session.flush()
        return count

    async def get_entity_summary(
        self,
        entity: str,
    ) -> dict[str, Any]:
        """
        Get a summary of all knowledge about an entity.

        Args:
            entity: Entity to summarize (subject)

        Returns:
            Dictionary with entity facts organized by predicate

        Example:
            >>> summary = await semantic.get_entity_summary("Acme Corp")
            >>> # Returns:
            >>> # {
            >>> #     "industry": "manufacturing",
            >>> #     "size": {"employees": 500, "revenue": "50M"},
            >>> #     "location": "San Francisco",
            >>> #     ...
            >>> # }
        """
        facts = await self.query_facts(subject=entity, limit=100)

        summary: dict[str, Any] = {}
        for fact in facts:
            summary[fact.predicate] = fact.object

        return summary
