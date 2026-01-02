"""Add revocation_failed status to credential status constraint

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-30

This migration adds the 'revocation_failed' status to the credentials table
CHECK constraint. This status indicates that token revocation with the
OAuth provider failed, meaning the token may still be valid at the provider
even though we've attempted to revoke it.

This is a security improvement to properly track credentials that couldn't
be revoked with the provider, rather than silently marking them as revoked.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6g7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add revocation_failed status to credential status constraint."""
    # Drop the old constraint
    op.drop_constraint("ck_credentials_status", "integration_credentials", type_="check")

    # Add new constraint with revocation_failed status
    op.create_check_constraint(
        "ck_credentials_status",
        "integration_credentials",
        "status IN ('active', 'expired', 'revoked', 'refreshing', 'revocation_failed')",
    )


def downgrade() -> None:
    """Remove revocation_failed status from credential status constraint.

    WARNING: This downgrade will fail if any credentials have status='revocation_failed'.
    You must first update those credentials to a different status (e.g., 'revoked')
    before running this downgrade.
    """
    # Drop the new constraint
    op.drop_constraint("ck_credentials_status", "integration_credentials", type_="check")

    # Re-add old constraint without revocation_failed
    op.create_check_constraint(
        "ck_credentials_status",
        "integration_credentials",
        "status IN ('active', 'expired', 'revoked', 'refreshing')",
    )
