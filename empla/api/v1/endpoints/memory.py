"""
empla.api.v1.endpoints.memory - Memory Read Endpoints

Paginated, filtered read-only access to an employee's four memory systems:
episodic, semantic, procedural, and working. Mirrors the pattern in
``bdi.py`` — inline offset/limit pagination, tenant-scoped queries, and
response schemas that explicitly avoid the lazy ``employee`` relationship
to prevent N+1.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.memory import (
    EpisodicMemoryListResponse,
    EpisodicMemoryResponse,
    ProceduralMemoryListResponse,
    ProceduralMemoryResponse,
    SemanticMemoryListResponse,
    SemanticMemoryResponse,
    WorkingMemoryListResponse,
    WorkingMemoryResponse,
)
from empla.models.employee import Employee
from empla.models.memory import (
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    WorkingMemory,
)

logger = logging.getLogger(__name__)

router = APIRouter()


_VALID_EPISODE_TYPES = {
    "interaction",
    "event",
    "observation",
    "feedback",
    "strategic_planning",
    "intention_execution",
    "deep_reflection",
}
_VALID_FACT_TYPES = {"entity", "relationship", "rule", "definition"}
_VALID_PROCEDURE_TYPES = {
    "skill",
    "workflow",
    "heuristic",
    "intention_execution",
    "playbook",
    "reflection_adjustment",
}
_VALID_WORKING_ITEM_TYPES = {"task", "goal", "observation", "conversation", "context"}

# Belt-and-suspenders cap on the working-memory endpoint. Working memory is
# "always small (tens of items at most)" by design, but this invariant is not
# enforced upstream. Without a LIMIT, a bug or runaway producer could surface
# thousands of items in one response.
_MAX_WORKING_MEMORY_ITEMS = 200


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
# Episodic
# =========================================================================


@router.get("/{employee_id}/memory/episodic", response_model=EpisodicMemoryListResponse)
async def list_episodic_memory(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 25,
    episode_type: Annotated[str | None, Query()] = None,
    min_importance: Annotated[float | None, Query(ge=0, le=1)] = None,
) -> EpisodicMemoryListResponse:
    """List episodic memories for an employee, newest first."""
    if episode_type and episode_type not in _VALID_EPISODE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid episode_type '{episode_type}'. Must be one of: "
                f"{', '.join(sorted(_VALID_EPISODE_TYPES))}"
            ),
        )
    await _verify_employee(db, employee_id, auth.tenant_id)

    base = select(EpisodicMemory).where(
        EpisodicMemory.employee_id == employee_id,
        EpisodicMemory.tenant_id == auth.tenant_id,
        EpisodicMemory.deleted_at.is_(None),
    )
    if episode_type:
        base = base.where(EpisodicMemory.episode_type == episode_type)
    if min_importance is not None:
        base = base.where(EpisodicMemory.importance >= min_importance)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    query = (
        base.order_by(EpisodicMemory.occurred_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    return EpisodicMemoryListResponse(
        items=[EpisodicMemoryResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )


# =========================================================================
# Semantic
# =========================================================================


@router.get("/{employee_id}/memory/semantic", response_model=SemanticMemoryListResponse)
async def list_semantic_memory(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 25,
    fact_type: Annotated[str | None, Query()] = None,
    subject: Annotated[str | None, Query()] = None,
    predicate: Annotated[str | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
) -> SemanticMemoryListResponse:
    """List semantic facts for an employee, highest confidence first."""
    if fact_type and fact_type not in _VALID_FACT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid fact_type '{fact_type}'. Must be one of: "
                f"{', '.join(sorted(_VALID_FACT_TYPES))}"
            ),
        )
    await _verify_employee(db, employee_id, auth.tenant_id)

    base = select(SemanticMemory).where(
        SemanticMemory.employee_id == employee_id,
        SemanticMemory.tenant_id == auth.tenant_id,
        SemanticMemory.deleted_at.is_(None),
    )
    if fact_type:
        base = base.where(SemanticMemory.fact_type == fact_type)
    if subject:
        base = base.where(SemanticMemory.subject == subject)
    if predicate:
        base = base.where(SemanticMemory.predicate == predicate)
    if min_confidence is not None:
        base = base.where(SemanticMemory.confidence >= min_confidence)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    query = (
        base.order_by(SemanticMemory.confidence.desc(), SemanticMemory.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    return SemanticMemoryListResponse(
        items=[SemanticMemoryResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )


# =========================================================================
# Procedural
# =========================================================================


@router.get("/{employee_id}/memory/procedural", response_model=ProceduralMemoryListResponse)
async def list_procedural_memory(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 25,
    procedure_type: Annotated[str | None, Query()] = None,
    min_success_rate: Annotated[float | None, Query(ge=0, le=1)] = None,
    is_playbook: Annotated[bool | None, Query()] = None,
) -> ProceduralMemoryListResponse:
    """List procedures for an employee, highest success rate first."""
    if procedure_type and procedure_type not in _VALID_PROCEDURE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid procedure_type '{procedure_type}'. Must be one of: "
                f"{', '.join(sorted(_VALID_PROCEDURE_TYPES))}"
            ),
        )
    await _verify_employee(db, employee_id, auth.tenant_id)

    base = select(ProceduralMemory).where(
        ProceduralMemory.employee_id == employee_id,
        ProceduralMemory.tenant_id == auth.tenant_id,
        ProceduralMemory.deleted_at.is_(None),
    )
    if procedure_type:
        base = base.where(ProceduralMemory.procedure_type == procedure_type)
    if min_success_rate is not None:
        base = base.where(ProceduralMemory.success_rate >= min_success_rate)
    if is_playbook is not None:
        base = base.where(ProceduralMemory.is_playbook.is_(is_playbook))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    query = (
        base.order_by(ProceduralMemory.success_rate.desc(), ProceduralMemory.execution_count.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    return ProceduralMemoryListResponse(
        items=[ProceduralMemoryResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )


# =========================================================================
# Working
# =========================================================================


@router.get("/{employee_id}/memory/working", response_model=WorkingMemoryListResponse)
async def list_working_memory(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    item_type: Annotated[str | None, Query()] = None,
) -> WorkingMemoryListResponse:
    """
    List the current working-memory items for an employee.

    Working memory is always small (tens of items at most), so no pagination.
    Items are returned in importance order, highest first.
    """
    if item_type and item_type not in _VALID_WORKING_ITEM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid item_type '{item_type}'. Must be one of: "
                f"{', '.join(sorted(_VALID_WORKING_ITEM_TYPES))}"
            ),
        )
    await _verify_employee(db, employee_id, auth.tenant_id)

    query = (
        select(WorkingMemory)
        .where(
            WorkingMemory.employee_id == employee_id,
            WorkingMemory.tenant_id == auth.tenant_id,
            WorkingMemory.deleted_at.is_(None),
        )
        .order_by(WorkingMemory.importance.desc(), WorkingMemory.updated_at.desc())
        .limit(_MAX_WORKING_MEMORY_ITEMS)
    )
    if item_type:
        query = query.where(WorkingMemory.item_type == item_type)

    result = await db.execute(query)
    items = list(result.scalars().all())
    if len(items) >= _MAX_WORKING_MEMORY_ITEMS:
        logger.warning(
            "working memory hit cap for employee=%s tenant=%s (cap=%d) — "
            "expected tens of items; check for runaway producer",
            employee_id,
            auth.tenant_id,
            _MAX_WORKING_MEMORY_ITEMS,
        )

    return WorkingMemoryListResponse(
        items=[WorkingMemoryResponse.model_validate(w) for w in items],
        total=len(items),
    )
