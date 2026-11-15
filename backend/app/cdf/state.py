"""
Authoritative Mission Design State & Deterministic SWaP-C Recomputation
Mission Forge — Phase 4
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.models.component import SubsystemType
from backend.app.models.mission import MissionClass, MissionTarget
from backend.app.physics.swapc import calculate_swapc
from backend.app.physics.telecom import deep_space_link_budget
from backend.app.schemas.swapc import ComponentSpecSchema, SWaPCAnalysisRequest
from backend.app.physics.constants import ASTRONOMICAL_UNIT_M

logger = logging.getLogger(__name__)


class ConstraintAlert(BaseModel):
    """Actionable alert generated when engineering margins or constraints are breached."""
    alert_code: str
    severity: str  # NOMINAL, CAUTION, WARNING, CRITICAL
    subsystem: str
    message: str
    actionable_guidance: str
    threshold: float
    current_value: float
    unit: str


class CalculatedBudgets(BaseModel):
    """Authoritative recalculated engineering budgets and margins."""
    dry_mass_kg: float = 0.0
    wet_mass_kg: float = 0.0
    mass_margin_percent: float = 0.0

    total_power_draw_w: float = 0.0
    total_power_generated_w: float = 0.0
    power_margin_percent: float = 0.0

    available_delta_v_mps: float = 0.0
    delta_v_margin_percent: float = 0.0

    total_cost_usd: float = 0.0
    cost_margin_percent: float = 0.0

    link_margin_db: Optional[float] = None
    is_feasible: bool = False
    violations: List[Dict[str, Any]] = Field(default_factory=list)


class SystemConstraints(BaseModel):
    """System-level constraints governed by the Lead Systems Architect."""
    target: str = "MARS"
    mission_class: str = "DISCOVERY"
    budget_cap_usd: float = Field(default=500_000_000.0, gt=0.0)
    max_launch_mass_kg: float = Field(default=1500.0, gt=0.0)
    min_delta_v_mps: float = Field(default=3800.0, ge=0.0)
    min_power_margin_percent: float = Field(default=15.0, ge=0.0)


class PropulsionAndPowerState(BaseModel):
    """Propulsion and power parameters governed by the Propulsion & Power Officer."""
    propellant_mass_kg: float = Field(default=0.0, ge=0.0)
    components: List[Dict[str, Any]] = Field(default_factory=list)


class SciencePayloadState(BaseModel):
    """Payload and scientific instrument configuration governed by the Science Officer."""
    components: List[Dict[str, Any]] = Field(default_factory=list)


class FlightDynamicsAndCommsState(BaseModel):
    """Trajectory inputs and comms assumptions governed by Flight Dynamics & Comms Officer."""
    required_delta_v_mps: float = Field(default=3800.0, ge=0.0)
    departure_window: Dict[str, str] = Field(
        default_factory=lambda: {"start": "2026-06-01", "end": "2026-07-01"}
    )
    arrival_window: Dict[str, str] = Field(
        default_factory=lambda: {"start": "2027-01-01", "end": "2027-02-01"}
    )
    parking_orbit_alt_km: float = Field(default=200.0, ge=0.0)
    distance_au: float = Field(default=1.524, gt=0.0)  # Mars average
    tx_power_w: float = Field(default=20.0, ge=0.0)
    antenna_diameter_m: float = Field(default=1.5, gt=0.0)
    carrier_frequency_hz: float = Field(default=8.4e9, gt=0.0)  # X-band (8.4 GHz)
    components: List[Dict[str, Any]] = Field(default_factory=list)


class CDFAuthoritativeState(BaseModel):
    """Authoritative, versioned mission-design state maintained across CDF participants."""
    room_id: str
    mission_id: str
    version: int = 1
    system_constraints: SystemConstraints = Field(default_factory=SystemConstraints)
    propulsion_and_power: PropulsionAndPowerState = Field(default_factory=PropulsionAndPowerState)
    science_payload: SciencePayloadState = Field(default_factory=SciencePayloadState)
    flight_dynamics_and_comms: FlightDynamicsAndCommsState = Field(
        default_factory=FlightDynamicsAndCommsState
    )
    calculated_budgets: CalculatedBudgets = Field(default_factory=CalculatedBudgets)
    provenance_map: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    constraint_alerts: List[ConstraintAlert] = Field(default_factory=list)


def initialize_default_cdf_state(
    room_id: str,
    mission_id: str,
    target: str = "MARS",
    mission_class: str = "DISCOVERY",
    budget_cap_usd: float = 500_000_000.0,
    max_launch_mass_kg: float = 1500.0,
    min_delta_v_mps: float = 3800.0,
    min_power_margin_percent: float = 15.0,
) -> CDFAuthoritativeState:
    """Creates a fresh authoritative CDF mission design state."""
    state = CDFAuthoritativeState(
        room_id=room_id,
        mission_id=mission_id,
        version=1,
        system_constraints=SystemConstraints(
            target=target,
            mission_class=mission_class,
            budget_cap_usd=budget_cap_usd,
            max_launch_mass_kg=max_launch_mass_kg,
            min_delta_v_mps=min_delta_v_mps,
            min_power_margin_percent=min_power_margin_percent,
        ),
        flight_dynamics_and_comms=FlightDynamicsAndCommsState(
            required_delta_v_mps=min_delta_v_mps,
        ),
    )
    return recalculate_authoritative_state(state)


def recalculate_authoritative_state(state: CDFAuthoritativeState) -> CDFAuthoritativeState:
    """
    Deterministically computes SWaP-C, link budgets, margins, and constraint alerts
    based on the current aggregated components and parameters in the state.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    # 1. Gather all components from propulsion/power, science, and comms
    all_raw_components: List[Dict[str, Any]] = []
    all_raw_components.extend(state.propulsion_and_power.components)
    all_raw_components.extend(state.science_payload.components)
    all_raw_components.extend(state.flight_dynamics_and_comms.components)

    subsystem_mapping = {
        "SCIENCE_PAYLOAD": SubsystemType.SCIENCE,
        "ELECTRICAL_POWER": SubsystemType.POWER,
        "COMMUNICATIONS": SubsystemType.TELECOM,
        "COMMS": SubsystemType.TELECOM,
        "PROPULSION_POWER": SubsystemType.PROPULSION,
    }
    typed_components: List[ComponentSpecSchema] = []
    for c in all_raw_components:
        c_copy = dict(c)
        sub = c_copy.get("subsystem")
        if isinstance(sub, str):
            sub_upper = sub.upper()
            if sub_upper in subsystem_mapping:
                c_copy["subsystem"] = subsystem_mapping[sub_upper]
            elif sub_upper in SubsystemType.__members__:
                c_copy["subsystem"] = SubsystemType[sub_upper]
        if "isp_s" in c_copy and "isp_seconds" not in c_copy:
            c_copy["isp_seconds"] = c_copy.pop("isp_s")
        if "thrust_n" in c_copy and "thrust_newtons" not in c_copy:
            c_copy["thrust_newtons"] = c_copy.pop("thrust_n")
        try:
            typed_components.append(ComponentSpecSchema(**c_copy))
        except Exception as e:
            logger.warning("Could not parse component into ComponentSpecSchema: %s", e)

    # Resolve mission target and class
    try:
        t_enum = MissionTarget(state.system_constraints.target)
    except Exception:
        t_enum = MissionTarget.MARS

    try:
        c_enum = MissionClass(state.system_constraints.mission_class)
    except Exception:
        c_enum = MissionClass.DISCOVERY

    # 2. Run deterministic SWaP-C calculation
    req_delta_v = state.flight_dynamics_and_comms.required_delta_v_mps
    swapc_req = SWaPCAnalysisRequest(
        target=t_enum,
        mission_class=c_enum,
        components=typed_components,
        propellant_mass_kg=state.propulsion_and_power.propellant_mass_kg,
        required_delta_v_mps=req_delta_v,
        custom_budget_cap_usd=state.system_constraints.budget_cap_usd,
        custom_max_mass_kg=state.system_constraints.max_launch_mass_kg,
        min_power_margin_percent=state.system_constraints.min_power_margin_percent,
    )
    swapc_res = calculate_swapc(swapc_req)

    # 3. Compute engineering margins
    max_mass = state.system_constraints.max_launch_mass_kg
    mass_margin_pct = (
        ((max_mass - swapc_res.wet_mass_kg) / max_mass) * 100.0 if max_mass > 0 else 0.0
    )

    power_margin_pct = swapc_res.power_margin_percent

    dv_margin_pct = (
        ((swapc_res.available_delta_v_mps - req_delta_v) / req_delta_v) * 100.0
        if req_delta_v > 0
        else 0.0
    )

    budget_cap = state.system_constraints.budget_cap_usd
    cost_margin_pct = (
        ((budget_cap - swapc_res.total_mission_cost_usd) / budget_cap) * 100.0
        if budget_cap > 0
        else 0.0
    )

    # 4. Deep-Space Link Budget calculation
    link_margin_db: Optional[float] = None
    dist_au = state.flight_dynamics_and_comms.distance_au
    dist_m = dist_au * ASTRONOMICAL_UNIT_M
    tx_pwr = state.flight_dynamics_and_comms.tx_power_w
    ant_diam = state.flight_dynamics_and_comms.antenna_diameter_m
    freq_hz = state.flight_dynamics_and_comms.carrier_frequency_hz

    if dist_m > 0 and tx_pwr > 0 and ant_diam > 0 and freq_hz > 0:
        try:
            link_res = deep_space_link_budget(
                distance_m=dist_m,
                frequency_hz=freq_hz,
                tx_power_w=tx_pwr,
                tx_antenna_diameter_m=ant_diam,
            )
            link_margin_db = link_res.get("link_margin_db")
        except Exception:
            link_margin_db = None

    # 5. Generate Actionable Constraint Alerts
    alerts: List[ConstraintAlert] = []

    # Mass constraint check
    if swapc_res.wet_mass_kg > max_mass:
        diff_mass = swapc_res.wet_mass_kg - max_mass
        alerts.append(
            ConstraintAlert(
                alert_code="MASS_BUDGET_EXCEEDED",
                severity="CRITICAL",
                subsystem="STRUCTURE_MASS",
                message=(
                    f"Wet mass ({swapc_res.wet_mass_kg:.1f} kg) exceeds launch limit "
                    f"({max_mass:.1f} kg) by {diff_mass:.1f} kg."
                ),
                actionable_guidance=(
                    "Reduce science payload mass or optimize propulsion propellant load."
                ),
                threshold=max_mass,
                current_value=swapc_res.wet_mass_kg,
                unit="kg",
            )
        )
    elif mass_margin_pct < 5.0:
        alerts.append(
            ConstraintAlert(
                alert_code="MASS_MARGIN_LOW",
                severity="CAUTION",
                subsystem="STRUCTURE_MASS",
                message=f"Mass margin is only {mass_margin_pct:.1f}% (below standard 5% buffer).",
                actionable_guidance="Review non-critical payloads before design freeze.",
                threshold=5.0,
                current_value=mass_margin_pct,
                unit="%",
            )
        )

    # Power margin check
    min_power_margin = state.system_constraints.min_power_margin_percent
    if power_margin_pct < 0.0:
        diff_pwr = swapc_res.total_power_draw_w - swapc_res.total_power_generated_w
        alerts.append(
            ConstraintAlert(
                alert_code="POWER_DEFICIT",
                severity="CRITICAL",
                subsystem="ELECTRICAL_POWER",
                message=(
                    f"Power gen ({swapc_res.total_power_generated_w:.1f} W) cannot support "
                    f"power draw ({swapc_res.total_power_draw_w:.1f} W). Deficit: {diff_pwr:.1f} W."
                ),
                actionable_guidance="Add solar array capacity or reduce payload duty cycle.",
                threshold=0.0,
                current_value=power_margin_pct,
                unit="%",
            )
        )
    elif power_margin_pct < min_power_margin:
        alerts.append(
            ConstraintAlert(
                alert_code="POWER_MARGIN_VIOLATION",
                severity="WARNING",
                subsystem="ELECTRICAL_POWER",
                message=(
                    f"Power margin ({power_margin_pct:.1f}%) below minimum required "
                    f"({min_power_margin:.1f}%)."
                ),
                actionable_guidance="Resize solar array area or review battery storage.",
                threshold=min_power_margin,
                current_value=power_margin_pct,
                unit="%",
            )
        )

    # Delta-V check
    if swapc_res.available_delta_v_mps < req_delta_v:
        diff_dv = req_delta_v - swapc_res.available_delta_v_mps
        alerts.append(
            ConstraintAlert(
                alert_code="DELTA_V_SHORTFALL",
                severity="CRITICAL",
                subsystem="PROPULSION",
                message=(
                    f"Available Delta-V ({swapc_res.available_delta_v_mps:.1f} m/s) below required "
                    f"({req_delta_v:.1f} m/s). Shortfall: {diff_dv:.1f} m/s."
                ),
                actionable_guidance="Increase propellant mass or upgrade thruster Isp.",
                threshold=req_delta_v,
                current_value=swapc_res.available_delta_v_mps,
                unit="m/s",
            )
        )

    # Budget cost check
    if swapc_res.total_mission_cost_usd > budget_cap:
        alerts.append(
            ConstraintAlert(
                alert_code="BUDGET_CAP_EXCEEDED",
                severity="WARNING",
                subsystem="SYSTEM_MANAGEMENT",
                message=(
                    f"Total cost (${swapc_res.total_mission_cost_usd/1e6:.2f}M) exceeds "
                    f"budget cap (${budget_cap/1e6:.2f}M)."
                ),
                actionable_guidance="Descope instruments or choose higher TRL COTS parts.",
                threshold=budget_cap,
                current_value=swapc_res.total_mission_cost_usd,
                unit="USD",
            )
        )

    # Telecom Link margin check
    if link_margin_db is not None:
        if link_margin_db < 0.0:
            alerts.append(
                ConstraintAlert(
                    alert_code="LINK_MARGIN_NEGATIVE",
                    severity="CRITICAL",
                    subsystem="COMMUNICATIONS",
                    message=(
                        f"Downlink margin is negative ({link_margin_db:.2f} dB) "
                        f"at {dist_au:.3f} AU."
                    ),
                    actionable_guidance="Increase RF transmit power or antenna diameter.",
                    threshold=0.0,
                    current_value=link_margin_db,
                    unit="dB",
                )
            )
        elif link_margin_db < 3.0:
            alerts.append(
                ConstraintAlert(
                    alert_code="LINK_MARGIN_LOW",
                    severity="CAUTION",
                    subsystem="COMMUNICATIONS",
                    message=(
                        f"Downlink margin is low ({link_margin_db:.2f} dB, "
                        "recommended >= 3 dB)."
                    ),
                    actionable_guidance="Verify RF pointing losses and modulation coding margin.",
                    threshold=3.0,
                    current_value=link_margin_db,
                    unit="dB",
                )
            )

    # 6. Update calculated budgets
    state.calculated_budgets = CalculatedBudgets(
        dry_mass_kg=round(swapc_res.dry_mass_kg, 2),
        wet_mass_kg=round(swapc_res.wet_mass_kg, 2),
        mass_margin_percent=round(mass_margin_pct, 2),
        total_power_draw_w=round(swapc_res.total_power_draw_w, 2),
        total_power_generated_w=round(swapc_res.total_power_generated_w, 2),
        power_margin_percent=round(power_margin_pct, 2),
        available_delta_v_mps=round(swapc_res.available_delta_v_mps, 2),
        delta_v_margin_percent=round(dv_margin_pct, 2),
        total_cost_usd=round(swapc_res.total_mission_cost_usd, 2),
        cost_margin_percent=round(cost_margin_pct, 2),
        link_margin_db=round(link_margin_db, 2) if link_margin_db is not None else None,
        is_feasible=swapc_res.is_feasible and (link_margin_db is None or link_margin_db >= 0.0),
        violations=[v.model_dump() for v in swapc_res.violations],
    )
    state.constraint_alerts = alerts

    # Update provenance for calculated values
    state.provenance_map["calculated_budgets"] = {
        "source_type": "CALCULATED",
        "source": "SWAPC_AND_TELECOM_DETERMINISTIC_ENGINE",
        "updated_at": now_iso,
    }

    return state


