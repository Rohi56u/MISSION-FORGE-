"""phase6_dossiers

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Dossier Jobs table
    op.create_table(
        'dossier_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            'mission_id',
            sa.String(length=36),
            sa.ForeignKey('missions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.String(length=36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'room_id',
            sa.String(length=36),
            sa.ForeignKey('cdf_rooms.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'design_id',
            sa.String(length=36),
            sa.ForeignKey('spacecraft_designs.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'format',
            sa.Enum('PDF', 'JSON', 'BOTH', name='dossierformat'),
            nullable=False,
            server_default='BOTH',
        ),
        sa.Column(
            'status',
            sa.Enum('QUEUED', 'GENERATING', 'COMPLETED', 'FAILED', 'CANCELLED', name='dossierjobstatus'),
            nullable=False,
            server_default='QUEUED',
        ),
        sa.Column('progress_percent', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('report_id', sa.String(length=36), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_dossier_jobs_id', 'dossier_jobs', ['id'], unique=False)
    op.create_index('ix_dossier_jobs_mission_id', 'dossier_jobs', ['mission_id'], unique=False)
    op.create_index('ix_dossier_jobs_user_id', 'dossier_jobs', ['user_id'], unique=False)
    op.create_index('ix_dossier_jobs_room_id', 'dossier_jobs', ['room_id'], unique=False)
    op.create_index('ix_dossier_jobs_status', 'dossier_jobs', ['status'], unique=False)
    op.create_index('ix_dossier_jobs_report_id', 'dossier_jobs', ['report_id'], unique=False)

    # 2. Dossier Reports table
    op.create_table(
        'dossier_reports',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            'job_id',
            sa.String(length=36),
            sa.ForeignKey('dossier_jobs.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'mission_id',
            sa.String(length=36),
            sa.ForeignKey('missions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.String(length=36),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'room_id',
            sa.String(length=36),
            sa.ForeignKey('cdf_rooms.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'design_id',
            sa.String(length=36),
            sa.ForeignKey('spacecraft_designs.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('format', sa.String(length=16), nullable=False, server_default='BOTH'),
        sa.Column('pdf_path', sa.String(length=512), nullable=True),
        sa.Column('pdf_size_bytes', sa.Integer(), nullable=True),
        sa.Column('pdf_sha256', sa.String(length=64), nullable=True),
        sa.Column('json_path', sa.String(length=512), nullable=True),
        sa.Column('json_size_bytes', sa.Integer(), nullable=True),
        sa.Column('json_sha256', sa.String(length=64), nullable=True),
        sa.Column('schema_version', sa.String(length=32), nullable=False, server_default='1.0.0'),
        sa.Column('snapshot_data', sa.JSON(), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_dossier_reports_id', 'dossier_reports', ['id'], unique=False)
    op.create_index('ix_dossier_reports_mission_id', 'dossier_reports', ['mission_id'], unique=False)
    op.create_index('ix_dossier_reports_user_id', 'dossier_reports', ['user_id'], unique=False)
    op.create_index('ix_dossier_reports_job_id', 'dossier_reports', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_table('dossier_reports')
    op.drop_table('dossier_jobs')
