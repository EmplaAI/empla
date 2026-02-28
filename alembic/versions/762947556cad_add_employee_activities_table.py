"""add employee_activities table

Revision ID: 762947556cad
Revises: c3d4e5f6g7h8
Create Date: 2026-02-26 18:05:37.382707

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '762947556cad'
down_revision: Union[str, None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('employee_activities',
    sa.Column('id', sa.UUID(), nullable=False, comment='Unique identifier'),
    sa.Column('tenant_id', sa.UUID(), nullable=False, comment='Tenant this activity belongs to'),
    sa.Column('employee_id', sa.UUID(), nullable=False, comment='Employee who performed this activity'),
    sa.Column('event_type', sa.String(length=50), nullable=False, comment='Type of event (email_sent, goal_progress, intention_completed, etc.)'),
    sa.Column('description', sa.String(length=500), nullable=False, comment='Human-readable description of the activity'),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='Additional structured data about the activity'),
    sa.Column('importance', sa.Float(), server_default=sa.text('0.5'), nullable=False, comment='Importance score (0.0-1.0), used for filtering/ranking'),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='When the activity occurred (UTC)'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='When this record was created (UTC)'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='When this record was last updated (UTC)'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_activities_employee_time', 'employee_activities', ['employee_id', 'occurred_at'], unique=False)
    op.create_index('idx_activities_importance', 'employee_activities', ['employee_id', 'importance'], unique=False)
    op.create_index('idx_activities_tenant_time', 'employee_activities', ['tenant_id', 'occurred_at'], unique=False)
    op.create_index('idx_activities_type', 'employee_activities', ['employee_id', 'event_type'], unique=False)
    op.create_index(op.f('ix_employee_activities_employee_id'), 'employee_activities', ['employee_id'], unique=False)
    op.create_index(op.f('ix_employee_activities_tenant_id'), 'employee_activities', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_employee_activities_tenant_id'), table_name='employee_activities')
    op.drop_index(op.f('ix_employee_activities_employee_id'), table_name='employee_activities')
    op.drop_index('idx_activities_type', table_name='employee_activities')
    op.drop_index('idx_activities_tenant_time', table_name='employee_activities')
    op.drop_index('idx_activities_importance', table_name='employee_activities')
    op.drop_index('idx_activities_employee_time', table_name='employee_activities')
    op.drop_table('employee_activities')
