"""
empla.services.activity_service - Activity Recording Service

Service for recording and querying employee activities.
Used by the dashboard activity feed.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.activity import ActivityEventType, EmployeeActivity

logger = logging.getLogger(__name__)


class ActivityService:
    """
    Service for recording and querying employee activities.

    Provides methods to:
    - Record new activities
    - Query activities with filtering and pagination
    - Get activity counts and summaries
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize activity service.

        Args:
            session: Database session for all operations
        """
        self.session = session

    async def record(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        event_type: str,
        description: str,
        data: dict[str, Any] | None = None,
        importance: float = 0.5,
        occurred_at: datetime | None = None,
    ) -> EmployeeActivity:
        """
        Record a new activity.

        Args:
            tenant_id: Tenant ID
            employee_id: Employee who performed the activity
            event_type: Type of event (use ActivityEventType constants)
            description: Human-readable description
            data: Additional structured data
            importance: Importance score (0.0-1.0)
            occurred_at: When the activity occurred (defaults to now)

        Returns:
            Created activity record
        """
        activity = EmployeeActivity(
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type=event_type,
            description=description,
            data=data or {},
            importance=max(0.0, min(1.0, importance)),  # Clamp to 0-1
            occurred_at=occurred_at or datetime.now(UTC),
        )

        self.session.add(activity)
        await self.session.flush()

        logger.debug(
            f"Recorded activity: {event_type} for employee {employee_id}",
            extra={"activity_id": str(activity.id), "event_type": event_type},
        )

        return activity

    async def get_activities(
        self,
        tenant_id: UUID,
        employee_id: UUID | None = None,
        event_types: list[str] | None = None,
        min_importance: float | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EmployeeActivity], int]:
        """
        Query activities with filtering and pagination.

        Args:
            tenant_id: Tenant ID (required for multi-tenant isolation)
            employee_id: Filter by specific employee
            event_types: Filter by event types
            min_importance: Minimum importance score
            since: Activities after this time
            until: Activities before this time
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (activities, total_count)
        """
        # Base query
        query = select(EmployeeActivity).where(EmployeeActivity.tenant_id == tenant_id)

        # Apply filters
        if employee_id:
            query = query.where(EmployeeActivity.employee_id == employee_id)

        if event_types:
            query = query.where(EmployeeActivity.event_type.in_(event_types))

        if min_importance is not None:
            query = query.where(EmployeeActivity.importance >= min_importance)

        if since:
            query = query.where(EmployeeActivity.occurred_at >= since)

        if until:
            query = query.where(EmployeeActivity.occurred_at <= until)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        query = query.order_by(EmployeeActivity.occurred_at.desc()).offset(offset).limit(page_size)

        # Execute
        result = await self.session.execute(query)
        activities = list(result.scalars().all())

        return activities, total

    async def get_recent(
        self,
        tenant_id: UUID,
        employee_id: UUID | None = None,
        limit: int = 20,
    ) -> list[EmployeeActivity]:
        """
        Get recent activities (shortcut for common use case).

        Args:
            tenant_id: Tenant ID
            employee_id: Optional employee filter
            limit: Max number of activities

        Returns:
            List of recent activities
        """
        activities, _ = await self.get_activities(
            tenant_id=tenant_id,
            employee_id=employee_id,
            page=1,
            page_size=limit,
        )
        return activities

    async def get_summary(
        self,
        tenant_id: UUID,
        employee_id: UUID | None = None,
        hours: int = 24,
    ) -> dict[str, int]:
        """
        Get activity summary (counts by event type).

        Args:
            tenant_id: Tenant ID
            employee_id: Optional employee filter
            hours: Time window in hours

        Returns:
            Dictionary of event_type -> count
        """
        since = datetime.now(UTC) - timedelta(hours=hours)

        query = (
            select(
                EmployeeActivity.event_type,
                func.count(EmployeeActivity.id).label("count"),
            )
            .where(
                EmployeeActivity.tenant_id == tenant_id,
                EmployeeActivity.occurred_at >= since,
            )
            .group_by(EmployeeActivity.event_type)
        )

        if employee_id:
            query = query.where(EmployeeActivity.employee_id == employee_id)

        result = await self.session.execute(query)
        rows = result.all()

        return {str(row.event_type): int(row.count) for row in rows}  # type: ignore[call-overload]


# Convenience functions for common activity recording


async def record_email_sent(
    session: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    recipient: str,
    subject: str,
    importance: float = 0.6,
) -> EmployeeActivity:
    """Record an email sent activity."""
    service = ActivityService(session)
    return await service.record(
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type=ActivityEventType.EMAIL_SENT,
        description=f"Sent email to {recipient}: {subject}",
        data={"recipient": recipient, "subject": subject},
        importance=importance,
    )


async def record_goal_progress(
    session: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    goal_description: str,
    progress: float,
    importance: float = 0.5,
) -> EmployeeActivity:
    """Record goal progress activity."""
    service = ActivityService(session)
    return await service.record(
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type=ActivityEventType.GOAL_PROGRESS,
        description=f"Made progress on: {goal_description} ({progress:.0%})",
        data={"goal": goal_description, "progress": progress},
        importance=importance,
    )


async def record_intention_completed(
    session: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    intention_description: str,
    result: dict[str, Any] | None = None,
    importance: float = 0.7,
) -> EmployeeActivity:
    """Record intention completion activity."""
    service = ActivityService(session)
    return await service.record(
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type=ActivityEventType.INTENTION_COMPLETED,
        description=f"Completed: {intention_description}",
        data={"intention": intention_description, "result": result or {}},
        importance=importance,
    )


async def record_error(
    session: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    error_message: str,
    context: dict[str, Any] | None = None,
    importance: float = 0.8,
) -> EmployeeActivity:
    """Record an error activity."""
    service = ActivityService(session)
    return await service.record(
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type=ActivityEventType.ERROR_OCCURRED,
        description=f"Error: {error_message}",
        data={"error": error_message, "context": context or {}},
        importance=importance,
    )


__all__ = [
    "ActivityService",
    "record_email_sent",
    "record_error",
    "record_goal_progress",
    "record_intention_completed",
]
