"""Add 'restarting' to employees.status CHECK constraint

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2026-04-15

PR #83 introduces a settings page. Changing tenant settings triggers a
runner restart so processes pick up fresh config at startup. We mark
affected employees with ``status='restarting'`` as an intermediate state
so the loop exits gracefully and the supervisor can respawn. The existing
CHECK constraint allows only onboarding / active / paused / stopped /
terminated, so the first UPDATE would fail without this migration.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "j5e6f7g8h9i0"
down_revision: str | None = "i4d5e6f7g8h9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS ck_employees_status")
    op.execute(
        "ALTER TABLE employees ADD CONSTRAINT ck_employees_status "
        "CHECK (status IN ('onboarding', 'active', 'paused', 'stopped', "
        "'terminated', 'restarting'))"
    )


def downgrade() -> None:
    # Never silently drop rows — if any employees are mid-restart, fail the
    # downgrade so the operator decides whether to wait for them to stabilize
    # or manually transition them first.
    bind = op.get_bind()
    count = bind.execute(
        sa_text("SELECT COUNT(*) FROM employees WHERE status = 'restarting'")
    ).scalar()
    if count and int(count) > 0:
        raise RuntimeError(
            f"Refusing to downgrade: {count} employees are in 'restarting' state. "
            "Wait for the supervisor to finish respawning them, or UPDATE them "
            "to a pre-PR-#83 status first."
        )
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS ck_employees_status")
    op.execute(
        "ALTER TABLE employees ADD CONSTRAINT ck_employees_status "
        "CHECK (status IN ('onboarding', 'active', 'paused', 'stopped', 'terminated'))"
    )
