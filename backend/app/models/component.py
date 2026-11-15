"""
Component and Subsystem Catalog Models
"""

import enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Float, Integer, Enum, JSON, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import UUIDModelMixin, TimestampModelMixin


class SubsystemType(str, enum.Enum):
    STRUCTURE = "STRUCTURE"
    POWER = "POWER"
    PROPULSION = "PROPULSION"
    TELECOM = "TELECOM"
    THERMAL = "THERMAL"
    SCIENCE = "SCIENCE"
    ADCS = "ADCS"  # Attitude Determination & Control System
    PAYLOAD_SUPPORT = "PAYLOAD_SUPPORT"


class VerificationStatus(str, enum.Enum):
    VERIFIED_AUTHORITATIVE = "VERIFIED_AUTHORITATIVE"
    DERIVED_FROM_FLIGHT_DATA = "DERIVED_FROM_FLIGHT_DATA"
    ESTIMATED = "ESTIMATED"
    UNVERIFIED = "UNVERIFIED"


class Component(Base, UUIDModelMixin, TimestampModelMixin):
    """
    Persistent component catalog item with flight heritage and provenance.
    """
    __tablename__ = "components"

    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    subsystem: Mapped[SubsystemType] = mapped_column(
        Enum(SubsystemType), index=True, nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Physical specs (SI Units: kg, W, $, s, N)
    mass_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    power_draw_w: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    power_generation_w: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Subsystem-specific attributes
    # For propulsion:
    isp_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thrust_newtons: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    propellant_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # For power:
    solar_area_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    solar_efficiency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    decay_rate_annual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # For telecom:
    antenna_diameter_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency_band: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tx_power_w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Provenance & NASA TechPort tracking
    trl: Mapped[int] = mapped_column(Integer, nullable=False, default=9)  # 1 to 9
    flight_heritage: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    techport_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_system: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    raw_source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus),
        nullable=False,
        default=VerificationStatus.VERIFIED_AUTHORITATIVE,
    )

    # Field-level provenance mapping: {field: {source_system, citation, url, status}}
    field_provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Flexible metadata
    specifications: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
