"""add platform_oauth_apps table and use_platform_credentials column

Revision ID: d4e5f6g7h8i9
Revises: 762947556cad
Create Date: 2026-02-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "762947556cad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create platform_oauth_apps table (global, not tenant-scoped)
    op.create_table(
        "platform_oauth_apps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(50), nullable=False, unique=True),
        sa.Column("client_id", sa.String(500), nullable=False),
        sa.Column("encrypted_client_secret", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_id", sa.String(50), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column(
            "default_scopes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_platform_oauth_apps_status",
        ),
    )

    # Add use_platform_credentials column to integrations table
    op.add_column(
        "integrations",
        sa.Column(
            "use_platform_credentials",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("integrations", "use_platform_credentials")
    op.drop_table("platform_oauth_apps")
