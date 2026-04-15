"""Add version (optimistic lock) + enabled (toggleable) to memory_procedural

Revision ID: k6f7g8h9i0j1
Revises: j5e6f7g8h9i0
Create Date: 2026-04-15

PR #84 introduces the playbook editor. Two new columns on
``memory_procedural``:

- ``version``: monotonic counter bumped on every write by either the API
  editor path or the autonomous ``promote_to_playbook`` path. The PUT
  endpoint's ``expected_version`` gives optimistic locking — concurrent
  edits across two tabs, or an API edit racing with reflection's
  auto-promotion, produce a 409 instead of silently clobbering.
- ``enabled``: lets users disable a playbook without demoting it (which
  would lose the ``promoted_at`` timestamp and force a re-evaluation).
  The loop's playbook lookup filters on ``enabled = true``.

Both are ``NOT NULL`` with sensible defaults so existing rows
back-fill cleanly.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k6f7g8h9i0j1"
down_revision: str | None = "j5e6f7g8h9i0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_procedural",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "memory_procedural",
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("memory_procedural", "enabled")
    op.drop_column("memory_procedural", "version")
