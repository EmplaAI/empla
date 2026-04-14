"""Widen audit_log.actor_type to include 'webhook'

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2026-04-14

PR #81 adds a per-tenant webhook event feed sourced from AuditLog with
``actor_type='webhook'``. The existing CHECK constraint only allows
employee / user / system, so the first webhook INSERT would fail
without this migration.

Drop and recreate the constraint with the new value.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "i4d5e6f7g8h9"
down_revision: str | None = "h3c4d5e6f7g8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS ck_audit_log_actor_type")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_actor_type "
        "CHECK (actor_type IN ('employee', 'user', 'system', 'webhook'))"
    )


def downgrade() -> None:
    # Drop any webhook-actor rows so the narrower constraint can re-apply.
    op.execute("DELETE FROM audit_log WHERE actor_type = 'webhook'")
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS ck_audit_log_actor_type")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_actor_type "
        "CHECK (actor_type IN ('employee', 'user', 'system'))"
    )
