"""phase2_provenance_and_techport

Revision ID: a1b2c3d4e5f6
Revises: f3a9f0df7570
Create Date: 2026-11-14 14:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f3a9f0df7570'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply Phase 2 provenance columns and NASA TechPort projects table."""
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'source_system',
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'raw_source_hash',
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'last_synced_at',
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'field_provenance',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )
        batch_op.create_index(
            batch_op.f('ix_components_source_system'),
            ['source_system'],
            unique=False,
        )

    op.create_table(
        'techport_projects',
        sa.Column('techport_id', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('status', sa.String(length=64), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('benefits', sa.Text(), nullable=True),
        sa.Column('lead_organization', sa.String(length=256), nullable=True),
        sa.Column('program', sa.String(length=128), nullable=True),
        sa.Column('trl_begin', sa.Integer(), nullable=True),
        sa.Column('trl_current', sa.Integer(), nullable=True),
        sa.Column('trl_end', sa.Integer(), nullable=True),
        sa.Column('last_updated_date', sa.String(length=32), nullable=True),
        sa.Column('canonical_url', sa.String(length=512), nullable=False),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('techport_projects', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_techport_projects_id'),
            ['id'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_techport_projects_techport_id'),
            ['techport_id'],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f('ix_techport_projects_title'),
            ['title'],
            unique=False,
        )


def downgrade() -> None:
    """Revert Phase 2 schema additions."""
    with op.batch_alter_table('techport_projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_techport_projects_title'))
        batch_op.drop_index(batch_op.f('ix_techport_projects_techport_id'))
        batch_op.drop_index(batch_op.f('ix_techport_projects_id'))

    op.drop_table('techport_projects')

    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_components_source_system'))
        batch_op.drop_column('field_provenance')
        batch_op.drop_column('last_synced_at')
        batch_op.drop_column('raw_source_hash')
        batch_op.drop_column('source_system')
