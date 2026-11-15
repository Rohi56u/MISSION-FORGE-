"""
SQLAlchemy Model for NASA TechPort Research & Technology Projects
Persists official NASA TechPort project records and associated TRL milestones.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, JSON, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import UUIDModelMixin, TimestampModelMixin


class TechPortProject(Base, UUIDModelMixin, TimestampModelMixin):
    """
    Persisted record of an official NASA TechPort technology development project.
    Distinguished from hardware flight components: TechPort captures programmatics,
    TRL progressions, lead centers, and technology taxonomy.
    """
    __tablename__ = "techport_projects"

    techport_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    benefits: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lead_organization: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    program: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Technology Readiness Levels recorded in TechPort
    trl_begin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trl_current: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trl_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    last_updated_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    canonical_url: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
