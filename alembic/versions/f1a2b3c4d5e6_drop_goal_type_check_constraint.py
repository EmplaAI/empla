"""Drop goal_type CHECK constraint and widen column

Revision ID: f1a2b3c4d5e6
Revises: e5f6g7h8i9j0
Create Date: 2026-03-02

The ck_employee_goals_goal_type constraint only allowed
('achievement', 'maintenance', 'prevention'), but the LLM-driven
loop creates goals with types like 'opportunity' and 'problem',
and the events system uses 'event_triggered', 'build_pipeline', etc.

goal_type is a free-form string label used as LLM context and for
human readability — no code branches on specific values. Dropping
the constraint lets the loop create goals from LLM analysis.

Also widens goal_type from VARCHAR(20) to VARCHAR(50) since LLM-generated
types can be longer than the original constraint-limited values.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e5f6g7h8i9j0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop goal_type CHECK constraint and widen column."""
    op.drop_constraint("ck_employee_goals_goal_type", "employee_goals", type_="check")
    op.alter_column(
        "employee_goals",
        "goal_type",
        type_=sa.String(50),
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Re-add goal_type CHECK constraint and narrow column.

    Replaces any non-standard goal_type values with 'achievement', narrows
    the column to VARCHAR(20), and re-adds the CHECK constraint.
    """
    op.execute(
        "UPDATE employee_goals SET goal_type = 'achievement' "
        "WHERE goal_type NOT IN ('achievement', 'maintenance', 'prevention')"
    )
    op.alter_column(
        "employee_goals",
        "goal_type",
        type_=sa.String(20),
        existing_type=sa.String(50),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_employee_goals_goal_type",
        "employee_goals",
        "goal_type IN ('achievement', 'maintenance', 'prevention')",
    )
