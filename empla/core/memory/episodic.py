"""
empla.core.memory.episodic - Episodic Memory System

Episodic Memory stores personal experiences and events:
- Email conversations
- Meeting interactions
- Observations of world state changes
- Human feedback

Key characteristics:
- Time-ordered (temporal index)
- Context-rich (who, what, where, when)
- Similarity-based retrieval (semantic search via embeddings)
- Importance-weighted (not all memories equally valuable)
- Decay over time (unless reinforced by recall)
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.memory import EpisodicMemory


class EpisodicMemorySystem:
    """
    Episodic Memory System - Personal experiences and events.

    Manages an employee's experiential memory - every interaction,
    event, and observation is stored with full context and can be
    recalled via similarity search.

    Example:
        >>> episodic = EpisodicMemorySystem(session, employee_id, tenant_id)
        >>> memory = await episodic.record_episode(
        ...     episode_type="interaction",
        ...     description="Discussed pricing with Acme Corp CEO",
        ...     content={"email_thread": [...], "key_points": [...]},
        ...     participants=["ceo@acmecorp.com"]
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """
        Initialize EpisodicMemorySystem.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this memory belongs to
            tenant_id: Tenant ID for multi-tenancy
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id

    async def record_episode(
        self,
        episode_type: str,
        description: str,
        content: dict[str, Any],
        participants: list[str] | None = None,
        location: str | None = None,
        importance: float = 0.5,
        embedding: list[float] | None = None,
    ) -> EpisodicMemory:
        """
        Record a new episodic memory.

        Args:
            episode_type: Type of episode (interaction, event, observation, feedback)
            description: Human-readable summary
            content: Full episode data (emails, transcripts, etc.)
            participants: Who was involved (email addresses or identifiers)
            location: Where it happened (email, slack, zoom, phone, etc.)
            importance: Importance score (0-1 scale)
            embedding: Pre-computed embedding (if None, needs to be generated separately)

        Returns:
            Created EpisodicMemory

        Example:
            >>> memory = await episodic.record_episode(
            ...     episode_type="interaction",
            ...     description="Pricing discussion with Acme Corp",
            ...     content={
            ...         "email_from": "ceo@acmecorp.com",
            ...         "email_body": "Interested in Enterprise plan...",
            ...         "key_points": ["pricing", "enterprise", "timeline"]
            ...     },
            ...     participants=["ceo@acmecorp.com"],
            ...     location="email",
            ...     importance=0.8
            ... )
        """
        # Note: Embedding generation is deferred to a separate service/function
        # This keeps the memory system focused on storage/retrieval
        # The proactive loop or calling code should handle embedding generation

        memory = EpisodicMemory(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            episode_type=episode_type,
            description=description,
            content=content,
            participants=participants or [],
            location=location,
            embedding=embedding,  # Can be None initially, set later
            importance=importance,
            occurred_at=datetime.now(UTC),
        )

        self.session.add(memory)
        await self.session.flush()

        return memory

    async def recall_similar(
        self,
        query_embedding: list[float],
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[EpisodicMemory]:
        """
        Retrieve memories similar to query embedding.

        Uses pgvector cosine similarity search to find memories
        semantically similar to the query.

        Args:
            query_embedding: Vector embedding of query
            limit: Maximum number of memories to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of similar EpisodicMemories, sorted by similarity (highest first)

        Example:
            >>> # First, generate embedding for your query
            >>> query_embedding = await generate_embedding(
            ...     "Conversations about pricing with Acme Corp"
            ... )
            >>> # Then search for similar memories
            >>> memories = await episodic.recall_similar(
            ...     query_embedding=query_embedding,
            ...     limit=5,
            ...     similarity_threshold=0.75
            ... )
        """
        # pgvector similarity search using cosine distance (<=>)
        # 1 - (embedding <=> query_embedding) = similarity score (0-1)
        result = await self.session.execute(
            select(EpisodicMemory)
            .where(
                EpisodicMemory.employee_id == self.employee_id,
                EpisodicMemory.tenant_id == self.tenant_id,
                EpisodicMemory.deleted_at.is_(None),
                EpisodicMemory.embedding.is_not(None),  # Only memories with embeddings
                # Similarity threshold check
                text("1 - (embedding <=> :query_emb) >= :threshold"),
            )
            .params(
                query_emb=str(query_embedding),  # pgvector expects string representation
                threshold=similarity_threshold,
            )
            .order_by(text("embedding <=> :query_emb"))  # Order by distance (closest first)
            .limit(limit)
        )

        memories = list(result.scalars().all())

        # Update recall counts (for memory reinforcement)
        now = datetime.now(UTC)
        for memory in memories:
            memory.recall_count += 1
            memory.last_recalled_at = now

        await self.session.flush()

        return memories

    async def recall_recent(
        self,
        days: int = 7,
        limit: int = 50,
        episode_type: str | None = None,
    ) -> list[EpisodicMemory]:
        """
        Retrieve recent memories.

        Args:
            days: How many days back to search
            limit: Maximum number of memories
            episode_type: Optional filter by episode type

        Returns:
            List of recent memories, ordered by occurrence (newest first)

        Example:
            >>> recent = await episodic.recall_recent(
            ...     days=7,
            ...     episode_type="interaction"
            ... )
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        query = select(EpisodicMemory).where(
            EpisodicMemory.employee_id == self.employee_id,
            EpisodicMemory.tenant_id == self.tenant_id,
            EpisodicMemory.occurred_at >= cutoff,
            EpisodicMemory.deleted_at.is_(None),
        )

        if episode_type:
            query = query.where(EpisodicMemory.episode_type == episode_type)

        result = await self.session.execute(
            query.order_by(EpisodicMemory.occurred_at.desc()).limit(limit)
        )

        return list(result.scalars().all())

    async def recall_with_participant(
        self,
        participant: str,
        limit: int = 20,
    ) -> list[EpisodicMemory]:
        """
        Retrieve all memories involving a participant.

        Args:
            participant: Email or identifier of participant
            limit: Maximum number of memories

        Returns:
            List of memories involving participant, ordered by time (newest first)

        Example:
            >>> memories = await episodic.recall_with_participant(
            ...     participant="ceo@acmecorp.com",
            ...     limit=10
            ... )
        """
        # PostgreSQL array contains operator (ANY)
        result = await self.session.execute(
            select(EpisodicMemory)
            .where(
                EpisodicMemory.employee_id == self.employee_id,
                EpisodicMemory.tenant_id == self.tenant_id,
                EpisodicMemory.deleted_at.is_(None),
                # Check if participant is in the participants array
                text(":participant = ANY(participants)"),
            )
            .params(participant=participant)
            .order_by(EpisodicMemory.occurred_at.desc())
            .limit(limit)
        )

        return list(result.scalars().all())

    async def recall_by_type(
        self,
        episode_type: str,
        limit: int = 20,
    ) -> list[EpisodicMemory]:
        """
        Retrieve memories of specific type.

        Args:
            episode_type: Type of episode (interaction, event, observation, feedback)
            limit: Maximum number of memories

        Returns:
            List of memories of specified type, ordered by time (newest first)

        Example:
            >>> meetings = await episodic.recall_by_type(
            ...     episode_type="event",
            ...     limit=20
            ... )
        """
        result = await self.session.execute(
            select(EpisodicMemory)
            .where(
                EpisodicMemory.employee_id == self.employee_id,
                EpisodicMemory.tenant_id == self.tenant_id,
                EpisodicMemory.episode_type == episode_type,
                EpisodicMemory.deleted_at.is_(None),
            )
            .order_by(EpisodicMemory.occurred_at.desc())
            .limit(limit)
        )

        return list(result.scalars().all())

    async def get_memory(self, memory_id: UUID) -> EpisodicMemory | None:
        """
        Get a specific memory by ID.

        Args:
            memory_id: Memory UUID

        Returns:
            EpisodicMemory if found, None otherwise
        """
        result = await self.session.execute(
            select(EpisodicMemory).where(
                EpisodicMemory.id == memory_id,
                EpisodicMemory.employee_id == self.employee_id,
                EpisodicMemory.tenant_id == self.tenant_id,
                EpisodicMemory.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_importance(
        self,
        memory_id: UUID,
        new_importance: float,
    ) -> EpisodicMemory | None:
        """
        Update memory importance score.

        Args:
            memory_id: Memory UUID
            new_importance: New importance score (0-1)

        Returns:
            Updated EpisodicMemory, or None if not found
        """
        memory = await self.get_memory(memory_id)

        if not memory:
            return None

        memory.importance = max(0.0, min(1.0, new_importance))  # Clamp to [0, 1]
        memory.updated_at = datetime.now(UTC)

        await self.session.flush()
        return memory

    async def consolidate_memories(
        self,
        days_back: int = 30,
        similarity_threshold: float = 0.95,
    ) -> int:
        """
        Consolidate episodic memories by merging similar ones.

        This helps manage memory growth by combining redundant memories.
        Should be run periodically (e.g., daily).

        Args:
            days_back: How many days of recent memories to consolidate
            similarity_threshold: How similar memories must be to merge (0-1)

        Returns:
            Number of memories consolidated

        Note:
            Current implementation marks duplicates for deletion.
            A more sophisticated version could merge content.
        """
        # Get recent memories for consolidation
        recent = await self.recall_recent(days=days_back, limit=1000)

        consolidated_count = 0

        # Simple deduplication: if memories are very similar, keep highest importance
        # In production, could use more sophisticated merging
        seen = set()

        for memory in recent:
            if memory.id in seen:
                continue

            # Find very similar memories (would need embedding comparison)
            # For now, this is a placeholder for the consolidation logic
            # Full implementation would use vector similarity

            # Mark as seen
            seen.add(memory.id)

        return consolidated_count

    async def reinforce_frequently_recalled(
        self,
        min_recall_count: int = 5,
        importance_boost: float = 1.1,
    ) -> int:
        """
        Reinforce frequently-recalled memories by boosting importance.

        Memories that are recalled often are likely important and should
        be prioritized for retention.

        Args:
            min_recall_count: Minimum recalls to qualify for reinforcement
            importance_boost: Multiplier for importance (default 1.1 = +10%)

        Returns:
            Number of memories reinforced
        """
        result = await self.session.execute(
            select(EpisodicMemory).where(
                EpisodicMemory.employee_id == self.employee_id,
                EpisodicMemory.tenant_id == self.tenant_id,
                EpisodicMemory.recall_count >= min_recall_count,
                EpisodicMemory.deleted_at.is_(None),
            )
        )

        memories = list(result.scalars().all())
        count = 0

        for memory in memories:
            # Boost importance but cap at 1.0
            memory.importance = min(1.0, memory.importance * importance_boost)
            count += 1

        await self.session.flush()
        return count

    async def decay_rarely_recalled(
        self,
        min_days_old: int = 90,
        importance_decay: float = 0.9,
    ) -> int:
        """
        Decay rarely-recalled old memories by reducing importance.

        Memories that are old and never recalled are likely less important.

        Args:
            min_days_old: Minimum age in days to qualify for decay
            importance_decay: Multiplier for importance (default 0.9 = -10%)

        Returns:
            Number of memories decayed
        """
        cutoff = datetime.now(UTC) - timedelta(days=min_days_old)

        result = await self.session.execute(
            select(EpisodicMemory).where(
                EpisodicMemory.employee_id == self.employee_id,
                EpisodicMemory.tenant_id == self.tenant_id,
                EpisodicMemory.occurred_at < cutoff,
                EpisodicMemory.recall_count == 0,
                EpisodicMemory.deleted_at.is_(None),
            )
        )

        memories = list(result.scalars().all())
        count = 0

        for memory in memories:
            memory.importance *= importance_decay
            count += 1

        await self.session.flush()
        return count

    async def archive_low_importance(
        self,
        min_days_old: int = 365,
        max_importance: float = 0.3,
    ) -> int:
        """
        Archive (soft delete) very old low-importance memories.

        Prevents the memory system from growing indefinitely while
        preserving important historical memories.

        Args:
            min_days_old: Minimum age in days to qualify for archival
            max_importance: Maximum importance to qualify for archival

        Returns:
            Number of memories archived
        """
        cutoff = datetime.now(UTC) - timedelta(days=min_days_old)
        now = datetime.now(UTC)

        result = await self.session.execute(
            select(EpisodicMemory).where(
                EpisodicMemory.employee_id == self.employee_id,
                EpisodicMemory.tenant_id == self.tenant_id,
                EpisodicMemory.occurred_at < cutoff,
                EpisodicMemory.importance < max_importance,
                EpisodicMemory.deleted_at.is_(None),
            )
        )

        memories = list(result.scalars().all())
        count = 0

        for memory in memories:
            memory.deleted_at = now
            count += 1

        await self.session.flush()
        return count
