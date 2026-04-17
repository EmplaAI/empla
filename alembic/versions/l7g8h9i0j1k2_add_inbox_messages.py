"""Add inbox_messages table for PR #86

Revision ID: l7g8h9i0j1k2
Revises: k6f7g8h9i0j1
Create Date: 2026-04-16

PR #86 adds the employee → human inbox. Employees post structured
messages (subject + typed content blocks) via
``DigitalEmployee.post_to_inbox()``; admins read, mark-read, and
soft-delete from the dashboard.

The content body is a list of typed blocks (``text``,
``cost_breakdown``, ``link``, ``stat``, ``list``) stored as JSONB —
the cost hard-stop posts ``[text, cost_breakdown, link]`` so the
"why did my employee pause?" context lives INSIDE the message, not
behind a click.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "l7g8h9i0j1k2"
down_revision: str | None = "k6f7g8h9i0j1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.UUID(), nullable=False, comment="Unique identifier"),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Tenant this message belongs to",
        ),
        sa.Column(
            "employee_id",
            sa.UUID(),
            nullable=False,
            comment="Employee that posted the message",
        ),
        sa.Column(
            "priority",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'normal'"),
            comment="Priority tier (urgent, normal, off). 'off' = silently "
            "logged, not surfaced; 'urgent' triggers dashboard-wide banners.",
        ),
        sa.Column(
            "subject",
            sa.String(length=200),
            nullable=False,
            comment="Short subject line shown in list view",
        ),
        sa.Column(
            "blocks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="List of typed InboxBlock objects (text, cost_breakdown, "
            "link, stat, list). Body size capped at 10kB at write time.",
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the message was marked read (NULL = unread)",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the message was soft-deleted (NULL = live)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the message was posted (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this record was last updated (UTC)",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "priority IN ('urgent', 'normal', 'off')",
            name="ck_inbox_messages_priority",
        ),
    )
    # Primary list view: most recent first, per tenant.
    op.create_index(
        "idx_inbox_tenant_created",
        "inbox_messages",
        ["tenant_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Unread badge count — read path hits this 10+ times per minute.
    op.create_index(
        "idx_inbox_tenant_unread",
        "inbox_messages",
        ["tenant_id"],
        postgresql_where=sa.text("read_at IS NULL AND deleted_at IS NULL"),
    )
    # Per-employee list view (e.g., "all messages from Jordan") and
    # urgent-banner query which filters by priority.
    op.create_index(
        "idx_inbox_employee_created",
        "inbox_messages",
        ["employee_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_inbox_urgent_unread",
        "inbox_messages",
        ["tenant_id"],
        postgresql_where=sa.text(
            "priority = 'urgent' AND read_at IS NULL AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_inbox_urgent_unread", table_name="inbox_messages")
    op.drop_index("idx_inbox_employee_created", table_name="inbox_messages")
    op.drop_index("idx_inbox_tenant_unread", table_name="inbox_messages")
    op.drop_index("idx_inbox_tenant_created", table_name="inbox_messages")
    op.drop_table("inbox_messages")
