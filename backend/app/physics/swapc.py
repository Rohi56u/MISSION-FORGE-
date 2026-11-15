"""
Deterministic SWaP-C Aerospace Aggregator
Integrates Mass, Power, Propulsion, Telecom, and Cost into a unified
Systems Engineering analysis.
"""

from typing import List, Dict, Tuple
import math
from backend.app.schemas.swapc import (
    SWaPCAnalysisRequest,
    SWaPCAnalysisResponse,
    ComponentSpecSchema,
    ConstraintViolation,
)
from backend.app.physics.constants import (
    BODY_DISTANCES_AU,
    ASTRONOMICAL_UNIT_M,
    FREQUENCY_BANDS_HZ,
)
from backend.app.physics.propulsion import (
    tsiolkovsky_delta_v,
    propellant_mass_required,
    calculate_multithruster_effective_isp,
    calculate_staged_propulsion_systems,
    ThrusterOperatingSpec,
)
from backend.app.physics.power import solar_array_power, mmrtg_power_at_time
from backend.app.physics.telecom import (
    deep_space_link_budget,
    round_trip_light_time_seconds,
)
from backend.app.models.mission import MissionClass
from backend.app.models.component import SubsystemType


def estimate_transit_duration_years(target_name: str, distance_au: float) -> float:
    """
    Estimates nominal mission transit / cruise duration in years based on target
    astronomical distance (Hohmann or ballistic flight baselines).
    """
    target_clean = target_name.upper().strip()
    if target_clean in ("MOON", "EARTH"):
        return 0.1
    elif target_clean in ("VENUS", "MERCURY"):
        return 0.5
    elif target_clean == "MARS":
        return 0.7  # ~8.5 months nominal Hohmann transit
    elif target_clean in ("CERES", "PSYCHE"):
        return 3.5
    elif target_clean in ("JUPITER", "EUROPA", "GANYMEDE"):
        return 5.5  # Europa Clipper flight baseline (~5.5 yr)
    elif target_clean in ("SATURN", "TITAN", "ENCELADUS"):
        return 7.0  # Cassini flight baseline (~6.7 yr)
    elif target_clean in ("URANUS", "NEPTUNE", "PLUTO"):
        return 10.0
    else:
        return max(0.5, round(math.sqrt(abs(distance_au - 1.0) * 1.5), 1))


# Standard Launch Vehicle Selection & Cost Model
def estimate_launch_cost(wet_mass_kg: float) -> Tuple[float, str]:
    """
    Estimates launch vehicle procurement cost based on payload mass requirement.
    Falcon 9 / Heavy ($70M - $120M) vs Vulcan ($110M) vs SLS ($2.2B).
    """
    if wet_mass_kg <= 2500.0:
        return 70_000_000.0, "Medium Lift Launch Vehicle (e.g. Falcon 9)"
    elif wet_mass_kg <= 8000.0:
        return 120_000_000.0, "Heavy Lift Launch Vehicle (e.g. Falcon Heavy)"
    else:
        return 350_000_000.0, "Super Heavy Lift Vehicle"


