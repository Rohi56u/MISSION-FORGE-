"""
Pydantic v2 Schemas for SWaP-C and Aerospace Calculations
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from backend.app.models.component import SubsystemType
from backend.app.models.mission import MissionTarget, MissionClass


class ComponentSpecSchema(BaseModel):
    """Specification of an individual spacecraft component for SWaP-C analysis."""
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=128)
    subsystem: SubsystemType
    mass_kg: float = Field(..., ge=0.0, description="Component dry mass in kg")
    power_draw_w: float = Field(
        default=0.0, ge=0.0, description="Electrical power consumed in W"
    )
    power_generation_w: float = Field(
        default=0.0, ge=0.0, description="Power generated at 1 AU in W"
    )
    cost_usd: float = Field(
        default=0.0, ge=0.0, description="Subsystem procurement/manufacturing cost in USD"
    )

    # Optional propulsion attributes
    isp_seconds: Optional[float] = Field(default=None, gt=0.0)
    thrust_newtons: Optional[float] = Field(default=None, gt=0.0)
    maneuver_system: str = Field(
        default="PRIMARY",
        max_length=32,
        description="Maneuver stage / system (e.g. PRIMARY, RCS, DESCENT)",
    )
    is_active: bool = Field(default=True, description="Whether active in this evaluation")

    # Optional solar attributes
    solar_area_m2: Optional[float] = Field(default=None, gt=0.0)
    solar_efficiency: Optional[float] = Field(default=0.30, gt=0.0, le=1.0)

    # Optional radioisotope attributes
    is_radioisotope: bool = False
    annual_decay_rate: Optional[float] = Field(default=0.008, ge=0.0, lt=1.0)

    # Optional telecom attributes
    antenna_diameter_m: Optional[float] = Field(default=None, gt=0.0)
    tx_power_w: Optional[float] = Field(default=None, gt=0.0)
    frequency_hz: Optional[float] = Field(default=8.425e9, gt=0.0)


class ConstraintViolation(BaseModel):
    """A specific aerospace engineering constraint violation."""
    constraint_type: str = Field(
        ..., description="e.g., BUDGET_CAP, LAUNCH_MASS, POWER_DEFICIT, DELTA_V"
    )
    severity: str = Field(..., description="CAUTION, WARNING, CRITICAL")
    message: str
    limit_value: float
    actual_value: float
    unit: str
    actionable_fix: str


class SWaPCAnalysisRequest(BaseModel):
    """Input payload to evaluate spacecraft SWaP-C systems balance."""
    target: MissionTarget = MissionTarget.MARS
    mission_class: MissionClass = MissionClass.DISCOVERY
    distance_au: Optional[float] = Field(default=None, gt=0.0)

    # Components list
    components: List[ComponentSpecSchema] = Field(default_factory=list)

    # Sized propellant or auto-calculate based on required Delta-V
    propellant_mass_kg: Optional[float] = Field(default=None, ge=0.0)
    required_delta_v_mps: float = Field(default=3800.0, ge=0.0)
    mission_duration_years: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Mission elapsed duration for degradation models (years). "
            "If None, estimated from target."
        ),
    )

    # Overrides for mission constraints
    custom_budget_cap_usd: Optional[float] = Field(default=None, gt=0.0)
    custom_max_mass_kg: Optional[float] = Field(default=None, gt=0.0)
    min_power_margin_percent: float = Field(default=15.0, ge=0.0)


class SWaPCAnalysisResponse(BaseModel):
    """Complete aggregated SWaP-C evaluation result."""
    target: str
    distance_au: float
    mission_class: str

    # Mass budget (kg)
    dry_mass_kg: float
    propellant_mass_kg: float
    wet_mass_kg: float
    mass_by_subsystem: Dict[str, float]

    # Power budget (W)
    total_power_draw_w: float
    total_power_generated_w: float
    power_margin_w: float
    power_margin_percent: float
    power_by_subsystem: Dict[str, float]

    # Propulsion & Delta-V
    available_delta_v_mps: float
    required_delta_v_mps: float
    delta_v_margin_mps: float
    effective_isp_s: float
    propulsion_systems: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Separate propulsion systems evaluated per maneuver stage"
    )
    mission_duration_years: float = Field(
        default=1.0, description="Assumed mission transit / elapsed duration in years"
    )

    # Telecom Link Summary
    downlink_margin_db: Optional[float] = None
    round_trip_light_time_seconds: float
    rtlt_formatted: str

    # Financial Cost ($)
    hardware_cost_usd: float
    launch_vehicle_cost_usd: float
    total_mission_cost_usd: float
    budget_cap_usd: float
    budget_margin_usd: float

    # Feasibility verdict
    is_feasible: bool
    status: str  # NOMINAL, MARGINAL, INFEASIBLE
    violations: List[ConstraintViolation]
    warnings: List[str]
