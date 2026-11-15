"""phase3_porkchop_jobs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-14 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create porkchop_jobs table for asynchronous trajectory calculations."""
    op.create_table(
        'porkchop_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'QUEUED',
                'RUNNING',
                'COMPLETED',
                'FAILED',
                'CANCELLED',
                name='porkchopjobstatus',
            ),
            nullable=False,
            default='QUEUED',
        ),
        sa.Column('progress_percent', sa.Float(), nullable=False, default=0.0),
        sa.Column('origin_body', sa.String(length=64), nullable=False),
        sa.Column('target_body', sa.String(length=64), nullable=False),
        sa.Column('departure_start', sa.String(length=32), nullable=False),
        sa.Column('departure_end', sa.String(length=32), nullable=False),
        sa.Column('arrival_start', sa.String(length=32), nullable=False),
        sa.Column('arrival_end', sa.String(length=32), nullable=False),
        sa.Column('step_size_days', sa.Float(), nullable=False, default=2.0),
        sa.Column('parameters', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('results', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f('ix_porkchop_jobs_id'),
        'porkchop_jobs',
        ['id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_porkchop_jobs_status'),
        'porkchop_jobs',
        ['status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_porkchop_jobs_origin_body'),
        'porkchop_jobs',
        ['origin_body'],
        unique=False,
    )
    op.create_index(
        op.f('ix_porkchop_jobs_target_body'),
        'porkchop_jobs',
        ['target_body'],
        unique=False,
    )


def downgrade() -> None:
    """Drop porkchop_jobs table."""
    op.drop_index(op.f('ix_porkchop_jobs_target_body'), table_name='porkchop_jobs')
    op.drop_index(op.f('ix_porkchop_jobs_origin_body'), table_name='porkchop_jobs')
    op.drop_index(op.f('ix_porkchop_jobs_status'), table_name='porkchop_jobs')
    op.drop_index(op.f('ix_porkchop_jobs_id'), table_name='porkchop_jobs')
    op.drop_table('porkchop_jobs')