def apply_mutation_to_state(
    current_state: CDFAuthoritativeState,
    mutation_category: str,
    patch_data: Dict[str, Any],
    actor_role: str,
) -> CDFAuthoritativeState:
    """
    Applies a validated mutation patch to the authoritative design state,
    updates provenance records, bumps the version number, and runs
    deterministic recomputation of all engineering budgets and alerts.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    new_state = current_state.model_copy(deep=True)

    if mutation_category == "SYSTEM_CONSTRAINTS":
        c_data = new_state.system_constraints.model_dump()
        for k, v in patch_data.items():
            if k in c_data and v is not None:
                c_data[k] = v
                new_state.provenance_map[f"system_constraints.{k}"] = {
                    "source_type": "USER_INPUT",
                    "updated_by_role": actor_role,
                    "updated_at": now_iso,
                    "source": "CDF_SYSTEM_ARCHITECT_CONSOLE",
                }
        new_state.system_constraints = SystemConstraints(**c_data)

    elif mutation_category == "PROPULSION_POWER":
        p_data = new_state.propulsion_and_power.model_dump()
        if "propellant_mass_kg" in patch_data and patch_data["propellant_mass_kg"] is not None:
            p_data["propellant_mass_kg"] = float(patch_data["propellant_mass_kg"])
            new_state.provenance_map["propulsion_and_power.propellant_mass_kg"] = {
                "source_type": "USER_INPUT",
                "updated_by_role": actor_role,
                "updated_at": now_iso,
                "source": "CDF_PROPULSION_OFFICER_CONSOLE",
            }
        if "components" in patch_data and isinstance(patch_data["components"], list):
            p_data["components"] = patch_data["components"]
            new_state.provenance_map["propulsion_and_power.components"] = {
                "source_type": "USER_INPUT",
                "updated_by_role": actor_role,
                "updated_at": now_iso,
                "source": "CDF_PROPULSION_OFFICER_CONSOLE",
            }
        new_state.propulsion_and_power = PropulsionAndPowerState(**p_data)

    elif mutation_category == "SCIENCE_PAYLOAD":
        s_data = new_state.science_payload.model_dump()
        if "components" in patch_data and isinstance(patch_data["components"], list):
            s_data["components"] = patch_data["components"]
            new_state.provenance_map["science_payload.components"] = {
                "source_type": "USER_INPUT",
                "updated_by_role": actor_role,
                "updated_at": now_iso,
                "source": "CDF_SCIENCE_OFFICER_CONSOLE",
            }
        new_state.science_payload = SciencePayloadState(**s_data)

    elif mutation_category == "FLIGHT_DYNAMICS_COMMS":
        f_data = new_state.flight_dynamics_and_comms.model_dump()
        for k, v in patch_data.items():
            if k in f_data and v is not None:
                f_data[k] = v
                new_state.provenance_map[f"flight_dynamics_and_comms.{k}"] = {
                    "source_type": "USER_INPUT",
                    "updated_by_role": actor_role,
                    "updated_at": now_iso,
                    "source": "CDF_FLIGHT_DYNAMICS_CONSOLE",
                }
        new_state.flight_dynamics_and_comms = FlightDynamicsAndCommsState(**f_data)

    # Bump authoritative version
    new_state.version = current_state.version + 1

    # Deterministically recalculate all SWaP-C budgets, margins, and alerts
    return recalculate_authoritative_state(new_state)
