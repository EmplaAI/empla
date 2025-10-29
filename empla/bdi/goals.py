"""
empla.bdi.goals - Goal System

BDI Goal System implementation:
- Manages employee goals (BDI Desires)
- Tracks goal progress
- Handles goal lifecycle (active, in_progress, completed, abandoned, blocked)
- Prioritizes goals based on importance
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.employee import EmployeeGoal


class GoalSystem:
    """
    BDI Goal System (Desires).

    Manages an employee's goals and tracks progress toward achieving them.
    Goals are prioritized and can be in various states of completion.

    Example:
        >>> goal_system = GoalSystem(session, employee_id, tenant_id)
        >>> goal = await goal_system.add_goal(
        ...     goal_type="achievement",
        ...     description="Close 10 deals this quarter",
        ...     priority=8,
        ...     target={"metric": "deals_closed", "value": 10, "timeframe": "Q1"}
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ):
        """
        Initialize GoalSystem.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this goal system belongs to
            tenant_id: Tenant ID for multi-tenancy
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id

    async def add_goal(
        self,
        goal_type: str,
        description: str,
        priority: int,
        target: dict[str, Any],
        current_progress: dict[str, Any] | None = None,
    ) -> EmployeeGoal:
        """
        Add a new goal.

        Args:
            goal_type: Type of goal (achievement, maintenance, prevention)
            description: Human-readable goal description
            priority: Priority (1=lowest, 10=highest)
            target: Goal-specific target metrics (metric, value, timeframe, etc.)
            current_progress: Initial progress tracking (optional)

        Returns:
            Created EmployeeGoal

        Example:
            >>> goal = await goal_system.add_goal(
            ...     goal_type="achievement",
            ...     description="Build pipeline to 3x coverage",
            ...     priority=9,
            ...     target={
            ...         "metric": "pipeline_coverage",
            ...         "current": 2.0,
            ...         "target": 3.0,
            ...         "timeframe": "30_days"
            ...     }
            ... )
        """
        goal = EmployeeGoal(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            goal_type=goal_type,
            description=description,
            priority=priority,
            target=target,
            current_progress=current_progress or {},
            status="active",
        )

        self.session.add(goal)
        await self.session.flush()

        return goal

    async def get_goal(self, goal_id: UUID) -> EmployeeGoal | None:
        """
        Get a specific goal by ID.

        Args:
            goal_id: Goal UUID

        Returns:
            EmployeeGoal if found, None otherwise
        """
        result = await self.session.execute(
            select(EmployeeGoal).where(
                EmployeeGoal.id == goal_id,
                EmployeeGoal.employee_id == self.employee_id,
                EmployeeGoal.tenant_id == self.tenant_id,
                EmployeeGoal.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_goals(
        self,
        min_priority: int = 1,
    ) -> list[EmployeeGoal]:
        """
        Get all active goals.

        Args:
            min_priority: Minimum priority threshold (1-10)

        Returns:
            List of active EmployeeGoals, ordered by priority (highest first)
        """
        result = await self.session.execute(
            select(EmployeeGoal)
            .where(
                EmployeeGoal.employee_id == self.employee_id,
                EmployeeGoal.tenant_id == self.tenant_id,
                EmployeeGoal.status == "active",
                EmployeeGoal.priority >= min_priority,
                EmployeeGoal.deleted_at.is_(None),
            )
            .order_by(EmployeeGoal.priority.desc(), EmployeeGoal.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_goals_by_status(
        self,
        status: str,
    ) -> list[EmployeeGoal]:
        """
        Get goals by status.

        Args:
            status: Goal status (active, in_progress, completed, abandoned, blocked)

        Returns:
            List of EmployeeGoals with the given status
        """
        result = await self.session.execute(
            select(EmployeeGoal)
            .where(
                EmployeeGoal.employee_id == self.employee_id,
                EmployeeGoal.tenant_id == self.tenant_id,
                EmployeeGoal.status == status,
                EmployeeGoal.deleted_at.is_(None),
            )
            .order_by(EmployeeGoal.priority.desc())
        )
        return list(result.scalars().all())

    async def update_goal_progress(
        self,
        goal_id: UUID,
        progress: dict[str, Any],
    ) -> EmployeeGoal | None:
        """
        Update goal progress.

        Args:
            goal_id: Goal UUID
            progress: Progress data to merge with current_progress

        Returns:
            Updated EmployeeGoal, or None if not found

        Example:
            >>> await goal_system.update_goal_progress(
            ...     goal_id=goal.id,
            ...     progress={
            ...         "deals_closed": 3,
            ...         "last_updated": "2025-01-15",
            ...         "velocity": 0.3  # deals per day
            ...     }
            ... )
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return None

        # Merge progress (copy dict to ensure SQLAlchemy detects mutation)
        updated_progress = dict(goal.current_progress or {})
        updated_progress.update(progress)
        goal.current_progress = updated_progress
        goal.updated_at = datetime.now(timezone.utc)

        # Auto-transition to in_progress if still active
        if goal.status == "active":
            goal.status = "in_progress"

        return goal

    async def complete_goal(
        self,
        goal_id: UUID,
        final_progress: dict[str, Any] | None = None,
    ) -> EmployeeGoal | None:
        """
        Mark a goal as completed.

        Args:
            goal_id: Goal UUID
            final_progress: Final progress data (optional)

        Returns:
            Updated EmployeeGoal, or None if not found
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return None

        goal.status = "completed"
        goal.completed_at = datetime.now(timezone.utc)

        if final_progress:
            updated_progress = dict(goal.current_progress or {})
            updated_progress.update(final_progress)
            goal.current_progress = updated_progress

        return goal

    async def abandon_goal(
        self,
        goal_id: UUID,
        reason: str | None = None,
    ) -> EmployeeGoal | None:
        """
        Abandon a goal.

        Args:
            goal_id: Goal UUID
            reason: Reason for abandonment (optional, stored in current_progress)

        Returns:
            Updated EmployeeGoal, or None if not found
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return None

        goal.status = "abandoned"
        goal.abandoned_at = datetime.now(timezone.utc)

        if reason:
            updated_progress = dict(goal.current_progress or {})
            updated_progress["abandonment_reason"] = reason
            goal.current_progress = updated_progress

        return goal

    async def block_goal(
        self,
        goal_id: UUID,
        blocker: str,
    ) -> EmployeeGoal | None:
        """
        Mark a goal as blocked.

        Args:
            goal_id: Goal UUID
            blocker: Description of what's blocking the goal

        Returns:
            Updated EmployeeGoal, or None if not found
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return None

        goal.status = "blocked"
        updated_progress = dict(goal.current_progress or {})
        updated_progress["blocker"] = blocker
        updated_progress["blocked_at"] = datetime.now(timezone.utc).isoformat()
        goal.current_progress = updated_progress

        return goal

    async def unblock_goal(
        self,
        goal_id: UUID,
    ) -> EmployeeGoal | None:
        """
        Unblock a goal (return to active).

        Args:
            goal_id: Goal UUID

        Returns:
            Updated EmployeeGoal, or None if not found
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return None

        if goal.status != "blocked":
            return goal

        goal.status = "active"

        # Remove blocker info (copy dict to ensure SQLAlchemy detects mutation)
        updated_progress = dict(goal.current_progress or {})
        updated_progress.pop("blocker", None)
        updated_progress.pop("blocked_at", None)
        updated_progress["unblocked_at"] = datetime.now(timezone.utc).isoformat()
        goal.current_progress = updated_progress

        return goal

    async def update_goal_priority(
        self,
        goal_id: UUID,
        new_priority: int,
    ) -> EmployeeGoal | None:
        """
        Update goal priority.

        Args:
            goal_id: Goal UUID
            new_priority: New priority (1-10)

        Returns:
            Updated EmployeeGoal, or None if not found
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return None

        goal.priority = new_priority
        goal.updated_at = datetime.now(timezone.utc)

        return goal

    async def get_highest_priority_goal(self) -> EmployeeGoal | None:
        """
        Get the highest priority active goal.

        Returns:
            Highest priority EmployeeGoal, or None if no active goals
        """
        active_goals = await self.get_active_goals()

        if not active_goals:
            return None

        return active_goals[0]  # Already sorted by priority desc

    async def calculate_goal_progress_percentage(
        self,
        goal_id: UUID,
    ) -> float | None:
        """
        Calculate goal progress as percentage (0-100).

        This is a simple heuristic based on comparing current vs target values.
        For more complex goals, override this method.

        Args:
            goal_id: Goal UUID

        Returns:
            Progress percentage (0-100), or None if not calculable
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return None

        # Extract current and target values
        target_value = goal.target.get("value")
        current_value = goal.current_progress.get(goal.target.get("metric"))

        if target_value is None or current_value is None:
            return None

        # Calculate percentage
        if target_value == 0:
            return 100.0 if current_value >= 0 else 0.0

        percentage = (current_value / target_value) * 100.0
        return min(100.0, max(0.0, percentage))

    async def should_focus_on_goal(
        self,
        goal_id: UUID,
        progress_threshold: float = 50.0,
    ) -> bool:
        """
        Determine if employee should focus on this goal.

        Decision factors:
        - Goal is active or in_progress
        - Priority is high (>= 7)
        - Progress is below threshold

        Args:
            goal_id: Goal UUID
            progress_threshold: Progress threshold below which to focus (0-100)

        Returns:
            True if should focus on goal, False otherwise
        """
        goal = await self.get_goal(goal_id)

        if not goal:
            return False

        # Must be active or in_progress
        if goal.status not in ("active", "in_progress"):
            return False

        # High priority goals always need attention
        if goal.priority >= 7:
            return True

        # Check progress
        progress = await self.calculate_goal_progress_percentage(goal_id)

        if progress is None:
            # Can't calculate progress, focus on it
            return True

        return progress < progress_threshold
