"""
Mission Concept Dossier & Report Database Models
Mission Forge — Phase 6
"""

from datetime import datetime
import enum
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    Float,
    Integer,
    Enum,
    JSON,
    ForeignKey,
    Text,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import UUIDModelMixin, TimestampModelMixin


class DossierReportStatus(str, enum.Enum):
    """Lifecycle state of an asynchronous dossier generation job."""
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DossierFormat(str, enum.Enum):
    """Supported export formats for mission dossiers."""
    PDF = "PDF"
    JSON = "JSON"
    BOTH = "BOTH"


class DossierJob(Base, UUIDModelMixin, TimestampModelMixin):
    """
    Tracks state, progress, and execution metadata for long-running
    asynchronous mission dossier compilation and rendering jobs.
    """
    __tablename__ = "dossier_jobs"

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("missions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    room_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("cdf_rooms.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    design_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("spacecraft_designs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    format: Mapped[DossierFormat] = mapped_column(
        Enum(DossierFormat),
        nullable=False,
        default=DossierFormat.BOTH,
    )
    status: Mapped[DossierReportStatus] = mapped_column(
        Enum(DossierReportStatus),
        nullable=False,
        default=DossierReportStatus.QUEUED,
        index=True,
    )
    progress_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    report_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DossierReport(Base, UUIDModelMixin, TimestampModelMixin):
    """
    Authoritative, immutable mission dossier artifact record.
    Stores complete frozen snapshot data, file references, SHA-256 checksums,
    and schema versioning to guarantee mathematical reproducibility.
    """
    __tablename__ = "dossier_reports"

    job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("dossier_jobs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("missions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    room_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("cdf_rooms.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    design_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("spacecraft_designs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    format: Mapped[str] = mapped_column(
        String(16), nullable=False, default="BOTH"
    )
    pdf_path: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    pdf_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    pdf_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    json_path: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    json_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    json_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    schema_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1.0.0"
    )
    snapshot_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    page_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
