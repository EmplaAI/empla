"""
empla.api.v1.endpoints.scheduler - Scheduled Actions API (PR #82)

Three endpoints over the existing ``WorkingMemory`` scheduled-action
items (``content["subtype"] == "scheduled_action"``). No new storage,
no migration.

- ``GET  /employees/{id}/schedule``                 list queued actions
- ``POST /employees/{id}/schedule``                 add a user-requested action
- ``DELETE /employees/{id}/schedule/{action_id}``   cancel one-shot or recurring

Source tagging:
  Self-scheduled actions written from the employee's intention-execution
  path carry ``content["source"] = "employee"`` (PR #82). Actions filed
  via this endpoint carry ``"user_requested"``. The BDI loop's
  perception prefix differentiates so the LLM sees whose idea it was.

Tenant isolation:
  ``_verify_employee`` scopes every query to ``auth.tenant_id`` and
  rejects soft-deleted employees. Same pattern as the memory and tools
  endpoints.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.scheduler import (
    ScheduledActionCreateRequest,
    ScheduledActionListResponse,
    ScheduledActionResponse,
)
from empla.models.employee import Employee
from empla.models.memory import WorkingMemory

logger = logging.getLogger(__name__)

router = APIRouter()


async def _verify_employee(db: DBSession, employee_id: UUID, tenant_id: UUID) -> None:
    """Enforce tenant ownership + soft-delete filter. 404 otherwise."""
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


def _row_to_response(row: WorkingMemory) -> ScheduledActionResponse | None:
    """Render a WorkingMemory row into the response schema, or None if malformed.

    Treats legacy rows (no ``source`` key) as ``"employee"`` — every action
    recorded before PR #82 was self-scheduled.
    """
    content = row.content or {}
    if content.get("subtype") != "scheduled_action":
        return None
    scheduled_for_str = content.get("scheduled_for")
    if not scheduled_for_str:
        return None
    try:
        scheduled_for = datetime.fromisoformat(scheduled_for_str)
    except (ValueError, TypeError):
        return None

    created_at_str = content.get("created_at")
    created_at: datetime | None = None
    if created_at_str:
        with contextlib.suppress(ValueError, TypeError):
            created_at = datetime.fromisoformat(created_at_str)

    return ScheduledActionResponse(
        id=row.id,
        description=str(content.get("description", "")),
        scheduled_for=scheduled_for,
        recurring=bool(content.get("recurring", False)),
        interval_hours=content.get("interval_hours"),
        source=content.get("source", "employee"),  # legacy rows default to employee
        created_at=created_at,
    )


@router.get(
    "/{employee_id}/schedule",
    response_model=ScheduledActionListResponse,
)
async def list_scheduled_actions(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> ScheduledActionListResponse:
    """List pending scheduled actions for an employee, soonest first."""
    await _verify_employee(db, employee_id, auth.tenant_id)

    result = await db.execute(
        select(WorkingMemory).where(
            WorkingMemory.tenant_id == auth.tenant_id,
            WorkingMemory.employee_id == employee_id,
            WorkingMemory.deleted_at.is_(None),
            WorkingMemory.item_type == "task",
        )
    )
    rows = result.scalars().all()

    items: list[ScheduledActionResponse] = []
    for row in rows:
        rendered = _row_to_response(row)
        if rendered is not None:
            items.append(rendered)
    items.sort(key=lambda a: a.scheduled_for)
    return ScheduledActionListResponse(items=items, total=len(items))


@router.post(
    "/{employee_id}/schedule",
    response_model=ScheduledActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_action(
    db: DBSession,
    auth: CurrentUser,
    body: ScheduledActionCreateRequest,
    employee_id: UUID,
) -> ScheduledActionResponse:
    """Add a user-requested scheduled action to the employee's working memory.

    The employee's next BDI cycle sees it via ``_check_scheduled_actions``
    with a ``USER-REQUESTED SCHEDULED ACTION:`` prefix — explicit signal
    that the user filed it, not the employee itself.
    """
    await _verify_employee(db, employee_id, auth.tenant_id)

    scheduled_for_utc = body.scheduled_for.astimezone(UTC)
    now = datetime.now(UTC)
    if scheduled_for_utc <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scheduled_for must be in the future",
        )

    action_id = str(uuid4())
    content = {
        "subtype": "scheduled_action",
        "action_id": action_id,
        "description": body.description,
        "scheduled_for": scheduled_for_utc.isoformat(),
        "recurring": body.recurring,
        "interval_hours": body.interval_hours if body.recurring else None,
        "context": {},
        "created_at": now.isoformat(),
        "source": "user_requested",
    }

    # `WorkingMemory.get_active_items` filters on ``expires_at > now``. If
    # we don't set ``expires_at`` to something past ``scheduled_for``, the
    # row disappears from the loop's view before firing. 24-hour grace so
    # even if the loop is paused or slow, the action stays visible once due.
    expires_at_ts = scheduled_for_utc.timestamp() + 86400

    row = WorkingMemory(
        tenant_id=auth.tenant_id,
        employee_id=employee_id,
        item_type="task",
        content=content,
        importance=0.7,
        expires_at=expires_at_ts,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info(
        "User-requested scheduled action created",
        extra={
            "employee_id": str(employee_id),
            "tenant_id": str(auth.tenant_id),
            "scheduled_for": content["scheduled_for"],
            "recurring": body.recurring,
        },
    )

    rendered = _row_to_response(row)
    if rendered is None:  # defensive — we just constructed it
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to render created action",
        )
    return rendered


@router.delete(
    "/{employee_id}/schedule/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_scheduled_action(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    action_id: UUID,
) -> None:
    """Cancel a queued action. Works for one-shot and recurring, employee- or user-sourced."""
    await _verify_employee(db, employee_id, auth.tenant_id)

    result = await db.execute(
        select(WorkingMemory).where(
            WorkingMemory.id == action_id,
            WorkingMemory.tenant_id == auth.tenant_id,
            WorkingMemory.employee_id == employee_id,
            WorkingMemory.deleted_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()
    if row is None or (row.content or {}).get("subtype") != "scheduled_action":
        # Opaque 404 — don't leak whether the row exists as something else.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled action not found",
        )

    # Soft-delete via timestamp (WorkingMemory inherits from TenantScopedModel
    # which uses a deleted_at column). The loop's _check_scheduled_actions
    # filters on get_active_items() which skips deleted_at.
    row.deleted_at = datetime.now(UTC)
    await db.commit()

    logger.info(
        "Scheduled action cancelled",
        extra={
            "employee_id": str(employee_id),
            "tenant_id": str(auth.tenant_id),
            "action_id": str(action_id),
            "source": (row.content or {}).get("source", "employee"),
        },
    )
