"""
Concurrent Design Facility (CDF) Database Models
Mission Forge — Phase 4
"""

import enum
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Enum,
    JSON,
    ForeignKey,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.base import UUIDModelMixin, TimestampModelMixin
from backend.app.models.mission import Mission
from backend.app.models.auth import User


class CDFRole(str, enum.Enum):
    """The four official roles in the Concurrent Design Facility."""
    LEAD_SYSTEMS_ARCHITECT = "LEAD_SYSTEMS_ARCHITECT"
    PROPULSION_POWER_OFFICER = "PROPULSION_POWER_OFFICER"
    SCIENCE_OFFICER = "SCIENCE_OFFICER"
    FLIGHT_DYNAMICS_COMMS_OFFICER = "FLIGHT_DYNAMICS_COMMS_OFFICER"


class CDFRoomStatus(str, enum.Enum):
    """Lifecycle status of a CDF Room."""
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    ARCHIVED = "ARCHIVED"


class CDFRoom(Base, UUIDModelMixin, TimestampModelMixin):
    """Authoritative Collaborative Mission Design Room."""
    __tablename__ = "cdf_rooms"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("missions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    creator_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[CDFRoomStatus] = mapped_column(
        Enum(CDFRoomStatus),
        default=CDFRoomStatus.ACTIVE,
        nullable=False,
    )
    max_participants: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    mission: Mapped[Mission] = relationship("Mission")
    participants: Mapped[List["CDFRoomParticipant"]] = relationship(
        "CDFRoomParticipant", back_populates="room", cascade="all, delete-orphan"
    )
    revisions: Mapped[List["CDFDesignRevision"]] = relationship(
        "CDFDesignRevision",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="CDFDesignRevision.version.asc()",
    )
    events: Mapped[List["CDFEvent"]] = relationship(
        "CDFEvent",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="CDFEvent.created_at.asc()",
    )


class CDFRoomParticipant(Base, UUIDModelMixin):
    """Participant membership and role assignment in a CDF Room."""
    __tablename__ = "cdf_room_participants"

    room_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cdf_rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[CDFRole] = mapped_column(
        Enum(CDFRole),
        nullable=False,
    )
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("room_id", "role", name="uq_room_role"),
        UniqueConstraint("room_id", "user_id", name="uq_room_user"),
    )

    # Relationships
    room: Mapped[CDFRoom] = relationship("CDFRoom", back_populates="participants")
    user: Mapped[User] = relationship("User")


class CDFDesignRevision(Base, UUIDModelMixin):
    """Immutable snapshot of authoritative mission design state at a specific version."""
    __tablename__ = "cdf_revisions"

    room_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cdf_rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_role: Mapped[str] = mapped_column(String(64), nullable=False)
    mutation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    patch_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    state_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    swapc_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("room_id", "version", name="uq_room_revision_version"),
    )

    room: Mapped[CDFRoom] = relationship("CDFRoom", back_populates="revisions")


class CDFEvent(Base, UUIDModelMixin):
    """Ordered event stream for audit trail, chat, constraint alerts, and replay."""
    __tablename__ = "cdf_events"

    room_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cdf_rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    room: Mapped[CDFRoom] = relationship("CDFRoom", back_populates="events")
