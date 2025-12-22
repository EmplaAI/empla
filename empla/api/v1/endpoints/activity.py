"""
empla.api.v1.endpoints.activity - Activity Feed Endpoints

REST API endpoints for querying employee activity.
"""

import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from empla.api.deps import CurrentUser, DBSession
from empla.models.employee import Employee
from empla.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

router = APIRouter()


class ActivityResponse(BaseModel):
    """Schema for activity response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    event_type: str
    description: str
    data: dict[str, Any]
    importance: float
    occurred_at: datetime
    created_at: datetime


class ActivityListResponse(BaseModel):
    """Schema for paginated activity list."""

    items: list[ActivityResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ActivitySummaryResponse(BaseModel):
    """Schema for activity summary."""

    event_counts: dict[str, int]
    total: int


@router.get("", response_model=ActivityListResponse)
async def list_all_activities(
    db: DBSession,
    auth: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    event_type: Annotated[str | None, Query()] = None,
    min_importance: Annotated[float | None, Query(ge=0, le=1)] = None,
    since: Annotated[datetime | None, Query()] = None,
) -> ActivityListResponse:
    """
    List activities for all employees in the tenant.

    Args:
        db: Database session
        auth: Current user context
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
        event_type: Filter by event type
        min_importance: Minimum importance score
        since: Activities after this time

    Returns:
        Paginated list of activities
    """
    service = ActivityService(db)

    event_types = [event_type] if event_type else None

    activities, total = await service.get_activities(
        tenant_id=auth.tenant_id,
        event_types=event_types,
        min_importance=min_importance,
        since=since,
        page=page,
        page_size=page_size,
    )

    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return ActivityListResponse(
        items=[ActivityResponse.model_validate(a) for a in activities],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/summary", response_model=ActivitySummaryResponse)
async def get_activity_summary(
    db: DBSession,
    auth: CurrentUser,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> ActivitySummaryResponse:
    """
    Get activity summary for the tenant.

    Args:
        db: Database session
        auth: Current user context
        hours: Time window in hours (max 168 = 1 week)

    Returns:
        Activity counts by event type
    """
    service = ActivityService(db)

    event_counts = await service.get_summary(
        tenant_id=auth.tenant_id,
        hours=hours,
    )

    return ActivitySummaryResponse(
        event_counts=event_counts,
        total=sum(event_counts.values()),
    )


@router.get("/employees/{employee_id}", response_model=ActivityListResponse)
async def list_employee_activities(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    event_type: Annotated[str | None, Query()] = None,
    min_importance: Annotated[float | None, Query(ge=0, le=1)] = None,
    since: Annotated[datetime | None, Query()] = None,
) -> ActivityListResponse:
    """
    List activities for a specific employee.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
        event_type: Filter by event type
        min_importance: Minimum importance score
        since: Activities after this time

    Returns:
        Paginated list of activities

    Raises:
        HTTPException: If employee not found
    """
    # Verify employee belongs to tenant
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == auth.tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    service = ActivityService(db)

    event_types = [event_type] if event_type else None

    activities, total = await service.get_activities(
        tenant_id=auth.tenant_id,
        employee_id=employee_id,
        event_types=event_types,
        min_importance=min_importance,
        since=since,
        page=page,
        page_size=page_size,
    )

    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return ActivityListResponse(
        items=[ActivityResponse.model_validate(a) for a in activities],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/employees/{employee_id}/recent", response_model=list[ActivityResponse])
async def get_recent_activities(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[ActivityResponse]:
    """
    Get recent activities for an employee.

    Convenience endpoint for getting the most recent activities
    without pagination.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID
        limit: Max number of activities (max 50)

    Returns:
        List of recent activities

    Raises:
        HTTPException: If employee not found
    """
    # Verify employee belongs to tenant
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == auth.tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    service = ActivityService(db)
    activities = await service.get_recent(
        tenant_id=auth.tenant_id,
        employee_id=employee_id,
        limit=limit,
    )

    return [ActivityResponse.model_validate(a) for a in activities]


@router.get("/employees/{employee_id}/summary", response_model=ActivitySummaryResponse)
async def get_employee_activity_summary(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> ActivitySummaryResponse:
    """
    Get activity summary for a specific employee.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID
        hours: Time window in hours (max 168 = 1 week)

    Returns:
        Activity counts by event type

    Raises:
        HTTPException: If employee not found
    """
    # Verify employee belongs to tenant
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == auth.tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    service = ActivityService(db)

    event_counts = await service.get_summary(
        tenant_id=auth.tenant_id,
        employee_id=employee_id,
        hours=hours,
    )

    return ActivitySummaryResponse(
        event_counts=event_counts,
        total=sum(event_counts.values()),
    )
