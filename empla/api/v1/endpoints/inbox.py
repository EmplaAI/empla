"""
empla.api.v1.endpoints.inbox - Inbox API endpoints

Reads and modifies :class:`empla.models.inbox.InboxMessage` rows.
All endpoints are tenant-scoped via :class:`CurrentUser` — a member
in tenant A cannot read tenant B's inbox.

Endpoints:
    - ``GET  /inbox``           — paginated list + unread count
    - ``POST /inbox/{id}/read`` — mark as read (idempotent)
    - ``DELETE /inbox/{id}``    — soft-delete (idempotent 204)

Writes come from :func:`empla.services.inbox_service.post_to_inbox`,
called by the BDI loop's cost hard-stop and
:meth:`DigitalEmployee.post_to_inbox`. The dashboard cannot create
messages — the inbox is one-way, employee → human, for now.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy import update as sa_update

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.inbox import (
    InboxListResponse,
    InboxMessageResponse,
    InboxPriority,
)
from empla.models.inbox import InboxMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=InboxListResponse)
async def list_inbox_messages(
    db: DBSession,
    auth: CurrentUser,
    unread_only: Annotated[bool, Query()] = False,
    priority: Annotated[InboxPriority | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> InboxListResponse:
    """List inbox messages for the current tenant.

    Args:
        unread_only: If true, filter to unread messages (``read_at IS NULL``).
        priority: If set, filter to a single priority tier.
        page: 1-indexed page number.
        page_size: Items per page (1-100, default 50).

    Returns:
        Paginated list + the tenant's total unread count (used by the
        sidebar badge — computed in the same roundtrip to avoid a second
        query).
    """
    filters = [
        InboxMessage.tenant_id == auth.tenant_id,
        InboxMessage.deleted_at.is_(None),
    ]
    if unread_only:
        filters.append(InboxMessage.read_at.is_(None))
    if priority is not None:
        filters.append(InboxMessage.priority == priority)

    # Count the filtered list
    count_result = await db.execute(select(func.count()).where(*filters))
    total = int(count_result.scalar() or 0)

    # Tenant-wide unread count for the sidebar badge — uses the
    # idx_inbox_tenant_unread partial index and never reflects the
    # page_size/priority filters (badge shows ALL unread).
    unread_result = await db.execute(
        select(func.count()).where(
            InboxMessage.tenant_id == auth.tenant_id,
            InboxMessage.deleted_at.is_(None),
            InboxMessage.read_at.is_(None),
        )
    )
    unread_count = int(unread_result.scalar() or 0)

    offset = (page - 1) * page_size
    query = (
        select(InboxMessage)
        .where(*filters)
        .order_by(InboxMessage.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [InboxMessageResponse.model_validate(m) for m in result.scalars()]

    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return InboxListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("/{message_id}/read", response_model=InboxMessageResponse)
async def mark_read(
    message_id: UUID,
    db: DBSession,
    auth: CurrentUser,
) -> InboxMessageResponse:
    """Mark a message as read. Idempotent: re-marking returns 200 with
    the same ``read_at`` timestamp unchanged.

    Uses a single UPDATE+WHERE+RETURNING to avoid the read-then-write
    race where two tabs mark the same message read simultaneously. The
    ``read_at IS NULL`` clause makes this idempotent — a second mark
    finds zero rows and we reload + return the already-set timestamp.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        sa_update(InboxMessage)
        .where(
            InboxMessage.id == message_id,
            InboxMessage.tenant_id == auth.tenant_id,
            InboxMessage.deleted_at.is_(None),
            InboxMessage.read_at.is_(None),
        )
        .values(read_at=now, updated_at=now)
        .returning(InboxMessage)
    )
    row = result.scalar_one_or_none()
    await db.commit()

    if row is not None:
        return InboxMessageResponse.model_validate(row)

    # Zero rows updated: either already read (idempotent success), or
    # deleted/missing (404). Distinguish with a follow-up SELECT that
    # ignores the read_at filter.
    reload = await db.execute(
        select(InboxMessage).where(
            InboxMessage.id == message_id,
            InboxMessage.tenant_id == auth.tenant_id,
            InboxMessage.deleted_at.is_(None),
        )
    )
    existing = reload.scalar_one_or_none()
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inbox message not found",
        )
    return InboxMessageResponse.model_validate(existing)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: UUID,
    db: DBSession,
    auth: CurrentUser,
) -> None:
    """Soft-delete a message. Idempotent 204: deleting an already-
    deleted or missing message also returns 204 (we don't leak the
    distinction — the client's "make it go away" intent is satisfied).

    Uses UPDATE+WHERE so we don't load the row into the session. The
    ``deleted_at IS NULL`` guard makes a second DELETE a no-op.
    """
    now = datetime.now(UTC)
    await db.execute(
        sa_update(InboxMessage)
        .where(
            InboxMessage.id == message_id,
            InboxMessage.tenant_id == auth.tenant_id,
            InboxMessage.deleted_at.is_(None),
        )
        .values(deleted_at=now, updated_at=now)
    )
    await db.commit()
    logger.info(
        "Inbox message soft-deleted",
        extra={
            "tenant_id": str(auth.tenant_id),
            "message_id": str(message_id),
            "user_id": str(auth.user_id),
        },
    )
