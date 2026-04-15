"""Backfill Phase 4 playbook schema + add version/enabled for PR #84

Revision ID: k6f7g8h9i0j1
Revises: j5e6f7g8h9i0
Create Date: 2026-04-15

PR #84 introduces the playbook editor. This migration does two jobs:

1. **Backfill the Phase 4 (PR #73) playbook schema that was never migrated.**
   PR #73 added ``is_playbook``, ``promoted_at``, the ``idx_procedural_playbooks``
   partial index, and widened the ``procedure_type`` + ``learned_from`` CHECK
   constraints on the model, but no alembic migration was ever generated. Unit
   tests passed because they use ``metadata.create_all()``, bypassing alembic.
   /qa on PR #84 caught the drift — any deployment built from migrations 500s
   on every playbook query. Using ``IF NOT EXISTS`` so this is idempotent on
   DBs that already have the columns from ``create_all``.

2. **Add the PR #84 editor columns.**
   - ``version``: monotonic counter bumped on every write by either the API
     editor path or the autonomous ``promote_to_playbook`` path. The PUT
     endpoint's ``expected_version`` gives optimistic locking — concurrent
     edits across two tabs, or an API edit racing with reflection's
     auto-promotion, produce a 409 instead of silently clobbering.
   - ``enabled``: lets users disable a playbook without demoting it (which
     would lose the ``promoted_at`` timestamp and force a re-evaluation).
     The loop's playbook lookup filters on ``enabled = true``.

All additions use sensible defaults so existing rows back-fill cleanly.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "k6f7g8h9i0j1"
down_revision: str | None = "j5e6f7g8h9i0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Backfill Phase 4 (PR #73) playbook schema ---
    # is_playbook + promoted_at columns, idempotent for DBs that got them via create_all
    op.execute(
        "ALTER TABLE memory_procedural "
        "ADD COLUMN IF NOT EXISTS is_playbook BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE memory_procedural "
        "ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMP WITH TIME ZONE"
    )

    # Fast lookup for playbooks (partial index matching the model)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_procedural_playbooks "
        "ON memory_procedural (tenant_id, employee_id, success_rate) "
        "WHERE is_playbook = true AND deleted_at IS NULL"
    )

    # Widen CHECK constraints that drifted when new procedure_type / learned_from
    # values were added in Phase 3C/4 without a migration
    op.execute("ALTER TABLE memory_procedural DROP CONSTRAINT IF EXISTS ck_procedural_procedure_type")
    op.execute(
        "ALTER TABLE memory_procedural ADD CONSTRAINT ck_procedural_procedure_type "
        "CHECK (procedure_type IN ('skill', 'workflow', 'heuristic', "
        "'intention_execution', 'playbook', 'reflection_adjustment'))"
    )

    op.execute("ALTER TABLE memory_procedural DROP CONSTRAINT IF EXISTS ck_procedural_learned_from")
    op.execute(
        "ALTER TABLE memory_procedural ADD CONSTRAINT ck_procedural_learned_from "
        "CHECK (learned_from IN ('human_demonstration', 'trial_and_error', "
        "'instruction', 'pre_built', 'autonomous_discovery', 'deep_reflection'))"
    )

    # --- PR #84 editor columns ---
    op.execute(
        "ALTER TABLE memory_procedural "
        "ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE memory_procedural "
        "ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    # PR #84 columns
    op.execute("ALTER TABLE memory_procedural DROP COLUMN IF EXISTS enabled")
    op.execute("ALTER TABLE memory_procedural DROP COLUMN IF EXISTS version")

    # NOTE: We intentionally leave the widened CHECK constraints in place on
    # downgrade. Re-narrowing them would fail against any row with
    # procedure_type='playbook' / 'reflection_adjustment' or
    # learned_from='autonomous_discovery' / 'deep_reflection' — values the
    # runtime has been writing since Phase 3C/4 without a migration. Downgrade
    # must not destroy user data, and the widened CHECKs are a superset of the
    # old ones, so nothing breaks by leaving them.

    op.execute("DROP INDEX IF EXISTS idx_procedural_playbooks")
    op.execute("ALTER TABLE memory_procedural DROP COLUMN IF EXISTS promoted_at")
    op.execute("ALTER TABLE memory_procedural DROP COLUMN IF EXISTS is_playbook")
