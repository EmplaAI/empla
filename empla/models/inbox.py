"""
empla.models.inbox - Inbox Message Model

Employees post structured messages to a per-tenant inbox via
``DigitalEmployee.post_to_inbox()``. Admins read, mark-read, and
soft-delete them from the dashboard.

The body is a list of typed content blocks (``text``, ``cost_breakdown``,
``link``, ``stat``, ``list``) stored as JSONB. The schema for those
blocks lives in ``empla/api/v1/schemas/inbox.py`` — the DB just stores
the JSON shape; validation happens at the API boundary and at write time
in the inbox service.

Separate from ``AuditLog``: audit logs are forensic (what happened),
inbox messages are conversational (what the human needs to see). Mixing
them would tangle ACLs and retention policies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from empla.models.base import TenantScopedModel


class InboxMessage(TenantScopedModel):
    """Employee → human message with typed content blocks."""

    __tablename__ = "inbox_messages"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee that posted the message",
    )

    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'normal'"),
        comment=(
            "Priority tier. 'urgent' surfaces in a dashboard-wide banner "
            "until the user resumes/dismisses; 'normal' is the default; "
            "'off' is silently logged (e.g., tenant muted this channel) "
            "but written for audit completeness."
        ),
    )

    subject: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Short subject line shown in list view",
    )

    blocks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        comment=(
            "List of typed InboxBlock objects. Each block is "
            "{'kind': str, 'data': dict}. Size capped at 10kB by the "
            "inbox service at write time."
        ),
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the message was marked read (NULL = unread)",
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('urgent', 'normal', 'off')",
            name="ck_inbox_messages_priority",
        ),
        # Primary list view (tenant scope, newest first).
        Index(
            "idx_inbox_tenant_created",
            "tenant_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Unread count — hit frequently by sidebar badge polling.
        Index(
            "idx_inbox_tenant_unread",
            "tenant_id",
            postgresql_where=text("read_at IS NULL AND deleted_at IS NULL"),
        ),
        # Per-employee view (e.g., "messages from Jordan").
        Index(
            "idx_inbox_employee_created",
            "employee_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Dashboard-wide urgent banner query.
        Index(
            "idx_inbox_urgent_unread",
            "tenant_id",
            postgresql_where=text("priority = 'urgent' AND read_at IS NULL AND deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<InboxMessage(id={self.id}, priority={self.priority}, subject={self.subject!r})>"
