"""
Mission and Spacecraft Design Database Models
"""

import enum
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Float, Integer, Enum, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.base import UUIDModelMixin, TimestampModelMixin


class MissionTarget(str, enum.Enum):
    MOON = "MOON"
    MARS = "MARS"
    EUROPA = "EUROPA"
    TITAN = "TITAN"
    PSYCHE = "PSYCHE"
    VENUS = "VENUS"
    JUPITER = "JUPITER"


class MissionClass(str, enum.Enum):
    DISCOVERY = "DISCOVERY"        # Cost-capped, ~$500M
    NEW_FRONTIERS = "NEW_FRONTIERS"  # Mid-size, ~$1.0B
    FLAGSHIP = "FLAGSHIP"          # Strategic large, ~$3.2B+


class Mission(Base, UUIDModelMixin, TimestampModelMixin):
    """A top-level space exploration mission."""
    __tablename__ = "missions"

    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target: Mapped[MissionTarget] = mapped_column(Enum(MissionTarget), nullable=False)
    mission_class: Mapped[MissionClass] = mapped_column(
        Enum(MissionClass), nullable=False, default=MissionClass.DISCOVERY
    )

    # Engineering baseline constraints
    budget_cap_usd: Mapped[float] = mapped_column(
        Float, nullable=False, default=500_000_000.0
    )
    max_launch_mass_kg: Mapped[float] = mapped_column(
        Float, nullable=False, default=1500.0
    )
    min_delta_v_mps: Mapped[float] = mapped_column(
        Float, nullable=False, default=3800.0
    )
    min_power_margin_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=15.0
    )

    # Active spacecraft designs
    designs: Mapped[List["SpacecraftDesign"]] = relationship(
        "SpacecraftDesign",
        back_populates="mission",
        cascade="all, delete-orphan",
    )


class SpacecraftDesign(Base, UUIDModelMixin, TimestampModelMixin):
    """A specific versioned configuration of a spacecraft for a mission."""
    __tablename__ = "spacecraft_designs"

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("missions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="Baseline Spacecraft"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Component references (list of component UUIDs)
    component_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # Sized propellant mass (calculated or overridden)
    propellant_mass_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Aggregated SWaP-C results snapshot
    dry_mass_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    wet_mass_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    power_draw_w: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    power_generation_w: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    delta_v_mps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Feasibility status
    is_feasible: Mapped[bool] = mapped_column(default=False, nullable=False)
    violations: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )

    # Relationships
    mission: Mapped["Mission"] = relationship("Mission", back_populates="designs")
