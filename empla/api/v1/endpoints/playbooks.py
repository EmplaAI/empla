"""
empla.api.v1.endpoints.playbooks - Playbook Viewer API

Dashboard-facing endpoints for viewing playbook performance, success rates,
and promotion candidates. Read-only — playbook promotion happens autonomously
in the reflection phase of the BDI loop.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError

from empla.api.deps import CurrentUser, DBSession, RequireAdmin
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
    # PR #84
    enabled: bool = True
    version: int = 0


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
# Editor Request Models (PR #84)
# ============================================================================


class PlaybookStep(BaseModel):
    """One step in a playbook. Keep the shape permissive — the BDI loop
    reads ``description`` but different procedure types attach extra
    keys (tool, args, condition) that we pass through."""

    model_config = ConfigDict(extra="allow")

    description: str = Field(min_length=1, max_length=500)


class PlaybookCreateRequest(BaseModel):
    """POST /playbooks body. Creates a new ProceduralMemory row already
    flagged ``is_playbook=True`` (the user is authoring one directly,
    not promoting an autonomous discovery)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    steps: list[PlaybookStep] = Field(min_length=1, max_length=50)
    trigger_conditions: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PlaybookUpdateRequest(BaseModel):
    """PUT /playbooks/{id} body. All content fields optional; only those
    provided are overwritten. ``expected_version`` is mandatory for
    optimistic locking — without it concurrent edits silently clobber."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(
        description="Must match the stored version or the PUT returns 409."
    )
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    steps: list[PlaybookStep] | None = Field(default=None, min_length=1, max_length=50)
    trigger_conditions: dict[str, Any] | None = None
    enabled: bool | None = None


class PlaybookToggleRequest(BaseModel):
    """POST /playbooks/{id}/toggle body. Idempotent by design — the
    server flips to the explicit value instead of toggling blindly, so
    double-clicks don't thrash the row."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool


# ============================================================================
# Helpers
# ============================================================================


def _is_unique_name_violation(err: IntegrityError) -> bool:
    """Detect whether an IntegrityError came from the unique-name index.

    Inspects the constraint name on the underlying asyncpg error rather
    than string-matching the message text — which would silently break
    the next time PostgreSQL or asyncpg adjusts its error format.
    """
    diag = getattr(getattr(err, "orig", None), "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == "idx_procedural_unique_name":
        return True
    # Fallback: some adapters don't expose .diag; keep the substring
    # match as a defensive last resort but log so we notice if we land
    # on this branch in production.
    return "idx_procedural_unique_name" in str(err)


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
    items = [_to_response(p) for p in result.scalars()]

    return PlaybookListResponse(items=items, total=total)


def _to_response(p: ProceduralMemory) -> PlaybookResponse:
    return PlaybookResponse(
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
        enabled=p.enabled,
        version=p.version,
    )


async def _load_playbook(
    db: DBSession, playbook_id: UUID, employee_id: UUID, tenant_id: UUID
) -> ProceduralMemory:
    """Fetch a playbook enforcing tenant+employee ownership. 404 otherwise."""
    result = await db.execute(
        select(ProceduralMemory).where(
            ProceduralMemory.id == playbook_id,
            ProceduralMemory.employee_id == employee_id,
            ProceduralMemory.tenant_id == tenant_id,
            ProceduralMemory.deleted_at.is_(None),
            ProceduralMemory.is_playbook.is_(True),
        )
    )
    playbook = result.scalar_one_or_none()
    if playbook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )
    return playbook


# ============================================================================
# Editor endpoints (PR #84)
# ============================================================================


