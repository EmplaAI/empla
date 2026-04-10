"""
empla.api.v1.endpoints.playbooks - Playbook Viewer API

Dashboard-facing endpoints for viewing playbook performance, success rates,
and promotion candidates. Read-only — playbook promotion happens autonomously
in the reflection phase of the BDI loop.
"""

import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from empla.api.deps import CurrentUser, DBSession
from empla.models.employee import Employee
from empla.models.memory import ProceduralMemory

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================


class PlaybookResponse(BaseModel):
    """Individual playbook data for the dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    procedure_type: str
    success_rate: float
    execution_count: int
    success_count: int
    avg_execution_time: float | None = None
    last_executed_at: datetime | None = None
    promoted_at: datetime | None = None
    learned_from: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    trigger_conditions: dict[str, Any] = Field(default_factory=dict)


class PlaybookListResponse(BaseModel):
    """Paginated playbook list."""

    items: list[PlaybookResponse]
    total: int


class PlaybookStats(BaseModel):
    """Aggregate playbook statistics for an employee."""

    employee_id: UUID
    total_playbooks: int
    avg_success_rate: float
    total_executions: int
    promotion_candidates: int


# ============================================================================
# Helpers
# ============================================================================


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


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/{employee_id}/playbooks",
    response_model=PlaybookListResponse,
)
async def list_playbooks(
    employee_id: UUID,
    db: DBSession,
    auth: CurrentUser,
    min_success_rate: Annotated[float, Query(ge=0, le=1)] = 0.0,
    learned_from: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "success_rate",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PlaybookListResponse:
    """List playbooks for an employee.

    Returns promoted procedures with their success rates, execution counts,
    and other performance data for the dashboard playbook viewer.
    """
    await _verify_employee(db, employee_id, auth.tenant_id)
    filters = [
        ProceduralMemory.tenant_id == auth.tenant_id,
        ProceduralMemory.employee_id == employee_id,
        ProceduralMemory.is_playbook.is_(True),
        ProceduralMemory.deleted_at.is_(None),
        ProceduralMemory.success_rate >= min_success_rate,
    ]
    if learned_from:
        filters.append(ProceduralMemory.learned_from == learned_from)

    # Sort
    sort_columns = {
        "success_rate": ProceduralMemory.success_rate.desc(),
        "execution_count": ProceduralMemory.execution_count.desc(),
        "promoted_at": ProceduralMemory.promoted_at.desc().nullslast(),
        "name": ProceduralMemory.name.asc(),
    }
    order = sort_columns.get(sort_by, ProceduralMemory.success_rate.desc())

    # Count
    count_result = await db.execute(select(func.count()).where(*filters))
    total = int(count_result.scalar() or 0)

    # Fetch
    query = select(ProceduralMemory).where(*filters).order_by(order).limit(limit)
    result = await db.execute(query)
    items = [
        PlaybookResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            procedure_type=p.procedure_type,
            success_rate=p.success_rate,
            execution_count=p.execution_count,
            success_count=p.success_count,
            avg_execution_time=p.avg_execution_time,
            last_executed_at=p.last_executed_at,
            promoted_at=p.promoted_at,
            learned_from=p.learned_from,
            steps=p.steps or [],
            trigger_conditions=p.trigger_conditions or {},
        )
        for p in result.scalars()
    ]

    return PlaybookListResponse(items=items, total=total)


@router.get(
    "/{employee_id}/playbooks/stats",
    response_model=PlaybookStats,
)
async def get_playbook_stats(
    employee_id: UUID,
    db: DBSession,
    auth: CurrentUser,
) -> PlaybookStats:
    """Get aggregate playbook statistics for an employee."""
    await _verify_employee(db, employee_id, auth.tenant_id)
    base = [
        ProceduralMemory.tenant_id == auth.tenant_id,
        ProceduralMemory.employee_id == employee_id,
        ProceduralMemory.deleted_at.is_(None),
    ]

    # Playbook stats
    playbook_result = await db.execute(
        select(
            func.count(),
            func.avg(ProceduralMemory.success_rate),
            func.sum(ProceduralMemory.execution_count),
        ).where(*base, ProceduralMemory.is_playbook.is_(True))
    )
    row = playbook_result.one()
    total_playbooks = int(row[0] or 0)
    avg_success = float(row[1] or 0)
    total_execs = int(row[2] or 0)

    # Promotion candidates: non-playbook procedures with 3+ executions and 70%+ success
    candidates_result = await db.execute(
        select(func.count()).where(
            *base,
            ProceduralMemory.is_playbook.is_(False),
            ProceduralMemory.execution_count >= 3,
            ProceduralMemory.success_rate >= 0.7,
        )
    )
    candidates = int(candidates_result.scalar() or 0)

    return PlaybookStats(
        employee_id=employee_id,
        total_playbooks=total_playbooks,
        avg_success_rate=round(avg_success, 4),
        total_executions=total_execs,
        promotion_candidates=candidates,
    )
