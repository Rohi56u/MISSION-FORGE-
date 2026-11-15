"""
Trajectory Optimization & Porkchop Job Database Models
Mission Forge — Phase 3
"""

from datetime import datetime
import enum
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, Enum, Float, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import TimestampModelMixin, UUIDModelMixin


class PorkchopJobStatus(str, enum.Enum):
    """Lifecycle status of a porkchop grid analysis job."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PorkchopJob(Base, UUIDModelMixin, TimestampModelMixin):
    """
    Database model representing an asynchronous porkchop trajectory computation.
    Tracks state transitions, computation progress, input parameters, and full
    2D contour result grids with provenance metadata.
    """
    __tablename__ = "porkchop_jobs"

    status: Mapped[PorkchopJobStatus] = mapped_column(
        Enum(PorkchopJobStatus),
        nullable=False,
        default=PorkchopJobStatus.QUEUED,
        index=True,
    )
    progress_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    origin_body: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_body: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    departure_start: Mapped[str] = mapped_column(String(32), nullable=False)
    departure_end: Mapped[str] = mapped_column(String(32), nullable=False)
    arrival_start: Mapped[str] = mapped_column(String(32), nullable=False)
    arrival_end: Mapped[str] = mapped_column(String(32), nullable=False)
    step_size_days: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    parameters: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    results: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
