"""Add composite index for semantic memory pagination

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-04-14

PR #79 (memory browsing API) lists semantic memories ORDER BY
``confidence DESC, updated_at DESC``. Existing indexes only cover
the WHERE clause; PostgreSQL has to filesort every page request.

This composite index lets the planner serve the paginated query with
an index scan instead of a sort. Adding it concurrently so it doesn't
lock writes on existing tables.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "h3c4d5e6f7g8"
down_revision: str | None = "g2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    # Alembic auto-wraps in a transaction unless we explicitly disable.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_semantic_employee_confidence
            ON memory_semantic (employee_id, confidence DESC, updated_at DESC)
            WHERE deleted_at IS NULL
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_semantic_employee_confidence")
