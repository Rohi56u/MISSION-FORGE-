"""
FDIR Database Models
Mission Forge — Phase 5
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    Boolean,
    JSON,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import UUIDModelMixin


class FDIRFindingLog(Base, UUIDModelMixin):
    """
    Persistent audit trail of deterministic FDIR anomaly detections,
    acknowledgements, and triage guidance.
    """
    __tablename__ = "fdir_findings"

    room_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("cdf_rooms.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    mission_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    affected_subsystem: Mapped[str] = mapped_column(String(64), nullable=False)
    input_evidence: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    thresholds: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_status: Mapped[str] = mapped_column(String(32), nullable=False)
    triage_guidance: Mapped[str] = mapped_column(Text, nullable=False)

    # Acknowledgement status
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
