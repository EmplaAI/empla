"""Add integration tables for OAuth and credentials

Revision ID: a1b2c3d4e5f6
Revises: c14764448a4d
Create Date: 2025-12-29 12:00:00.000000

This migration adds:
- integrations: Tenant-level OAuth provider configuration
- integration_credentials: Employee-level encrypted tokens
- integration_oauth_states: Temporary OAuth state for CSRF protection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c14764448a4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create integrations table (depends on tenants, users)
    op.create_table(
        "integrations",
        sa.Column("id", sa.UUID(), nullable=False, comment="Unique identifier"),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Tenant this record belongs to",
        ),
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
            comment="Provider (google_workspace, microsoft_graph)",
        ),
        sa.Column(
            "auth_type",
            sa.String(length=30),
            nullable=False,
            comment="Auth type (user_oauth, service_account)",
        ),
        sa.Column(
            "display_name",
            sa.String(length=200),
            nullable=False,
            comment="Human-readable name for this integration",
        ),
        sa.Column(
            "oauth_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="OAuth config (client_id, redirect_uri, scopes) - NO secrets",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
            comment="Integration status (active, disabled, revoked)",
        ),
        sa.Column(
            "enabled_by",
            sa.UUID(),
            nullable=True,
            comment="User who enabled this integration",
        ),
        sa.Column(
            "enabled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When integration was enabled",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this record was soft-deleted (UTC), None if active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this record was created (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this record was last updated (UTC)",
        ),
        sa.CheckConstraint(
            "provider IN ('google_workspace', 'microsoft_graph')",
            name="ck_integrations_provider",
        ),
        sa.CheckConstraint(
            "auth_type IN ('user_oauth', 'service_account')",
            name="ck_integrations_auth_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'revoked')",
            name="ck_integrations_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_integrations_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["enabled_by"],
            ["users.id"],
            name="fk_integrations_enabled_by",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_integrations_tenant_provider",
        "integrations",
        ["tenant_id", "provider"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_integrations_tenant",
        "integrations",
        ["tenant_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_integrations_status",
        "integrations",
        ["tenant_id", "status"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Create integration_credentials table (depends on integrations, employees)
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.UUID(), nullable=False, comment="Unique identifier"),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Tenant this record belongs to",
        ),
        sa.Column(
            "integration_id",
            sa.UUID(),
            nullable=False,
            comment="Integration this credential belongs to",
        ),
        sa.Column(
            "employee_id",
            sa.UUID(),
            nullable=False,
            comment="Employee this credential belongs to",
        ),
        sa.Column(
            "credential_type",
            sa.String(length=30),
            nullable=False,
            comment="Type (oauth_tokens, service_account_key)",
        ),
        sa.Column(
            "encrypted_data",
            sa.LargeBinary(),
            nullable=False,
            comment="Fernet-encrypted credential JSON",
        ),
        sa.Column(
            "encryption_key_id",
            sa.String(length=50),
            nullable=False,
            comment="ID of encryption key used (for rotation)",
        ),
        sa.Column(
            "token_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="Non-sensitive metadata (email, scopes)",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
            comment="Credential status (active, expired, revoked, refreshing)",
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When token was issued",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When token expires (NULL for service accounts)",
        ),
        sa.Column(
            "last_refreshed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When token was last refreshed",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When credential was last used",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this record was soft-deleted (UTC), None if active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this record was created (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this record was last updated (UTC)",
        ),
        sa.CheckConstraint(
            "credential_type IN ('oauth_tokens', 'service_account_key')",
            name="ck_credentials_credential_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'revoked', 'refreshing')",
            name="ck_credentials_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_credentials_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name="fk_credentials_integration_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_credentials_employee_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_credentials_employee_integration",
        "integration_credentials",
        ["employee_id", "integration_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_credentials_expires",
        "integration_credentials",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'active'"),
    )
    op.create_index(
        "idx_credentials_tenant",
        "integration_credentials",
        ["tenant_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_credentials_status",
        "integration_credentials",
        ["tenant_id", "status"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_credentials_integration",
        "integration_credentials",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        "idx_credentials_employee",
        "integration_credentials",
        ["employee_id"],
        unique=False,
    )

    # Create integration_oauth_states table (depends on integrations, employees, users)
    op.create_table(
        "integration_oauth_states",
        sa.Column("id", sa.UUID(), nullable=False, comment="Unique identifier"),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
            comment="Tenant this record belongs to",
        ),
        sa.Column(
            "state",
            sa.String(length=100),
            nullable=False,
            unique=True,
            comment="OAuth state parameter (CSRF token)",
        ),
        sa.Column(
            "integration_id",
            sa.UUID(),
            nullable=False,
            comment="Integration being authorized",
        ),
        sa.Column(
            "employee_id",
            sa.UUID(),
            nullable=False,
            comment="Employee being authorized for",
        ),
        sa.Column(
            "initiated_by",
            sa.UUID(),
            nullable=False,
            comment="User who initiated the flow",
        ),
        sa.Column(
            "redirect_uri",
            sa.String(length=500),
            nullable=False,
            comment="Where to redirect after callback",
        ),
        sa.Column(
            "code_verifier",
            sa.String(length=128),
            nullable=True,
            comment="PKCE code verifier (stored temporarily)",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="State expires after 10 minutes",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this record was soft-deleted (UTC), None if active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this record was created (UTC)",
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
            name="fk_oauth_states_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name="fk_oauth_states_integration_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_oauth_states_employee_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by"],
            ["users.id"],
            name="fk_oauth_states_initiated_by",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_oauth_state_state",
        "integration_oauth_states",
        ["state"],
        unique=True,
    )
    op.create_index(
        "idx_oauth_state_expires",
        "integration_oauth_states",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "idx_oauth_state_tenant",
        "integration_oauth_states",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("integration_oauth_states")
    op.drop_table("integration_credentials")
    op.drop_table("integrations")
