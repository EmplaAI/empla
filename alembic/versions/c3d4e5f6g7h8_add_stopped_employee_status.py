"""Add stopped status to employee status constraint

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-02-20

Adds the 'stopped' status to the employees table CHECK constraint.
- "stopped" means a clean shutdown (employee can be restarted)
- "terminated" means permanent removal (employee cannot be restarted)

This distinction supports the employee process infrastructure where
each employee runs as a persistent subprocess. Stop is a normal
lifecycle event (like shutting down a service); terminated is permanent.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: str | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add stopped status to employee status constraint."""
    op.drop_constraint("ck_employees_status", "employees", type_="check")
    op.create_check_constraint(
        "ck_employees_status",
        "employees",
        "status IN ('onboarding', 'active', 'paused', 'stopped', 'terminated')",
    )


def downgrade() -> None:
    """Remove stopped status from employee status constraint.

    Migrates any 'stopped' employees to 'paused' before removing the constraint.
    """
    op.execute(
        sa.text("UPDATE employees SET status = 'paused' WHERE status = 'stopped'")
    )
    op.drop_constraint("ck_employees_status", "employees", type_="check")
    op.create_check_constraint(
        "ck_employees_status",
        "employees",
        "status IN ('onboarding', 'active', 'paused', 'terminated')",
    )
