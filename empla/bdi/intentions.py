"""
empla.bdi.intentions - Intention Stack

BDI Intention System implementation:
- Manages employee intentions (BDI Intentions/Plans)
- Handles intention execution lifecycle
- Manages intention dependencies
- Prioritizes and schedules intentions
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.employee import EmployeeIntention


class IntentionStack:
    """
    BDI Intention Stack (Plans).

    Manages an employee's intentions - the plans they commit to executing.
    Intentions are prioritized, can have dependencies, and track execution state.

    Example:
        >>> intention_stack = IntentionStack(session, employee_id, tenant_id)
        >>> intention = await intention_stack.add_intention(
        ...     goal_id=goal.id,
        ...     intention_type="action",
        ...     description="Send follow-up email to prospect",
        ...     plan={"type": "send_email", "to": "prospect@company.com", ...},
        ...     priority=8
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ):
        """
        Initialize IntentionStack.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this intention stack belongs to
            tenant_id: Tenant ID for multi-tenancy
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id

    async def add_intention(
        self,
        intention_type: str,
        description: str,
        plan: dict[str, Any],
        priority: int = 5,
        goal_id: UUID | None = None,
        context: dict[str, Any] | None = None,
        dependencies: list[UUID] | None = None,
    ) -> EmployeeIntention:
        """
        Add a new intention to the stack.

        Args:
            intention_type: Type of intention (action, tactic, strategy)
            description: Human-readable intention description
            plan: Structured plan (steps, resources, expected outcomes)
            priority: Priority (1=lowest, 10=highest)
            goal_id: Goal this intention serves (None for opportunistic intentions)
            context: Why this plan was chosen (rationale, alternatives considered)
            dependencies: Other intention UUIDs this depends on

        Returns:
            Created EmployeeIntention

        Example:
            >>> intention = await intention_stack.add_intention(
            ...     intention_type="action",
            ...     description="Research competitors for Acme Corp deal",
            ...     plan={
            ...         "steps": [
            ...             {"action": "search_web", "query": "Acme Corp competitors"},
            ...             {"action": "analyze_results", "max_competitors": 5},
            ...             {"action": "summarize_findings"}
            ...         ],
            ...         "expected_duration": "15_minutes",
            ...         "required_capabilities": ["research", "web_search"]
            ...     },
            ...     priority=7,
            ...     goal_id=goal.id
            ... )
        """
        intention = EmployeeIntention(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            goal_id=goal_id,
            intention_type=intention_type,
            description=description,
            plan=plan,
            status="planned",
            priority=priority,
            context=context or {},
            dependencies=dependencies or [],
        )

        self.session.add(intention)
        await self.session.flush()

        return intention

    async def get_intention(self, intention_id: UUID) -> EmployeeIntention | None:
        """
        Get a specific intention by ID.

        Args:
            intention_id: Intention UUID

        Returns:
            EmployeeIntention if found, None otherwise
        """
        result = await self.session.execute(
            select(EmployeeIntention).where(
                EmployeeIntention.id == intention_id,
                EmployeeIntention.employee_id == self.employee_id,
                EmployeeIntention.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_planned_intentions(
        self,
        min_priority: int = 1,
    ) -> list[EmployeeIntention]:
        """
        Get all planned intentions (ready to execute).

        Args:
            min_priority: Minimum priority threshold (1-10)

        Returns:
            List of planned EmployeeIntentions, ordered by priority (highest first)
        """
        result = await self.session.execute(
            select(EmployeeIntention)
            .where(
                EmployeeIntention.employee_id == self.employee_id,
                EmployeeIntention.status == "planned",
                EmployeeIntention.priority >= min_priority,
                EmployeeIntention.deleted_at.is_(None),
            )
            .order_by(
                EmployeeIntention.priority.desc(), EmployeeIntention.created_at.asc()
            )
        )
        return list(result.scalars().all())

    async def get_intentions_for_goal(
        self,
        goal_id: UUID,
    ) -> list[EmployeeIntention]:
        """
        Get all intentions for a specific goal.

        Args:
            goal_id: Goal UUID

        Returns:
            List of EmployeeIntentions for the goal
        """
        result = await self.session.execute(
            select(EmployeeIntention)
            .where(
                EmployeeIntention.employee_id == self.employee_id,
                EmployeeIntention.goal_id == goal_id,
                EmployeeIntention.deleted_at.is_(None),
            )
            .order_by(EmployeeIntention.priority.desc())
        )
        return list(result.scalars().all())

    async def get_next_intention(self) -> EmployeeIntention | None:
        """
        Get the next intention to execute.

        Selection criteria:
        1. Must be planned (not in_progress, completed, failed, or abandoned)
        2. Dependencies must be satisfied (all dependency intentions completed)
        3. Highest priority wins

        Returns:
            Next EmployeeIntention to execute, or None if none available
        """
        planned = await self.get_planned_intentions()

        for intention in planned:
            # Check if dependencies are satisfied
            if await self._are_dependencies_satisfied(intention):
                return intention

        return None

    async def _are_dependencies_satisfied(
        self,
        intention: EmployeeIntention,
    ) -> bool:
        """
        Check if all dependencies for an intention are satisfied.

        Args:
            intention: Intention to check

        Returns:
            True if all dependencies are completed, False otherwise
        """
        if not intention.dependencies:
            return True

        # Get all dependency intentions
        result = await self.session.execute(
            select(EmployeeIntention).where(
                EmployeeIntention.id.in_(intention.dependencies),
                EmployeeIntention.employee_id == self.employee_id,
            )
        )
        dependencies = list(result.scalars().all())

        # All dependencies must be completed
        return all(dep.status == "completed" for dep in dependencies)

    async def start_intention(
        self,
        intention_id: UUID,
    ) -> EmployeeIntention | None:
        """
        Mark an intention as in_progress.

        Args:
            intention_id: Intention UUID

        Returns:
            Updated EmployeeIntention, or None if not found
        """
        intention = await self.get_intention(intention_id)

        if not intention:
            return None

        if intention.status != "planned":
            # Already started or completed
            return intention

        intention.status = "in_progress"
        intention.started_at = datetime.utcnow()

        return intention

    async def complete_intention(
        self,
        intention_id: UUID,
        outcome: dict[str, Any] | None = None,
    ) -> EmployeeIntention | None:
        """
        Mark an intention as completed.

        Args:
            intention_id: Intention UUID
            outcome: Execution outcome (stored in context)

        Returns:
            Updated EmployeeIntention, or None if not found
        """
        intention = await self.get_intention(intention_id)

        if not intention:
            return None

        intention.status = "completed"
        intention.completed_at = datetime.utcnow()

        if outcome:
            intention.context["outcome"] = outcome

        return intention

    async def fail_intention(
        self,
        intention_id: UUID,
        error: str,
        retry: bool = True,
    ) -> EmployeeIntention | None:
        """
        Mark an intention as failed.

        Args:
            intention_id: Intention UUID
            error: Error description
            retry: Whether to retry this intention

        Returns:
            Updated EmployeeIntention, or None if not found
        """
        intention = await self.get_intention(intention_id)

        if not intention:
            return None

        intention.status = "failed"
        intention.failed_at = datetime.utcnow()
        intention.context["error"] = error
        intention.context["retry"] = retry

        return intention

    async def abandon_intention(
        self,
        intention_id: UUID,
        reason: str,
    ) -> EmployeeIntention | None:
        """
        Abandon an intention.

        Args:
            intention_id: Intention UUID
            reason: Reason for abandonment

        Returns:
            Updated EmployeeIntention, or None if not found
        """
        intention = await self.get_intention(intention_id)

        if not intention:
            return None

        intention.status = "abandoned"
        intention.context["abandonment_reason"] = reason
        intention.context["abandoned_at"] = datetime.utcnow().isoformat()

        return intention

    async def update_intention_priority(
        self,
        intention_id: UUID,
        new_priority: int,
    ) -> EmployeeIntention | None:
        """
        Update intention priority.

        Args:
            intention_id: Intention UUID
            new_priority: New priority (1-10)

        Returns:
            Updated EmployeeIntention, or None if not found
        """
        intention = await self.get_intention(intention_id)

        if not intention:
            return None

        intention.priority = new_priority
        intention.updated_at = datetime.utcnow()

        return intention

    async def get_in_progress_intentions(self) -> list[EmployeeIntention]:
        """
        Get all in-progress intentions.

        Returns:
            List of in-progress EmployeeIntentions
        """
        result = await self.session.execute(
            select(EmployeeIntention)
            .where(
                EmployeeIntention.employee_id == self.employee_id,
                EmployeeIntention.status == "in_progress",
                EmployeeIntention.deleted_at.is_(None),
            )
            .order_by(EmployeeIntention.started_at.asc())
        )
        return list(result.scalars().all())

    async def get_failed_intentions(
        self,
        retryable_only: bool = True,
    ) -> list[EmployeeIntention]:
        """
        Get failed intentions.

        Args:
            retryable_only: Only return intentions marked for retry

        Returns:
            List of failed EmployeeIntentions
        """
        result = await self.session.execute(
            select(EmployeeIntention).where(
                EmployeeIntention.employee_id == self.employee_id,
                EmployeeIntention.status == "failed",
                EmployeeIntention.deleted_at.is_(None),
            )
        )
        intentions = list(result.scalars().all())

        if retryable_only:
            intentions = [
                i for i in intentions if i.context.get("retry", False)
            ]

        return intentions

    async def retry_intention(
        self,
        intention_id: UUID,
    ) -> EmployeeIntention | None:
        """
        Retry a failed intention.

        Args:
            intention_id: Intention UUID

        Returns:
            Updated EmployeeIntention, or None if not found
        """
        intention = await self.get_intention(intention_id)

        if not intention:
            return None

        if intention.status != "failed":
            return intention

        # Reset to planned state
        intention.status = "planned"
        intention.failed_at = None

        # Track retry count
        retry_count = intention.context.get("retry_count", 0)
        intention.context["retry_count"] = retry_count + 1
        intention.context["last_retry_at"] = datetime.utcnow().isoformat()

        return intention

    async def clear_completed_intentions(
        self,
        older_than_days: int = 7,
    ) -> int:
        """
        Clear (soft delete) completed intentions older than N days.

        This prevents the intention stack from growing indefinitely.

        Args:
            older_than_days: Delete intentions completed more than N days ago

        Returns:
            Number of intentions cleared
        """
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)

        result = await self.session.execute(
            select(EmployeeIntention).where(
                EmployeeIntention.employee_id == self.employee_id,
                EmployeeIntention.status == "completed",
                EmployeeIntention.completed_at < cutoff,
                EmployeeIntention.deleted_at.is_(None),
            )
        )
        intentions = list(result.scalars().all())

        for intention in intentions:
            intention.deleted_at = datetime.utcnow()

        return len(intentions)


# Import timedelta for clear_completed_intentions
from datetime import timedelta
