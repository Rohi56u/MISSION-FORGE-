"""add_firebase_uid_to_users

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('firebase_uid', sa.String(length=128), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_firebase_uid'), ['firebase_uid'], unique=True)

    with op.batch_alter_table('dossier_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dossier_jobs_design_id'), ['design_id'], unique=False)

    with op.batch_alter_table('dossier_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dossier_reports_design_id'), ['design_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dossier_reports_room_id'), ['room_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('dossier_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dossier_reports_room_id'))
        batch_op.drop_index(batch_op.f('ix_dossier_reports_design_id'))

    with op.batch_alter_table('dossier_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dossier_jobs_design_id'))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_firebase_uid'))
        batch_op.drop_column('firebase_uid')