def calculate_swapc(request: SWaPCAnalysisRequest) -> SWaPCAnalysisResponse:
    """
    Executes end-to-end aerospace SWaP-C aggregation and verifies engineering constraints.
    """
    # 1. Determine Distance & Mission Duration
    target_name = request.target.value.upper()
    distance_au = request.distance_au or BODY_DISTANCES_AU.get(target_name, 1.524)
    distance_m = distance_au * ASTRONOMICAL_UNIT_M
    if request.mission_duration_years is not None:
        mission_duration_years = request.mission_duration_years
    else:
        mission_duration_years = estimate_transit_duration_years(target_name, distance_au)

    # 2. Financial Caps based on Mission Class
    if request.custom_budget_cap_usd:
        budget_cap = request.custom_budget_cap_usd
    elif request.mission_class == MissionClass.DISCOVERY:
        budget_cap = 500_000_000.0
    elif request.mission_class == MissionClass.NEW_FRONTIERS:
        budget_cap = 1_000_000_000.0
    else:
        budget_cap = 3_200_000_000.0

    max_mass_limit = (
        request.custom_max_mass_kg
        or (1800.0 if request.mission_class == MissionClass.DISCOVERY else 4500.0)
    )

    # 3. Aggregate Component Metrics by Subsystem
    dry_mass = 0.0
    total_power_draw = 0.0
    total_power_gen = 0.0
    hardware_cost = 0.0

    mass_by_subsystem: Dict[str, float] = {}
    power_by_subsystem: Dict[str, float] = {}

    propulsion_components: List[ComponentSpecSchema] = []
    telecom_components: List[ComponentSpecSchema] = []

    for comp in request.components:
        sub_name = comp.subsystem.value
        dry_mass += comp.mass_kg
        total_power_draw += comp.power_draw_w
        hardware_cost += comp.cost_usd

        mass_by_subsystem[sub_name] = round(
            mass_by_subsystem.get(sub_name, 0.0) + comp.mass_kg, 2
        )
        power_by_subsystem[sub_name] = round(
            power_by_subsystem.get(sub_name, 0.0) + comp.power_draw_w, 2
        )

        # Power Generation Calculations
        if comp.solar_area_m2 and comp.solar_area_m2 > 0:
            gen_w = solar_array_power(
                distance_au=distance_au,
                area_m2=comp.solar_area_m2,
                efficiency=comp.solar_efficiency or 0.30,
            )
            total_power_gen += gen_w
        elif comp.is_radioisotope:
            # MMRTG generates continuous power independent of solar distance
            gen_w = mmrtg_power_at_time(
                p_bol_w=comp.power_generation_w or 110.0,
                time_years=mission_duration_years,
                annual_thermocouple_decay=comp.annual_decay_rate or 0.008,
            )
            total_power_gen += gen_w
        elif comp.power_generation_w > 0:
            # Baseline power generation at 1 AU scaled by 1/r^2
            scaled_w = comp.power_generation_w * ((1.0 / distance_au) ** 2)
            total_power_gen += scaled_w

        is_prop = (
            comp.subsystem == SubsystemType.PROPULSION
            or (comp.isp_seconds is not None and comp.isp_seconds > 0)
        )
        if is_prop:
            propulsion_components.append(comp)

        if comp.antenna_diameter_m and comp.antenna_diameter_m > 0:
            telecom_components.append(comp)

    # Base spacecraft avionics bus overhead if dry mass > 0
    if dry_mass > 0:
        base_avionics_power = 25.0  # 25W base computer/housekeeping
        total_power_draw += base_avionics_power
        power_by_subsystem["AVIONICS_BASE"] = base_avionics_power

    # 4. Propulsion & Propellant Sizing
    violations: List[ConstraintViolation] = []
    warnings: List[str] = []

    thruster_specs: List[ThrusterOperatingSpec] = []
    for c in propulsion_components:
        if c.isp_seconds is None or c.isp_seconds <= 0.0:
            raise ValueError(
                f"Propulsion component '{c.name}' must specify positive Isp (> 0 s)."
            )
        if c.thrust_newtons is None or c.thrust_newtons <= 0.0:
            raise ValueError(
                f"Multi-thruster calculation requires explicit thrust_newtons (> 0 N) "
                f"for thruster '{c.name}'. Arbitrary defaults (e.g. 1.0 N) are rejected."
            )
        thruster_specs.append(
            ThrusterOperatingSpec(
                thrust_newtons=float(c.thrust_newtons),
                isp_seconds=float(c.isp_seconds),
                name=c.name,
                is_active=c.is_active,
                maneuver_system=c.maneuver_system or "PRIMARY",
            )
        )

    # Evaluate separate propulsion systems per maneuver stage
    staged_propulsion = (
        calculate_staged_propulsion_systems(thruster_specs) if thruster_specs else {}
    )

    # Primary maneuver Delta-V effective Isp determination:
    primary_specs = [
        t for t in thruster_specs if t.maneuver_system == "PRIMARY" and t.is_active
    ]
    if primary_specs:
        effective_isp = calculate_multithruster_effective_isp(
            primary_specs, system_filter="PRIMARY"
        )
    elif any(t.is_active for t in thruster_specs):
        # Fall back to the first active stage if PRIMARY is not explicitly used
        first_stage = next(t.maneuver_system for t in thruster_specs if t.is_active)
        effective_isp = calculate_multithruster_effective_isp(
            [t for t in thruster_specs if t.maneuver_system == first_stage and t.is_active],
            system_filter=first_stage,
        )
    else:
        # No active propulsion components
        effective_isp = 315.0  # Reference baseline
        if request.required_delta_v_mps > 0:
            warnings.append(
                "No active propulsion system specified. "
                "Propellant sized using default 315 s chemical reference."
            )

    if request.propellant_mass_kg is not None:
        propellant_mass = request.propellant_mass_kg
    else:
        # Automatically size propellant to achieve required Delta-V
        propellant_mass = propellant_mass_required(
            isp_s=effective_isp,
            m_dry_kg=max(dry_mass, 1.0),
            delta_v_mps=request.required_delta_v_mps,
        )

    wet_mass = dry_mass + propellant_mass
    if dry_mass > 0.0 and wet_mass > dry_mass:
        available_delta_v = tsiolkovsky_delta_v(effective_isp, wet_mass, dry_mass)
    else:
        available_delta_v = 0.0
    delta_v_margin = available_delta_v - request.required_delta_v_mps

    # 5. Launch & Total Mission Cost
    launch_cost, _ = estimate_launch_cost(wet_mass)
    # 20% standard NASA project management and reserves
    mission_operations_and_reserves = (hardware_cost + launch_cost) * 0.20
    total_mission_cost = hardware_cost + launch_cost + mission_operations_and_reserves
    budget_margin = budget_cap - total_mission_cost

    # 6. Power Margin Analysis
    power_margin_w = total_power_gen - total_power_draw
    power_margin_pct = (
        (power_margin_w / total_power_draw * 100.0) if total_power_draw > 0 else 100.0
    )

    # 7. Telecom Link Budget
    downlink_margin_db = None
    if telecom_components:
        best_antenna = max(telecom_components, key=lambda c: c.antenna_diameter_m or 0.0)
        link = deep_space_link_budget(
            distance_m=distance_m,
            frequency_hz=best_antenna.frequency_hz or FREQUENCY_BANDS_HZ["X_BAND"],
            tx_power_w=best_antenna.tx_power_w or 20.0,
            tx_antenna_diameter_m=best_antenna.antenna_diameter_m or 1.5,
            data_rate_bps=10_000.0,
        )
        downlink_margin_db = link["link_margin_db"]

    rtlt_seconds = round_trip_light_time_seconds(distance_m)
    rtlt_minutes = int(rtlt_seconds // 60)
    rtlt_secs = int(rtlt_seconds % 60)
    rtlt_formatted = f"{rtlt_minutes}m {rtlt_secs}s"

    # 8. Constraint Verification & Anomaly Detection
    # Check Budget Cap
    if budget_margin < 0:
        violations.append(
            ConstraintViolation(
                constraint_type="BUDGET_CAP_EXCEEDED",
                severity="CRITICAL",
                message=(
                    f"Total cost (${total_mission_cost/1e6:.1f}M) exceeds "
                    f"{request.mission_class.value} budget cap of ${budget_cap/1e6:.1f}M."
                ),
                limit_value=budget_cap,
                actual_value=total_mission_cost,
                unit="USD",
                actionable_fix=(
                    "Downgrade expensive instruments or switch to higher Isp "
                    "propulsion to reduce launch vehicle class."
                ),
            )
        )

    # Check Launch Vehicle Fairing Mass
    if wet_mass > max_mass_limit:
        violations.append(
            ConstraintViolation(
                constraint_type="LAUNCH_MASS_EXCEEDED",
                severity="CRITICAL",
                message=(
                    f"Spacecraft wet mass ({wet_mass:.1f} kg) exceeds "
                    f"launch fairing limit ({max_mass_limit:.1f} kg)."
                ),
                limit_value=max_mass_limit,
                actual_value=wet_mass,
                unit="kg",
                actionable_fix=(
                    "Select lighter composite structures or upgrade to higher "
                    "Isp propulsion to reduce propellant load."
                ),
            )
        )

    # Check Power Deficit
    if power_margin_w < 0:
        violations.append(
            ConstraintViolation(
                constraint_type="POWER_DEFICIT",
                severity="CRITICAL",
                message=(
                    f"Power consumed ({total_power_draw:.1f} W) exceeds power "
                    f"generated ({total_power_gen:.1f} W) at {distance_au:.2f} AU."
                ),
                limit_value=total_power_draw,
                actual_value=total_power_gen,
                unit="W",
                actionable_fix=(
                    f"At {distance_au:.1f} AU solar irradiance drops significantly. "
                    "Add an MMRTG or increase solar array area."
                ),
            )
        )
    elif power_margin_pct < request.min_power_margin_percent:
        warnings.append(
            f"Power margin ({power_margin_pct:.1f}%) is below recommended margin "
            f"of {request.min_power_margin_percent:.1f}%."
        )

    # Check Delta-V Deficit (with floating-point precision tolerance)
    if delta_v_margin < -1e-5:
        violations.append(
            ConstraintViolation(
                constraint_type="DELTA_V_DEFICIT",
                severity="CRITICAL",
                message=(
                    f"Available Delta-V ({available_delta_v:.0f} m/s) is insufficient "
                    f"for target capture ({request.required_delta_v_mps:.0f} m/s)."
                ),
                limit_value=request.required_delta_v_mps,
                actual_value=available_delta_v,
                unit="m/s",
                actionable_fix=(
                    "Increase propellant tank capacity or select higher specific impulse thrusters."
                ),
            )
        )

    is_feasible = len(violations) == 0
    status = (
        "NOMINAL"
        if is_feasible and len(warnings) == 0
        else ("MARGINAL" if is_feasible else "INFEASIBLE")
    )

    return SWaPCAnalysisResponse(
        target=target_name,
        distance_au=round(distance_au, 3),
        mission_class=request.mission_class.value,
        dry_mass_kg=round(dry_mass, 2),
        propellant_mass_kg=round(propellant_mass, 2),
        wet_mass_kg=round(wet_mass, 2),
        mass_by_subsystem=mass_by_subsystem,
        total_power_draw_w=round(total_power_draw, 2),
        total_power_generated_w=round(total_power_gen, 2),
        power_margin_w=round(power_margin_w, 2),
        power_margin_percent=round(power_margin_pct, 1),
        power_by_subsystem=power_by_subsystem,
        available_delta_v_mps=round(available_delta_v, 1),
        required_delta_v_mps=round(request.required_delta_v_mps, 1),
        delta_v_margin_mps=round(delta_v_margin, 1),
        effective_isp_s=round(effective_isp, 1),
        propulsion_systems=staged_propulsion,
        mission_duration_years=round(mission_duration_years, 2),
        downlink_margin_db=(
            round(downlink_margin_db, 2) if downlink_margin_db is not None else None
        ),
        round_trip_light_time_seconds=round(rtlt_seconds, 2),
        rtlt_formatted=rtlt_formatted,
        hardware_cost_usd=round(hardware_cost, 2),
        launch_vehicle_cost_usd=round(launch_cost, 2),
        total_mission_cost_usd=round(total_mission_cost, 2),
        budget_cap_usd=round(budget_cap, 2),
        budget_margin_usd=round(budget_margin, 2),
        is_feasible=is_feasible,
        status=status,
        violations=violations,
        warnings=warnings,
    )
