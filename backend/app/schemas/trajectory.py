"""
Pydantic v2 Schemas for Astrodynamics & Porkchop Trajectory Analysis
Mission Forge — Phase 3
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.integrations.horizons.models import Vector3D
from backend.app.models.trajectory import PorkchopJobStatus


class LambertSolveRequest(BaseModel):
    """Request payload for direct two-body Lambert boundary-value solve."""
    model_config = ConfigDict(extra="forbid")

    r1_km: Vector3D = Field(..., description="Departure position vector in km")
    r2_km: Vector3D = Field(..., description="Arrival position vector in km")
    time_of_flight_s: float = Field(
        ..., gt=0.0, description="Transfer duration in seconds (must be > 0 s)"
    )
    mu_km3_s2: float = Field(
        default=132712440018.0,
        gt=0.0,
        description="Central gravitational parameter in km^3/s^2 (default: Sun)",
    )
    prograde: bool = Field(
        default=True,
        description="True for prograde transfer, False for retrograde",
    )
    transfer_angle_type: str = Field(
        default="auto",
        description="Transfer angle selection: 'auto', 'short' (<180 deg), or 'long' (>180 deg)",
    )
    max_iterations: int = Field(
        default=100,
        ge=5,
        le=1000,
        description="Maximum numerical iterations",
    )
    tolerance: float = Field(
        default=1e-7,
        gt=0.0,
        le=1e-3,
        description="Convergence residual tolerance",
    )

    @field_validator("transfer_angle_type")
    @classmethod
    def validate_transfer_type(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in ("auto", "short", "long"):
            raise ValueError("transfer_angle_type must be 'auto', 'short', or 'long'")
        return cleaned


class LambertSolveResponse(BaseModel):
    """Typed result of two-body Lambert solver."""
    v1_kms: Vector3D = Field(..., description="Departure velocity vector in km/s")
    v2_kms: Vector3D = Field(..., description="Arrival velocity vector in km/s")
    converged: bool = Field(..., description="Whether numerical solver converged")
    iterations: int = Field(..., description="Total iterations elapsed")
    residual: float = Field(
        ...,
        description=(
            "Final time-of-flight equation residual |F(z)| in km^1.5. "
            "Physical time-of-flight error in seconds is residual / sqrt(mu)."
        ),
    )
    semi_major_axis_km: float = Field(..., description="Transfer orbit semi-major axis in km")
    eccentricity: float = Field(..., description="Transfer orbit eccentricity")
    transfer_angle_deg: float = Field(..., description="Transfer angle in degrees")
    time_of_flight_s: float = Field(..., description="Time of flight in seconds")
    solution_branch: str = Field(..., description="Classification of transfer orbit branch")
    stumpff_z: float = Field(..., description="Universal variable root z")
    units: Dict[str, str] = Field(..., description="Physical units dictionary")


class PorkchopRequest(BaseModel):
    """Request payload for porkchop grid computation."""
    model_config = ConfigDict(extra="forbid")

    origin_body: str = Field(
        default="EARTH",
        min_length=1,
        max_length=64,
        description="Departure body (e.g. 'EARTH', '399', 'MARS')",
    )
    target_body: str = Field(
        default="MARS",
        min_length=1,
        max_length=64,
        description="Target destination body (e.g. 'MARS', '499', 'MOON', 'EUROPA')",
    )
    departure_start_date: str = Field(
        ...,
        description="Departure window start (YYYY-MM-DD)",
        examples=["2026-05-01"],
    )
    departure_end_date: str = Field(
        ...,
        description="Departure window end (YYYY-MM-DD)",
        examples=["2026-08-01"],
    )
    arrival_start_date: str = Field(
        ...,
        description="Arrival window start (YYYY-MM-DD)",
        examples=["2026-11-01"],
    )
    arrival_end_date: str = Field(
        ...,
        description="Arrival window end (YYYY-MM-DD)",
        examples=["2027-04-01"],
    )
    step_size_days: float = Field(
        default=2.0,
        gt=0.0,
        le=30.0,
        description="Grid resolution step size in days (e.g. 1.0, 2.0, 5.0)",
    )
    dep_parking_alt_km: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Optional departure circular parking orbit altitude in km (e.g. 200 km)",
    )
    arr_parking_alt_km: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Optional arrival circular parking orbit altitude in km (e.g. 300 km)",
    )
    prograde: bool = Field(
        default=True,
        description="Transfer direction (True for prograde, False for retrograde)",
    )

    @field_validator(
        "departure_start_date",
        "departure_end_date",
        "arrival_start_date",
        "arrival_end_date",
    )
    @classmethod
    def validate_iso_date(cls, v: str) -> str:
        cleaned = v.strip()[:10]
        try:
            datetime.strptime(cleaned, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Date '{v}' must be in YYYY-MM-DD format.") from exc
        return cleaned

    @model_validator(mode="after")
    def validate_dates_and_bodies(self) -> "PorkchopRequest":
        """Enforces physical date chronology and non-identical boundary bodies."""
        d_dep_s = datetime.strptime(self.departure_start_date, "%Y-%m-%d").date()
        d_dep_e = datetime.strptime(self.departure_end_date, "%Y-%m-%d").date()
        d_arr_s = datetime.strptime(self.arrival_start_date, "%Y-%m-%d").date()
        d_arr_e = datetime.strptime(self.arrival_end_date, "%Y-%m-%d").date()

        if d_dep_s > d_dep_e:
            raise ValueError("departure_start_date must be before or equal to departure_end_date.")
        if d_arr_s > d_arr_e:
            raise ValueError("arrival_start_date must be before or equal to arrival_end_date.")
        if d_dep_s >= d_arr_e:
            raise ValueError(
                "departure_start_date must be strictly before arrival_end_date "
                "(at least one positive time-of-flight cell is required)."
            )

        from backend.app.astrodynamics.porkchop import normalize_body_name
        try:
            norm_orig = normalize_body_name(self.origin_body)
            norm_target = normalize_body_name(self.target_body)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if norm_orig == norm_target:
            raise ValueError("Origin and target bodies cannot be identical.")

        if norm_orig in ("SUN", "10") or norm_target in ("SUN", "10"):
            raise ValueError(
                "The Sun (central gravitational body) cannot be an origin or target body "
                "for trajectory analysis."
            )

        if norm_orig in ("MOON", "EUROPA"):
            raise ValueError(
                f"Body '{norm_orig}' is a natural satellite and cannot be used as an independent "
                "departure origin without modeling multi-body planetary escape."
            )

        return self


class PorkchopJobCreateResponse(BaseModel):
    """Immediate acknowledgement returned upon job creation."""
    job_id: str
    status: PorkchopJobStatus
    created_at: datetime


class PorkchopJobStatusResponse(BaseModel):
    """Polling status and progress of a background porkchop computation job."""
    job_id: str
    status: PorkchopJobStatus
    progress_percent: float
    origin_body: str
    target_body: str
    departure_window: Dict[str, str]
    arrival_window: Dict[str, str]
    step_size_days: float
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class PorkchopResponse(BaseModel):
    """Complete structured porkchop grid dataset ready for 2D contour visualization."""
    job_id: Optional[str] = None
    origin_body: str
    target_body: str
    departure_dates: List[str]
    arrival_dates: List[str]
    step_size_days: float
    total_grid_points: int
    valid_cells_count: int
    c3_grid: List[List[Optional[float]]] = Field(
        ...,
        description=(
            "2D array of characteristic energy C3 in km^2/s^2, "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    vinf_dep_grid: List[List[Optional[float]]] = Field(
        ...,
        description=(
            "2D array of departure excess velocity in km/s, "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    vinf_arr_grid: List[List[Optional[float]]] = Field(
        ...,
        description=(
            "2D array of arrival excess velocity in km/s, "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    tof_days_grid: List[List[Optional[float]]] = Field(
        ...,
        description=(
            "2D array of time of flight in days, "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    dv_inj_grid: List[List[Optional[float]]] = Field(
        ...,
        description=(
            "2D array of departure injection Delta-V in km/s (or null), "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    dv_arr_grid: List[List[Optional[float]]] = Field(
        ...,
        description=(
            "2D array of arrival capture Delta-V in km/s (or null), "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    dv_total_grid: List[List[Optional[float]]] = Field(
        ...,
        description=(
            "2D array of total mission Delta-V in km/s (or null), "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    valid_mask: List[List[bool]] = Field(
        ...,
        description=(
            "2D boolean mask indicating converged/valid cells, "
            "indexed [arrival_idx][departure_idx]"
        ),
    )
    minima: Dict[str, Optional[Dict[str, Any]]]
    units: Dict[str, str]
    solver_diagnostics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Numerical solver convergence diagnostics and performance metrics",
    )
    provenance: Dict[str, Any]
