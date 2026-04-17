"""
empla.services.inbox_service - Inbox message writer

Employees post messages to the per-tenant inbox via
:func:`post_to_inbox`. The BDI loop's cost hard-stop calls this
directly; the :meth:`DigitalEmployee.post_to_inbox` helper wraps it
with error swallowing so a failed inbox write never crashes a cycle.

Design notes:
    - Uses a short-lived session (its own sessionmaker instance), not
      the BDI loop's long-lived session. Same pattern as
      ``_record_cycle_metrics`` — writes don't pollute the loop's
      transaction and a bad DB state doesn't cascade into belief
      updates.
    - Body-size cap is 10kB (sum of all block data payloads). Oversize
      messages are rejected at this layer with a WARN log — the loop
      does not retry, does not raise, does not crash. The per-block
      4kB cap at the schema layer is a cheaper first check; this is
      the total-message cap.
    - Returns ``bool`` so callers can branch on success (e.g., cost
      hard-stop wants to know whether the inbox message landed before
      flipping the employee status, but writing the pause is still
      worth doing even if the notification failed).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from empla.models.inbox import InboxMessage

logger = logging.getLogger(__name__)

# Total body-size cap, summed across all block data payloads. Oversize
# messages are dropped with a WARN. Matches the cap documented in the
# Phase 5 plan; tuned to "a few screens of dense content" — the cost
# breakdown block for 10 cycles is ~2kB, leaving headroom for 2-3
# complementary blocks.
MAX_BODY_BYTES = 10_240


async def post_to_inbox(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    employee_id: UUID,
    subject: str,
    blocks: list[dict[str, Any]],
    priority: str = "normal",
) -> InboxMessage | None:
    """Write an inbox message. Never raises.

    Args:
        sessionmaker: Short-lived async session factory. The inbox write
            runs in its own transaction, independent of any caller's
            session.
        tenant_id: Tenant owning the message. FK-enforced.
        employee_id: Employee posting the message. FK-enforced.
        subject: Short subject line, truncated to 200 chars if longer.
        blocks: List of InboxBlock-shaped dicts. Total serialized size
            must be ≤ ``MAX_BODY_BYTES``; oversize messages are dropped
            with a WARN.
        priority: One of ``urgent`` / ``normal`` / ``off``. Invalid
            values fall back to ``normal`` with a WARN (the CHECK
            constraint would raise otherwise — cheaper to normalize
            here).

    Returns:
        The created :class:`InboxMessage`, or ``None`` if the write was
        dropped (oversize, invalid shape) or failed (DB error, missing
        FK). Callers must treat ``None`` as "message not delivered".
    """
    # Priority normalization. The DB CHECK would reject unknown values
    # anyway, but defaulting to 'normal' at the service layer means a
    # single typo doesn't 500 the entire cost-hard-stop flow.
    if priority not in ("urgent", "normal", "off"):
        logger.warning(
            "Invalid inbox priority %r; defaulting to 'normal'",
            priority,
            extra={"tenant_id": str(tenant_id), "employee_id": str(employee_id)},
        )
        priority = "normal"

    # Subject truncation. The DB column is varchar(200); len() > 200
    # would fail at write with a vague asyncpg error. Truncate + WARN.
    if len(subject) > 200:
        logger.warning(
            "Inbox subject truncated from %d to 200 chars",
            len(subject),
            extra={"tenant_id": str(tenant_id), "employee_id": str(employee_id)},
        )
        subject = subject[:197] + "..."

    # Body-size cap. Serialize once for the check AND to guarantee the
    # JSONB column stores valid JSON (the SQLAlchemy dialect serializes
    # on insert, but that happens inside the transaction — a too-large
    # payload fails there with a worse error).
    try:
        serialized_size = len(json.dumps(blocks, default=str))
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Inbox blocks not JSON-serializable: %s — dropping message",
            exc,
            extra={"tenant_id": str(tenant_id), "employee_id": str(employee_id)},
        )
        return None

    if serialized_size > MAX_BODY_BYTES:
        logger.warning(
            "Inbox body is %d bytes, max is %d. Dropping message '%s'.",
            serialized_size,
            MAX_BODY_BYTES,
            subject,
            extra={"tenant_id": str(tenant_id), "employee_id": str(employee_id)},
        )
        return None

    try:
        async with sessionmaker() as session:
            msg = InboxMessage(
                tenant_id=tenant_id,
                employee_id=employee_id,
                priority=priority,
                subject=subject,
                blocks=blocks,
            )
            session.add(msg)
            await session.commit()
            await session.refresh(msg)
            logger.info(
                "Posted inbox message",
                extra={
                    "tenant_id": str(tenant_id),
                    "employee_id": str(employee_id),
                    "message_id": str(msg.id),
                    "priority": priority,
                    "block_count": len(blocks),
                },
            )
            return msg
    except Exception:
        # Broad catch: FK violations, connection errors, CHECK failures
        # all end up here. The loop must not crash on inbox failures.
        logger.exception(
            "Inbox write failed — message dropped",
            extra={
                "tenant_id": str(tenant_id),
                "employee_id": str(employee_id),
                "subject": subject,
            },
        )
        return None
