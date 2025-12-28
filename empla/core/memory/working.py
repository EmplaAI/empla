"""
empla.core.memory.working - Working Memory System

Working Memory stores current context and active information:
- Current tasks and goals being pursued
- Recent observations
- Active conversations
- Temporary context needed for decision-making
- Short-term attention focus

Key characteristics:
- Limited capacity (like human working memory ~7 items)
- Temporary (cleared when context switches)
- Highly accessible (fast retrieval)
- Context-specific (tied to current goals/tasks)
- Attention-weighted (important items retained longer)

Design: Unlike other memory types which persist to database,
working memory is primarily in-memory with optional persistence
for continuity across employee restarts.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.memory import WorkingMemory as WorkingMemoryModel


class WorkingMemory:
    """
    Working Memory - Current context and active information.

    Manages the employee's current "attention span" - what they're
    actively thinking about and working on right now. This has
    limited capacity and items decay quickly when not refreshed.

    Design rationale:
    - In-memory cache for fast access
    - Database persistence for crash recovery
    - Automatic capacity management (evicts least important items)
    - Decay mechanism (items fade without reinforcement)

    Example:
        >>> working = WorkingMemory(session, employee_id, tenant_id)
        >>> # Add current task to working memory
        >>> await working.add_item(
        ...     item_type="task",
        ...     content={"task": "Research Acme Corp", "deadline": "2024-10-30"},
        ...     importance=0.9,
        ...     ttl_seconds=3600  # Keep for 1 hour
        ... )
        >>> # Retrieve active items
        >>> items = await working.get_active_items()
    """

    # Working memory capacity (inspired by Miller's Law: 7±2 items)
    DEFAULT_CAPACITY = 7
    DEFAULT_TTL_SECONDS = 3600  # 1 hour default time-to-live

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
        capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        """
        Initialize WorkingMemory.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this working memory belongs to
            tenant_id: Tenant ID for multi-tenancy
            capacity: Maximum number of items (default 7)
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id
        self.capacity = capacity

    async def add_item(
        self,
        item_type: str,
        content: dict[str, Any],
        importance: float = 0.5,
        ttl_seconds: int | None = None,
        source_id: UUID | None = None,
        source_type: str | None = None,
    ) -> WorkingMemoryModel:
        """
        Add an item to working memory.

        If working memory is at capacity, evicts the least important item
        before adding the new one.

        Args:
            item_type: Type of item (task, goal, observation, conversation, context)
            content: Item data
            importance: Importance score (0-1 scale)
            ttl_seconds: Time-to-live in seconds (None = use default)
            source_id: Source memory UUID (episodic, semantic, etc.)
            source_type: Source memory type

        Returns:
            Created WorkingMemoryModel

        Example:
            >>> # Add current goal to working memory
            >>> item = await working.add_item(
            ...     item_type="goal",
            ...     content={"goal": "Close 10 deals this quarter", "progress": 3},
            ...     importance=0.95,
            ...     ttl_seconds=86400  # Keep for 24 hours
            ... )
        """
        # Check capacity and evict if necessary
        await self._enforce_capacity()

        # Calculate expiration
        ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        expires_at = datetime.now(UTC).timestamp() + ttl

        # Create item
        item = WorkingMemoryModel(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            item_type=item_type,
            content=content,
            importance=importance,
            access_count=1,
            last_accessed_at=datetime.now(UTC),
            expires_at=expires_at,
            source_id=source_id,
            source_type=source_type,
        )

        self.session.add(item)
        await self.session.flush()

        return item

    async def get_active_items(
        self,
        item_type: str | None = None,
    ) -> list[WorkingMemoryModel]:
        """
        Get all active (non-expired) items in working memory.

        Args:
            item_type: Optional filter by item type

        Returns:
            List of active items, sorted by importance (highest first)

        Example:
            >>> # Get all active tasks
            >>> tasks = await working.get_active_items(item_type="task")
        """
        now = datetime.now(UTC).timestamp()

        query = select(WorkingMemoryModel).where(
            WorkingMemoryModel.employee_id == self.employee_id,
            WorkingMemoryModel.tenant_id == self.tenant_id,
            WorkingMemoryModel.expires_at > now,
            WorkingMemoryModel.deleted_at.is_(None),
        )

        if item_type:
            query = query.where(WorkingMemoryModel.item_type == item_type)

        result = await self.session.execute(query.order_by(WorkingMemoryModel.importance.desc()))

        items = list(result.scalars().all())

        # Update access tracking
        access_time = datetime.now(UTC)
        for item in items:
            item.access_count += 1
            item.last_accessed_at = access_time

        await self.session.flush()

        return items

    async def get_item(self, item_id: UUID) -> WorkingMemoryModel | None:
        """
        Get a specific working memory item by ID.

        Args:
            item_id: Item UUID

        Returns:
            WorkingMemoryModel if found and active, None otherwise
        """
        now = datetime.now(UTC).timestamp()

        result = await self.session.execute(
            select(WorkingMemoryModel).where(
                WorkingMemoryModel.id == item_id,
                WorkingMemoryModel.employee_id == self.employee_id,
                WorkingMemoryModel.tenant_id == self.tenant_id,
                WorkingMemoryModel.expires_at > now,
                WorkingMemoryModel.deleted_at.is_(None),
            )
        )

        item = result.scalar_one_or_none()

        if item:
            # Update access tracking
            item.access_count += 1
            item.last_accessed_at = datetime.now(UTC)
            await self.session.flush()

        return item

    async def refresh_item(
        self,
        item_id: UUID,
        ttl_seconds: int | None = None,
        importance_boost: float | None = None,
    ) -> WorkingMemoryModel | None:
        """
        Refresh an item's expiration and optionally boost importance.

        This simulates "rehearsal" in human working memory - actively
        thinking about something keeps it in memory longer.

        Args:
            item_id: Item UUID
            ttl_seconds: New time-to-live (None = use default)
            importance_boost: Amount to increase importance (None = no change)

        Returns:
            Updated WorkingMemoryModel, or None if not found

        Example:
            >>> # Keep current task active
            >>> await working.refresh_item(
            ...     item_id=task_id,
            ...     ttl_seconds=3600,
            ...     importance_boost=0.1  # Increase importance by 0.1
            ... )
        """
        item = await self.get_item(item_id)

        if not item:
            return None

        # Extend expiration
        ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        item.expires_at = datetime.now(UTC).timestamp() + ttl

        # Optionally boost importance
        if importance_boost is not None:
            item.importance = round(min(1.0, item.importance + importance_boost), 10)

        item.updated_at = datetime.now(UTC)

        await self.session.flush()
        return item

    async def remove_item(self, item_id: UUID) -> bool:
        """
        Remove an item from working memory.

        Args:
            item_id: Item UUID

        Returns:
            True if removed, False if not found

        Example:
            >>> # Task completed, remove from working memory
            >>> await working.remove_item(task_id)
        """
        item = await self.get_item(item_id)

        if not item:
            return False

        item.deleted_at = datetime.now(UTC)
        await self.session.flush()

        return True

    async def clear_by_type(self, item_type: str) -> int:
        """
        Clear all items of a specific type.

        Args:
            item_type: Type to clear

        Returns:
            Number of items cleared

        Example:
            >>> # Clear all observations (switching context)
            >>> count = await working.clear_by_type("observation")
        """
        items = await self.get_active_items(item_type=item_type)

        now = datetime.now(UTC)
        for item in items:
            item.deleted_at = now

        await self.session.flush()
        return len(items)

    async def clear_all(self) -> int:
        """
        Clear all items from working memory.

        Args:
            None

        Returns:
            Number of items cleared

        Example:
            >>> # Context switch - clear everything
            >>> count = await working.clear_all()
        """
        items = await self.get_active_items()

        now = datetime.now(UTC)
        for item in items:
            item.deleted_at = now

        await self.session.flush()
        return len(items)

    async def cleanup_expired(self) -> int:
        """
        Remove expired items from working memory.

        This should be called periodically to free up capacity.

        Returns:
            Number of items cleaned up

        Example:
            >>> # Periodic cleanup (e.g., every 5 minutes)
            >>> count = await working.cleanup_expired()
        """
        now_timestamp = datetime.now(UTC).timestamp()
        now_datetime = datetime.now(UTC)

        result = await self.session.execute(
            select(WorkingMemoryModel).where(
                WorkingMemoryModel.employee_id == self.employee_id,
                WorkingMemoryModel.tenant_id == self.tenant_id,
                WorkingMemoryModel.expires_at <= now_timestamp,
                WorkingMemoryModel.deleted_at.is_(None),
            )
        )

        items = list(result.scalars().all())

        for item in items:
            item.deleted_at = now_datetime

        await self.session.flush()
        return len(items)

    async def _enforce_capacity(self) -> None:
        """
        Ensure working memory doesn't exceed capacity.

        If at capacity, evicts the least important non-expired item.
        This is called automatically before adding new items.
        """
        items = await self.get_active_items()

        # Remove any expired items first
        await self.cleanup_expired()

        # Re-fetch after cleanup
        items = await self.get_active_items()

        # If still at or over capacity, evict least important
        if len(items) >= self.capacity:
            # Items are already sorted by importance (descending)
            # Evict the last (least important) item
            least_important = items[-1]
            least_important.deleted_at = datetime.now(UTC)
            await self.session.flush()

    async def get_context_summary(self) -> dict[str, Any]:
        """
        Get a summary of current working memory context.

        Returns a structured summary of what's currently active,
        useful for providing context to decision-making.

        Returns:
            Dictionary with context summary

        Example:
            >>> summary = await working.get_context_summary()
            >>> # Returns:
            >>> # {
            >>> #     "active_goals": [...],
            >>> #     "active_tasks": [...],
            >>> #     "recent_observations": [...],
            >>> #     "active_conversations": [...],
            >>> #     "total_items": 7,
            >>> #     "capacity_used": "7/7"
            >>> # }
        """
        items = await self.get_active_items()

        # Group by type
        by_type: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            item_type = item.item_type
            if item_type not in by_type:
                by_type[item_type] = []

            by_type[item_type].append(
                {
                    "id": str(item.id),
                    "content": item.content,
                    "importance": item.importance,
                    "age_seconds": (datetime.now(UTC) - item.created_at).total_seconds(),
                }
            )

        return {
            **{f"active_{item_type}s": items for item_type, items in by_type.items()},
            "total_items": len(items),
            "capacity_used": f"{len(items)}/{self.capacity}",
            "at_capacity": len(items) >= self.capacity,
        }

    async def update_importance(
        self,
        item_id: UUID,
        new_importance: float,
    ) -> WorkingMemoryModel | None:
        """
        Update importance of a working memory item.

        Args:
            item_id: Item UUID
            new_importance: New importance score (0-1)

        Returns:
            Updated WorkingMemoryModel, or None if not found

        Example:
            >>> # Task became more urgent
            >>> await working.update_importance(task_id, 0.95)
        """
        item = await self.get_item(item_id)

        if not item:
            return None

        item.importance = max(0.0, min(1.0, new_importance))  # Clamp to [0, 1]
        item.updated_at = datetime.now(UTC)

        await self.session.flush()
        return item

    async def get_most_important(
        self,
        limit: int = 3,
    ) -> list[WorkingMemoryModel]:
        """
        Get the most important items in working memory.

        Useful for focus/attention mechanisms - "what should I be
        thinking about right now?"

        Args:
            limit: Number of items to return

        Returns:
            List of most important items

        Example:
            >>> # Get top 3 priorities
            >>> top_items = await working.get_most_important(limit=3)
        """
        items = await self.get_active_items()
        # Already sorted by importance (descending)
        return items[:limit]
