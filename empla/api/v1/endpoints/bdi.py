"""
empla.api.v1.endpoints.bdi - BDI State Endpoints

Read-only endpoints for goals, intentions, and beliefs scoped to an employee.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.bdi import (
    BeliefListResponse,
    BeliefResponse,
    GoalListResponse,
    GoalResponse,
    IntentionListResponse,
    IntentionResponse,
)
from empla.models.belief import Belief
from empla.models.employee import Employee, EmployeeGoal, EmployeeIntention

logger = logging.getLogger(__name__)

router = APIRouter()


async def _verify_employee(db: DBSession, employee_id: UUID, tenant_id: UUID) -> None:
    """Verify employee exists and belongs to tenant."""
    result = await db.execute(
        select(Employee.id).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )


def _pages(total: int, page_size: int) -> int:
    return (total + page_size - 1) // page_size if total > 0 else 1


# =========================================================================
# Goals
# =========================================================================


@router.get("/{employee_id}/goals", response_model=GoalListResponse)
async def list_employee_goals(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    goal_status: Annotated[str | None, Query(alias="status")] = None,
) -> GoalListResponse:
    """List goals for an employee."""
    await _verify_employee(db, employee_id, auth.tenant_id)

    base = select(EmployeeGoal).where(
        EmployeeGoal.employee_id == employee_id,
        EmployeeGoal.tenant_id == auth.tenant_id,
        EmployeeGoal.deleted_at.is_(None),
    )

    if goal_status:
        base = base.where(EmployeeGoal.status == goal_status)

    count_q = select(func.count()).select_from(base.subquery())

    total = (await db.execute(count_q)).scalar() or 0

    query = (
        base.order_by(EmployeeGoal.priority.desc(), EmployeeGoal.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    goals = list(result.scalars().all())

    return GoalListResponse(
        items=[GoalResponse.model_validate(g) for g in goals],
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )


# =========================================================================
# Intentions
# =========================================================================


@router.get("/{employee_id}/intentions", response_model=IntentionListResponse)
async def list_employee_intentions(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    intention_status: Annotated[str | None, Query(alias="status")] = None,
    goal_id: Annotated[UUID | None, Query()] = None,
) -> IntentionListResponse:
    """List intentions for an employee."""
    await _verify_employee(db, employee_id, auth.tenant_id)

    base = select(EmployeeIntention).where(
        EmployeeIntention.employee_id == employee_id,
        EmployeeIntention.tenant_id == auth.tenant_id,
        EmployeeIntention.deleted_at.is_(None),
    )

    if intention_status:
        base = base.where(EmployeeIntention.status == intention_status)
    if goal_id:
        base = base.where(EmployeeIntention.goal_id == goal_id)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = (
        base.order_by(EmployeeIntention.priority.desc(), EmployeeIntention.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    intentions = list(result.scalars().all())

    return IntentionListResponse(
        items=[IntentionResponse.model_validate(i) for i in intentions],
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )


# =========================================================================
# Beliefs
# =========================================================================


@router.get("/{employee_id}/beliefs", response_model=BeliefListResponse)
async def list_employee_beliefs(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    belief_type: Annotated[str | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
) -> BeliefListResponse:
    """List beliefs for an employee."""
    await _verify_employee(db, employee_id, auth.tenant_id)

    base = select(Belief).where(
        Belief.employee_id == employee_id,
        Belief.tenant_id == auth.tenant_id,
        Belief.deleted_at.is_(None),
    )

    if belief_type:
        base = base.where(Belief.belief_type == belief_type)
    if min_confidence is not None:
        base = base.where(Belief.confidence >= min_confidence)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = (
        base.order_by(Belief.confidence.desc(), Belief.last_updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    beliefs = list(result.scalars().all())

    return BeliefListResponse(
        items=[BeliefResponse.model_validate(b) for b in beliefs],
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )
