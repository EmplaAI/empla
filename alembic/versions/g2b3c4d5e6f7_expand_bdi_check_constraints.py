"""Expand BDI check constraints for new source/procedure types

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-18

The BDI loop now writes beliefs with source='execution_outcome' and
source='deep_reflection', and procedural memory with
procedure_type='intention_execution'. The existing DB constraints
only allow the original values. This migration updates them.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Update ck_beliefs_source to include new source types
    op.drop_constraint("ck_beliefs_source", "beliefs", type_="check")
    op.create_check_constraint(
        "ck_beliefs_source",
        "beliefs",
        "source IN ('observation', 'inference', 'told_by_human', 'prior', 'execution_outcome', 'deep_reflection')",
    )

    # Update ck_procedural_procedure_type to include intention_execution
    op.drop_constraint("ck_procedural_procedure_type", "memory_procedural", type_="check")
    op.create_check_constraint(
        "ck_procedural_procedure_type",
        "memory_procedural",
        "procedure_type IN ('skill', 'workflow', 'heuristic', 'intention_execution')",
    )

    # Update ck_integrations_integration_type (mcp_server -> mcp, oauth_provider -> api)
    op.execute("UPDATE integrations SET integration_type = 'mcp' WHERE integration_type = 'mcp_server'")
    op.execute("UPDATE integrations SET integration_type = 'api' WHERE integration_type = 'oauth_provider'")
    op.drop_constraint("ck_integrations_integration_type", "integrations", type_="check")
    op.create_check_constraint(
        "ck_integrations_integration_type",
        "integrations",
        "integration_type IN ('api', 'mcp')",
    )


def downgrade() -> None:
    # Restore original ck_beliefs_source
    op.drop_constraint("ck_beliefs_source", "beliefs", type_="check")
    op.create_check_constraint(
        "ck_beliefs_source",
        "beliefs",
        "source IN ('observation', 'inference', 'told_by_human', 'prior')",
    )

    # Restore original ck_procedural_procedure_type
    op.drop_constraint("ck_procedural_procedure_type", "memory_procedural", type_="check")
    op.create_check_constraint(
        "ck_procedural_procedure_type",
        "memory_procedural",
        "procedure_type IN ('skill', 'workflow', 'heuristic')",
    )

    # Restore original ck_integrations_integration_type
    op.execute("UPDATE integrations SET integration_type = 'mcp_server' WHERE integration_type = 'mcp'")
    op.execute("UPDATE integrations SET integration_type = 'oauth_provider' WHERE integration_type = 'api'")
    op.drop_constraint("ck_integrations_integration_type", "integrations", type_="check")
    op.create_check_constraint(
        "ck_integrations_integration_type",
        "integrations",
        "integration_type IN ('oauth_provider', 'mcp_server')",
    )
