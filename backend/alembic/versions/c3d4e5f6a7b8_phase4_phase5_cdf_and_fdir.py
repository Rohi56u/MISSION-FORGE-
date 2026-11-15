"""phase4_phase5_cdf_and_fdir

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-14 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=128), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_id', 'users', ['id'], unique=False)

    # 2. CDF Rooms table
    op.create_table(
        'cdf_rooms',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('mission_id', sa.String(length=36), sa.ForeignKey('missions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('creator_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'LOCKED', 'ARCHIVED', name='cdfroomstatus'),
            nullable=False,
            server_default='ACTIVE',
        ),
        sa.Column('max_participants', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('current_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_cdf_rooms_id', 'cdf_rooms', ['id'], unique=False)
    op.create_index('ix_cdf_rooms_mission_id', 'cdf_rooms', ['mission_id'], unique=False)

    # 3. CDF Room Participants table
    op.create_table(
        'cdf_room_participants',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('room_id', sa.String(length=36), sa.ForeignKey('cdf_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column(
            'role',
            sa.Enum(
                'LEAD_SYSTEMS_ARCHITECT',
                'PROPULSION_POWER_OFFICER',
                'SCIENCE_OFFICER',
                'FLIGHT_DYNAMICS_COMMS_OFFICER',
                name='cdfrole',
            ),
            nullable=False,
        ),
        sa.Column('is_connected', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('room_id', 'role', name='uq_room_role'),
        sa.UniqueConstraint('room_id', 'user_id', name='uq_room_user'),
    )
    op.create_index('ix_cdf_room_participants_id', 'cdf_room_participants', ['id'], unique=False)
    op.create_index('ix_cdf_room_participants_room_id', 'cdf_room_participants', ['room_id'], unique=False)
    op.create_index('ix_cdf_room_participants_user_id', 'cdf_room_participants', ['user_id'], unique=False)

    # 4. CDF Revisions table
    op.create_table(
        'cdf_revisions',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('room_id', sa.String(length=36), sa.ForeignKey('cdf_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=False),
        sa.Column('author_role', sa.String(length=64), nullable=False),
        sa.Column('mutation_type', sa.String(length=64), nullable=False),
        sa.Column('patch_data', sa.JSON(), nullable=False),
        sa.Column('state_snapshot', sa.JSON(), nullable=False),
        sa.Column('swapc_snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('room_id', 'version', name='uq_room_revision_version'),
    )
    op.create_index('ix_cdf_revisions_id', 'cdf_revisions', ['id'], unique=False)
    op.create_index('ix_cdf_revisions_room_id', 'cdf_revisions', ['room_id'], unique=False)
    op.create_index('ix_cdf_revisions_version', 'cdf_revisions', ['version'], unique=False)

    # 5. CDF Events table
    op.create_table(
        'cdf_events',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('room_id', sa.String(length=36), sa.ForeignKey('cdf_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('actor_role', sa.String(length=64), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_cdf_events_id', 'cdf_events', ['id'], unique=False)
    op.create_index('ix_cdf_events_room_id', 'cdf_events', ['room_id'], unique=False)
    op.create_index('ix_cdf_events_event_type', 'cdf_events', ['event_type'], unique=False)

    # 6. FDIR Findings table
    op.create_table(
        'fdir_findings',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('room_id', sa.String(length=36), sa.ForeignKey('cdf_rooms.id', ondelete='CASCADE'), nullable=True),
        sa.Column('mission_id', sa.String(length=36), nullable=True),
        sa.Column('rule_id', sa.String(length=64), nullable=False),
        sa.Column('rule_version', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('affected_subsystem', sa.String(length=64), nullable=False),
        sa.Column('input_evidence', sa.JSON(), nullable=False),
        sa.Column('thresholds', sa.JSON(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('confidence_status', sa.String(length=32), nullable=False),
        sa.Column('triage_guidance', sa.Text(), nullable=False),
        sa.Column('acknowledged', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('acknowledged_by', sa.String(length=36), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_fdir_findings_id', 'fdir_findings', ['id'], unique=False)
    op.create_index('ix_fdir_findings_room_id', 'fdir_findings', ['room_id'], unique=False)
    op.create_index('ix_fdir_findings_mission_id', 'fdir_findings', ['mission_id'], unique=False)
    op.create_index('ix_fdir_findings_rule_id', 'fdir_findings', ['rule_id'], unique=False)
    op.create_index('ix_fdir_findings_severity', 'fdir_findings', ['severity'], unique=False)


def downgrade() -> None:
    op.drop_table('fdir_findings')
    op.drop_table('cdf_events')
    op.drop_table('cdf_revisions')
    op.drop_table('cdf_room_participants')
    op.drop_table('cdf_rooms')
    op.drop_table('users')
