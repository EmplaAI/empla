"""add MCP server support to integrations

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-02-28 00:00:00.000000

Adds integration_type column to integrations table, relaxes provider and
auth_type CHECK constraints, and makes employee_id nullable on
integration_credentials for tenant-level MCP server credentials.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6g7h8i9j0"
down_revision: str | None = "d4e5f6g7h8i9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- integrations table ---

    # 1. Add integration_type column (default existing rows to oauth_provider)
    op.add_column(
        "integrations",
        sa.Column(
            "integration_type",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'oauth_provider'"),
        ),
    )

    # 2. Drop old CHECK constraints
    op.drop_constraint("ck_integrations_provider", "integrations", type_="check")
    op.drop_constraint("ck_integrations_auth_type", "integrations", type_="check")

    # 3. Add new CHECK constraint for integration_type
    op.create_check_constraint(
        "ck_integrations_integration_type",
        "integrations",
        "integration_type IN ('oauth_provider', 'mcp_server')",
    )

    # 4. Add expanded auth_type CHECK (includes MCP auth types)
    op.create_check_constraint(
        "ck_integrations_auth_type",
        "integrations",
        "auth_type IN ('user_oauth', 'service_account', 'api_key', 'bearer_token', 'oauth', 'none')",
    )

    # 5. Drop old unique index and recreate with integration_type filter
    op.drop_index("idx_integrations_tenant_provider", table_name="integrations")
    op.create_index(
        "idx_integrations_tenant_provider",
        "integrations",
        ["tenant_id", "provider"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND integration_type = 'oauth_provider'"),
    )

    # 6. Add unique index for MCP server names per tenant
    op.create_index(
        "idx_integrations_tenant_mcp_provider",
        "integrations",
        ["tenant_id", "provider"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND integration_type = 'mcp_server'"),
    )

    # 7. Add index for tenant + integration_type
    op.create_index(
        "idx_integrations_tenant_type",
        "integrations",
        ["tenant_id", "integration_type"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- integration_credentials table ---

    # 7. Make employee_id nullable
    op.alter_column(
        "integration_credentials",
        "employee_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
    )

    # 8. Drop old credential_type CHECK, add expanded one
    op.drop_constraint("ck_credentials_credential_type", "integration_credentials", type_="check")
    op.create_check_constraint(
        "ck_credentials_credential_type",
        "integration_credentials",
        "credential_type IN ('oauth_tokens', 'service_account_key', 'api_key', 'bearer_token')",
    )

    # 9. Drop old unique index, recreate with employee_id IS NOT NULL filter
    op.drop_index("idx_credentials_employee_integration", table_name="integration_credentials")
    op.create_index(
        "idx_credentials_employee_integration",
        "integration_credentials",
        ["employee_id", "integration_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND employee_id IS NOT NULL"),
    )

    # 10. Add unique index for tenant-level credentials (employee_id IS NULL)
    op.create_index(
        "idx_credentials_tenant_integration",
        "integration_credentials",
        ["integration_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND employee_id IS NULL"),
    )

    # 11. Backfill existing rows
    op.execute("UPDATE integrations SET integration_type = 'oauth_provider' WHERE integration_type IS NULL")


def downgrade() -> None:
    # --- Safety: abort if MCP-era data exists that would violate old constraints ---
    conn = op.get_bind()

    mcp_integrations = conn.execute(
        sa.text("SELECT COUNT(*) FROM integrations WHERE integration_type = 'mcp_server'")
    ).scalar()
    if mcp_integrations:
        raise RuntimeError(
            f"Cannot downgrade: {mcp_integrations} MCP server integration(s) exist. "
            "Delete all MCP server integrations before downgrading."
        )

    null_employee_creds = conn.execute(
        sa.text("SELECT COUNT(*) FROM integration_credentials WHERE employee_id IS NULL AND deleted_at IS NULL")
    ).scalar()
    if null_employee_creds:
        raise RuntimeError(
            f"Cannot downgrade: {null_employee_creds} tenant-level credential(s) with NULL employee_id exist. "
            "Remove these credentials before downgrading."
        )

    mcp_cred_types = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM integration_credentials "
            "WHERE credential_type NOT IN ('oauth_tokens', 'service_account_key') AND deleted_at IS NULL"
        )
    ).scalar()
    if mcp_cred_types:
        raise RuntimeError(
            f"Cannot downgrade: {mcp_cred_types} credential(s) with MCP-era credential_type values exist. "
            "Remove these credentials before downgrading."
        )

    # --- integration_credentials table ---
    op.drop_index("idx_credentials_tenant_integration", table_name="integration_credentials")
    op.drop_index("idx_credentials_employee_integration", table_name="integration_credentials")
    op.create_index(
        "idx_credentials_employee_integration",
        "integration_credentials",
        ["employee_id", "integration_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_constraint("ck_credentials_credential_type", "integration_credentials", type_="check")
    op.create_check_constraint(
        "ck_credentials_credential_type",
        "integration_credentials",
        "credential_type IN ('oauth_tokens', 'service_account_key')",
    )
    op.alter_column(
        "integration_credentials",
        "employee_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
    )

    # --- integrations table ---
    op.drop_index("idx_integrations_tenant_type", table_name="integrations")
    op.drop_index("idx_integrations_tenant_mcp_provider", table_name="integrations")
    op.drop_index("idx_integrations_tenant_provider", table_name="integrations")
    op.create_index(
        "idx_integrations_tenant_provider",
        "integrations",
        ["tenant_id", "provider"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_constraint("ck_integrations_auth_type", "integrations", type_="check")
    op.create_check_constraint(
        "ck_integrations_auth_type",
        "integrations",
        "auth_type IN ('user_oauth', 'service_account')",
    )
    op.drop_constraint("ck_integrations_integration_type", "integrations", type_="check")
    op.create_check_constraint(
        "ck_integrations_provider",
        "integrations",
        "provider IN ('google_workspace', 'microsoft_graph')",
    )
    op.drop_column("integrations", "integration_type")
