"""
Pydantic Models for JPL Horizons Ephemeris & Orbital Elements API
Authoritative data models for NASA/JPL Solar System Dynamics Horizons service.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.cache import CacheStatus


class HorizonsEphemType(str, Enum):
    VECTORS = "VECTORS"
    ELEMENTS = "ELEMENTS"
    OBSERVER = "OBSERVER"


class HorizonsRefPlane(str, Enum):
    FRAME = "FRAME"
    ECLIPTIC = "ECLIPTIC"


class HorizonsRefSystem(str, Enum):
    J2000 = "J2000"
    B1950 = "B1950"
    ICRF = "ICRF"


class HorizonsTimeScale(str, Enum):
    TDB = "TDB"
    UTC = "UTC"
    UT = "UT"


class HorizonsQueryRequest(BaseModel):
    """
    Validated request parameters for JPL Horizons ephemeris query.
    """
    model_config = ConfigDict(extra="forbid")

    target: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Target body ID or name (e.g. '399', '499', 'MARS', '301')",
        examples=["399", "499", "MARS"],
    )
    center: str = Field(
        default="500@0",
        min_length=1,
        max_length=64,
        description=(
            "Coordinate center: '500@0' (Solar System Barycenter), "
            "'500@10' (Sun), '500@399' (Geocenter)"
        ),
    )
    ephem_type: HorizonsEphemType = Field(
        default=HorizonsEphemType.VECTORS,
        description="Ephemeris product type: VECTORS or ELEMENTS",
    )
    start_time: str = Field(
        default="2026-01-01",
        description="Start time (e.g. '2026-01-01' or '2026-01-01 00:00')",
    )
    stop_time: str = Field(
        default="2026-01-02",
        description="Stop time (e.g. '2026-01-02' or '2026-01-02 00:00')",
    )
    step_size: str = Field(
        default="1d",
        description="Ephemeris time step (e.g. '1d', '6h', '30m')",
    )
    ref_plane: HorizonsRefPlane = Field(
        default=HorizonsRefPlane.FRAME,
        description="Reference plane: FRAME (ICRF) or ECLIPTIC",
    )
    ref_system: HorizonsRefSystem = Field(
        default=HorizonsRefSystem.J2000,
        description="Reference frame system: J2000, B1950, or ICRF",
    )
    time_scale: HorizonsTimeScale = Field(
        default=HorizonsTimeScale.TDB,
        description="Time scale: TDB (Barycentric Dynamical Time) or UTC",
    )

    @field_validator("target", "center", "start_time", "stop_time", "step_size")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field must not be empty or blank.")
        return cleaned

    @field_validator("start_time", "stop_time", "step_size")
    @classmethod
    def validate_time_and_step_safety(cls, v: str) -> str:
        cleaned = v.strip()
        for char in ("'", '"', ";", "\\", "\n", "\r", "\t", "<", ">", "{", "}", "$", "`"):
            if char in cleaned:
                raise ValueError(
                    f"Parameter contains invalid or unsafe character '{char}'. "
                    "Use standard calendar dates, Julian dates, or step specifiers."
                )
        return cleaned

    @field_validator("ephem_type")
    @classmethod
    def validate_ephemeris_type_supported(cls, v: HorizonsEphemType) -> HorizonsEphemType:
        if v not in (HorizonsEphemType.VECTORS, HorizonsEphemType.ELEMENTS):
            raise ValueError(
                f"Ephemeris type '{v.value}' is not supported. "
                "Supported types are VECTORS and ELEMENTS."
            )
        return v

    @field_validator("target", "center")
    @classmethod
    def validate_identifier_safety(cls, v: str) -> str:
        raw = v.strip()
        # If wrapped in symmetric matching quotes, strip outer wrapper
        if (raw.startswith("'") and raw.endswith("'") and len(raw) >= 2) or (
            raw.startswith('"') and raw.endswith('"') and len(raw) >= 2
        ):
            cleaned = raw[1:-1].strip()
        else:
            cleaned = raw

        if not cleaned:
            raise ValueError("Target or center identifier cannot be empty.")
        # Reject control characters, injection characters, or forbidden symbols
        for char in ("'", '"', ";", "\\", "\n", "\r", "\t", "<", ">", "{", "}"):
            if char in cleaned:
                raise ValueError(
                    f"Identifier contains invalid character '{char}'. "
                    "Use alphanumeric names, JPL numeric IDs, or standard designators."
                )
        return cleaned


class Vector3D(BaseModel):
    """3-dimensional Cartesian vector in SI-derived aerospace units (km or km/s)."""
    x: float = Field(..., description="X component in km or km/s")
    y: float = Field(..., description="Y component in km or km/s")
    z: float = Field(..., description="Z component in km or km/s")


class HorizonsVectorEntry(BaseModel):
    """State vector record for a specific epoch from JPL Horizons."""
    epoch_jd: float = Field(..., description="Julian Date (TDB)")
    calendar_date: str = Field(..., description="Human-readable calendar date (UTC/TDB)")
    position_km: Vector3D = Field(..., description="Position vector (km)")
    velocity_kms: Vector3D = Field(..., description="Velocity vector (km/s)")
    light_time_s: Optional[float] = Field(default=None, description="One-way light time in seconds")
    range_km: Optional[float] = Field(
        default=None, description="Distance from observer/center in km"
    )
    range_rate_kms: Optional[float] = Field(default=None, description="Range rate in km/s")


class HorizonsElementEntry(BaseModel):
    """Keplerian osculating orbital elements record from JPL Horizons."""
    epoch_jd: float = Field(..., description="Julian Date (TDB)")
    calendar_date: str = Field(..., description="Human-readable calendar date (UTC/TDB)")
    eccentricity: float = Field(..., description="Orbital eccentricity (e)")
    periapsis_dist_km: float = Field(..., description="Periapsis distance in km (q)")
    inclination_deg: float = Field(..., description="Orbital inclination in degrees (i)")
    longitude_asc_node_deg: float = Field(
        ..., description="Longitude of ascending node in degrees (node/OM)"
    )
    arg_perifocus_deg: float = Field(..., description="Argument of periapsis in degrees (peri/w)")
    mean_anomaly_deg: float = Field(..., description="Mean anomaly in degrees (MA)")
    true_anomaly_deg: Optional[float] = Field(
        default=None, description="True anomaly in degrees (TA)"
    )
    semi_major_axis_km: Optional[float] = Field(
        default=None, description="Semi-major axis in km (a)"
    )
    apoapsis_dist_km: Optional[float] = Field(
        default=None, description="Apoapsis distance in km (ad)"
    )
    orbital_period_s: Optional[float] = Field(
        default=None, description="Orbital period in seconds (PR)"
    )


class HorizonsTargetCandidate(BaseModel):
    """Candidate match when a Horizons target identifier matches multiple bodies."""
    target_id: str
    name: str
    designation: Optional[str] = None
    aliases: Optional[str] = None


class HorizonsQueryResponse(BaseModel):
    """Normalized typed response from JPL Horizons client."""
    target_id: str
    target_name: str
    center_id: str
    center_name: str
    ephem_type: HorizonsEphemType
    coordinate_frame: str = "ICRF / J2000"
    origin_center: str
    time_scale: str = "TDB"
    units: Dict[str, str] = Field(
        default_factory=lambda: {
            "position": "kilometers (km)",
            "velocity": "kilometers per second (km/s)",
            "angles": "degrees",
            "time": "TDB Julian Date / ISO calendar",
        }
    )
    vectors: List[HorizonsVectorEntry] = Field(default_factory=list)
    elements: List[HorizonsElementEntry] = Field(default_factory=list)
    raw_signature: Dict[str, Any] = Field(default_factory=dict)
    query_params: Dict[str, Any] = Field(default_factory=dict)
    source_url: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_status: CacheStatus = CacheStatus.LIVE