@router.post(
    "/{employee_id}/playbooks",
    response_model=PlaybookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_playbook(
    employee_id: UUID,
    body: PlaybookCreateRequest,
    db: DBSession,
    auth: RequireAdmin,
) -> PlaybookResponse:
    """Create a user-authored playbook from scratch.

    The autonomous promote_to_playbook path still exists for procedures
    learned from execution history; this endpoint lets an admin seed a
    playbook directly from domain knowledge.
    """
    await _verify_employee(db, employee_id, auth.tenant_id)

    playbook = ProceduralMemory(
        tenant_id=auth.tenant_id,
        employee_id=employee_id,
        name=body.name,
        description=body.description,
        procedure_type="playbook",
        steps=[step.model_dump() for step in body.steps],
        trigger_conditions=body.trigger_conditions,
        success_rate=0.0,
        execution_count=0,
        success_count=0,
        context={},
        is_playbook=True,
        promoted_at=datetime.now(UTC),
        learned_from="instruction",
        enabled=body.enabled,
        version=0,
    )
    db.add(playbook)
    try:
        await db.commit()
        await db.refresh(playbook)
    except IntegrityError as e:
        await db.rollback()
        # Unique-index collision on (employee_id, name) → 409, not 500.
        # Detect via the asyncpg constraint name on the underlying error.
        if _is_unique_name_violation(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A playbook named {body.name!r} already exists for this employee.",
            ) from e
        raise

    logger.info(
        "Playbook created",
        extra={
            "playbook_id": str(playbook.id),
            "employee_id": str(employee_id),
            "tenant_id": str(auth.tenant_id),
            "actor_user_id": str(auth.user_id),
        },
    )
    return _to_response(playbook)


@router.put(
    "/{employee_id}/playbooks/{playbook_id}",
    response_model=PlaybookResponse,
)
async def update_playbook(
    employee_id: UUID,
    playbook_id: UUID,
    body: PlaybookUpdateRequest,
    db: DBSession,
    auth: RequireAdmin,
) -> PlaybookResponse:
    """Edit a playbook with optimistic locking.

    The UPDATE filters on ``version = expected_version``; if it hits zero
    rows, either the playbook was deleted OR the version advanced — in
    either case, we return 409 so the client refetches and resolves the
    conflict. Both sides of the writer dual (API edit + autonomous
    promote_to_playbook) bump ``version``, so a reflection promotion
    mid-edit produces the same 409.
    """
    await _verify_employee(db, employee_id, auth.tenant_id)

    # Build the SET clause from non-None fields only.
    values: dict[str, Any] = {}
    if body.name is not None:
        values["name"] = body.name
    if body.description is not None:
        values["description"] = body.description
    if body.steps is not None:
        values["steps"] = [step.model_dump() for step in body.steps]
    if body.trigger_conditions is not None:
        values["trigger_conditions"] = body.trigger_conditions
    if body.enabled is not None:
        values["enabled"] = body.enabled
    # Always bump version — even a no-op PUT advances the lock so a stale
    # client's second PUT will 409.
    values["version"] = ProceduralMemory.version + 1

    result = await db.execute(
        update(ProceduralMemory)
        .where(
            and_(
                ProceduralMemory.id == playbook_id,
                ProceduralMemory.employee_id == employee_id,
                ProceduralMemory.tenant_id == auth.tenant_id,
                ProceduralMemory.deleted_at.is_(None),
                ProceduralMemory.is_playbook.is_(True),
                ProceduralMemory.version == body.expected_version,
            )
        )
        .values(**values)
        .returning(ProceduralMemory)
    )
    row = result.scalar_one_or_none()

    if row is None:
        # Either the playbook is gone (404) or the version advanced (409).
        # Distinguish by loading without the version filter.
        await db.rollback()  # release the failed UPDATE's lock
        try:
            current = await _load_playbook(db, playbook_id, employee_id, auth.tenant_id)
        except HTTPException:
            raise  # 404 — playbook genuinely missing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Playbook changed since you loaded it "
                f"(expected v{body.expected_version}, current v{current.version}). "
                "Reload and merge."
            ),
        )

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if _is_unique_name_violation(e):
            # Use values["name"] if the rename was the cause; fall back
            # to the row's pre-update name otherwise (shouldn't happen,
            # but better than printing literal None).
            offending_name = values.get("name") or row.name
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A playbook named {offending_name!r} already exists for this employee.",
            ) from e
        raise

    await db.refresh(row)
    logger.info(
        "Playbook updated",
        extra={
            "playbook_id": str(row.id),
            "employee_id": str(employee_id),
            "tenant_id": str(auth.tenant_id),
            "actor_user_id": str(auth.user_id),
            "new_version": row.version,
            "sections": list(values.keys()),
        },
    )
    return _to_response(row)


@router.post(
    "/{employee_id}/playbooks/{playbook_id}/toggle",
    response_model=PlaybookResponse,
)
async def toggle_playbook(
    employee_id: UUID,
    playbook_id: UUID,
    body: PlaybookToggleRequest,
    db: DBSession,
    auth: RequireAdmin,
) -> PlaybookResponse:
    """Enable or disable a playbook without demoting it.

    No ``expected_version`` — the caller provides the explicit target
    state, so double-clicks converge instead of racing. Version still
    bumps so concurrent PUT editors 409 as expected.
    """
    await _verify_employee(db, employee_id, auth.tenant_id)
    playbook = await _load_playbook(db, playbook_id, employee_id, auth.tenant_id)

    playbook.enabled = body.enabled
    playbook.version = playbook.version + 1
    await db.commit()
    await db.refresh(playbook)

    logger.info(
        "Playbook toggled",
        extra={
            "playbook_id": str(playbook.id),
            "employee_id": str(employee_id),
            "tenant_id": str(auth.tenant_id),
            "actor_user_id": str(auth.user_id),
            "enabled": body.enabled,
        },
    )
    return _to_response(playbook)


@router.delete(
    "/{employee_id}/playbooks/{playbook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_playbook(
    employee_id: UUID,
    playbook_id: UUID,
    db: DBSession,
    auth: RequireAdmin,
) -> None:
    """Soft-delete a playbook. Idempotent: a DELETE against an already-
    deleted row still returns 204 so optimistic-UI double-clicks don't
    surface error toasts."""
    await _verify_employee(db, employee_id, auth.tenant_id)

    # Match without the deleted_at filter so we can return 204 on an
    # already-deleted row. Still scoped to tenant+employee+is_playbook.
    result = await db.execute(
        select(ProceduralMemory).where(
            ProceduralMemory.id == playbook_id,
            ProceduralMemory.employee_id == employee_id,
            ProceduralMemory.tenant_id == auth.tenant_id,
            ProceduralMemory.is_playbook.is_(True),
        )
    )
    playbook = result.scalar_one_or_none()
    if playbook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )
    if playbook.deleted_at is not None:
        return  # already deleted — no-op

    playbook.deleted_at = datetime.now(UTC)
    playbook.version = playbook.version + 1
    await db.commit()

    logger.info(
        "Playbook deleted",
        extra={
            "playbook_id": str(playbook.id),
            "employee_id": str(employee_id),
            "tenant_id": str(auth.tenant_id),
            "actor_user_id": str(auth.user_id),
        },
    )


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
