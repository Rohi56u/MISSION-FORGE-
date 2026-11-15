"""
Deterministic Propulsion Physics
Implements the Tsiolkovsky Rocket Equation, multi-thruster effective Isp,
propellant mass sizing, and chemical vs electric propulsion trade-offs.
"""

from dataclasses import dataclass
import math
from typing import Dict, Any, List, Sequence, Optional, Union
from backend.app.physics.constants import STANDARD_GRAVITY


@dataclass(frozen=True)
class ThrusterOperatingSpec:
    """
    Specification of an operating thruster for effective Isp calculations.

    Attributes:
        thrust_newtons: Operating thrust in Newtons (> 0).
        isp_seconds: Specific impulse in seconds (> 0).
        name: Name or component identifier.
        is_active: Whether thruster operates in this simultaneous maneuver.
        maneuver_system: Identifier for staged/isolated maneuvers (e.g. "PRIMARY", "RCS").
    """
    thrust_newtons: float
    isp_seconds: float
    name: str = "Thruster"
    is_active: bool = True
    maneuver_system: str = "PRIMARY"


def calculate_multithruster_effective_isp(
    thrusters: Sequence[Union[ThrusterOperatingSpec, tuple[float, float], Dict[str, Any]]],
    system_filter: Optional[str] = None,
) -> float:
    """
    Derives the effective specific impulse for multiple thrusters operating simultaneously.

    Physics Derivation:
        When n thrusters fire simultaneously:
          Total Thrust:          F_tot = sum_{i=1}^n F_i
          Mass Flow Rate:        m_dot_i = F_i / (g_0 * Isp_i)
          Total Mass Flow Rate:  m_dot_tot = sum_{i=1}^n m_dot_i
                                           = (1 / g_0) * sum_{i=1}^n (F_i / Isp_i)
          Effective Isp:         Isp_eff = F_tot / (g_0 * m_dot_tot)
                                         = sum(F_i) / sum(F_i / Isp_i)

    Explicit Assumptions & Scope:
      1. SIMULTANEOUS FIRING: All included thrusters fire concurrently during the maneuver.
      2. COMPATIBLE SYSTEMS: Thrusters must belong to the same operating maneuver stage.
         Do NOT combine attitude control (RCS) thrusters with main propulsion engines.
      3. ARITHMETIC MEANS ARE PHYSICALLY INVALID: An arithmetic mean of Isp values
         violates propellant mass conservation and can wildly overestimate efficiency.
      4. NO ARBITRARY DEFAULTS: Thrust cannot be defaulted to arbitrary values (e.g. 1.0 N).
         Missing or non-positive thrust or Isp values raise ValueError.

    Args:
        thrusters: Sequence of ThrusterOperatingSpec, (thrust, isp) tuples, or dicts.
        system_filter: If specified, only includes thrusters matching this maneuver_system.

    Returns:
        Effective specific impulse in seconds.

    Raises:
        ValueError: If thruster list is empty, no thrusters are active, or any
            thrust/Isp value is non-positive, NaN, or missing.
    """
    if not thrusters:
        raise ValueError("No thrusters provided for multi-thruster calculation.")

    normalized: List[ThrusterOperatingSpec] = []
    for t in thrusters:
        if isinstance(t, ThrusterOperatingSpec):
            spec = t
        elif isinstance(t, tuple) and len(t) == 2:
            try:
                thrust_val = float(t[0])
                isp_val = float(t[1])
            except (TypeError, ValueError) as err:
                raise ValueError(
                    f"Tuple elements for (thrust, isp) must be numeric, got {t}: {err}"
                )
            spec = ThrusterOperatingSpec(thrust_newtons=thrust_val, isp_seconds=isp_val)
        elif isinstance(t, dict):
            thrust = t.get("thrust_newtons")
            isp = t.get("isp_seconds")
            if thrust is None or isp is None:
                raise ValueError(
                    f"Thruster dict must contain 'thrust_newtons' and 'isp_seconds', got {t}."
                )
            try:
                thrust_f = float(thrust)
                isp_f = float(isp)
            except (TypeError, ValueError) as err:
                raise ValueError(
                    f"Thruster dict values must be numeric, got thrust={thrust}, isp={isp}: {err}"
                )
            spec = ThrusterOperatingSpec(
                thrust_newtons=thrust_f,
                isp_seconds=isp_f,
                name=str(t.get("name", "Thruster")),
                is_active=bool(t.get("is_active", True)),
                maneuver_system=str(t.get("maneuver_system", "PRIMARY")),
            )
        else:
            raise ValueError(f"Unsupported thruster specification format: {type(t)}.")

        # Apply system filter if requested
        if system_filter is not None and spec.maneuver_system != system_filter:
            continue

        if spec.is_active:
            normalized.append(spec)

    if not normalized:
        raise ValueError("No active thrusters available for effective Isp calculation.")

    # Validation: all active thrusters must have strictly positive, finite numbers
    for t in normalized:
        if (
            not isinstance(t.thrust_newtons, (int, float))
            or not math.isfinite(t.thrust_newtons)
            or t.thrust_newtons <= 0.0
        ):
            raise ValueError(
                f"Thruster '{t.name}' has invalid thrust: {t.thrust_newtons} N. "
                "Thrust must be strictly positive and finite (> 0 N); "
                "arbitrary defaults are rejected."
            )
        if (
            not isinstance(t.isp_seconds, (int, float))
            or not math.isfinite(t.isp_seconds)
            or t.isp_seconds <= 0.0
        ):
            raise ValueError(
                f"Thruster '{t.name}' has invalid Isp: {t.isp_seconds} s. "
                "Specific impulse must be strictly positive and finite (> 0 s)."
            )

    # Incompatible maneuver systems must NOT be collapsed into one misleading Isp
    distinct_systems = {t.maneuver_system for t in normalized}
    if system_filter is None and len(distinct_systems) > 1:
        raise ValueError(
            f"Cannot calculate single effective Isp across distinct maneuver systems: "
            f"{sorted(distinct_systems)}. Thrusters operating in separate mission phases "
            "(e.g. PRIMARY vs RCS) must not be collapsed into a single misleading effective "
            "Isp. Specify 'system_filter' or use 'calculate_staged_propulsion_systems'."
        )

    # Single-thruster equivalence: exactly matches its own Isp
    if len(normalized) == 1:
        return float(normalized[0].isp_seconds)

    # Multi-thruster simultaneous derivation: F_tot / sum(F_i / Isp_i)
    total_thrust = sum(t.thrust_newtons for t in normalized)
    total_flow_denominator = sum(t.thrust_newtons / t.isp_seconds for t in normalized)

    if total_flow_denominator <= 0.0:
        raise ValueError("Total mass flow denominator must be strictly positive.")

    return float(total_thrust / total_flow_denominator)


def calculate_staged_propulsion_systems(
    thrusters: Sequence[Union[ThrusterOperatingSpec, tuple[float, float], Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """
    Evaluates propulsion systems separately by maneuver system identifier
    (e.g. PRIMARY, RCS, DESCENT, APOGEE_INSERTION).

    Ensures that separate propulsion systems used in different maneuvers
    are not collapsed into one misleading effective Isp.

    Returns:
        Dictionary mapping maneuver_system -> {
            "effective_isp_s": float,
            "total_thrust_n": float,
            "thruster_count": int,
            "thrusters": List[str],
        }
    """
    # Group by maneuver system
    grouped: Dict[str, List[Union[ThrusterOperatingSpec, tuple[float, float], Dict[str, Any]]]] = {}
    for t in thrusters:
        if isinstance(t, ThrusterOperatingSpec):
            sys_id = t.maneuver_system
        elif isinstance(t, dict):
            sys_id = str(t.get("maneuver_system", "PRIMARY"))
        else:
            sys_id = "PRIMARY"
        grouped.setdefault(sys_id, []).append(t)

    results: Dict[str, Dict[str, Any]] = {}
    for sys_id, stage_thrusters in grouped.items():
        try:
            isp_eff = calculate_multithruster_effective_isp(stage_thrusters, system_filter=sys_id)
            total_f = sum(
                t.thrust_newtons for t in stage_thrusters
                if isinstance(t, ThrusterOperatingSpec) and t.is_active
            )
            count = sum(
                1 for t in stage_thrusters
                if isinstance(t, ThrusterOperatingSpec) and t.is_active
            )
            results[sys_id] = {
                "effective_isp_s": round(isp_eff, 2),
                "total_thrust_n": round(total_f, 3),
                "thruster_count": count,
            }
        except ValueError as e:
            results[sys_id] = {
                "error": str(e),
                "thruster_count": len(stage_thrusters),
            }

    return results


def tsiolkovsky_delta_v(isp_s: float, m_wet_kg: float, m_dry_kg: float) -> float:
    """
    Calculates ideal velocity change (Delta-V) using Tsiolkovsky's Rocket Equation.

    Formula:
        Delta-V = Isp * g_0 * ln(m_wet / m_dry)

    Args:
        isp_s: Specific impulse in seconds (> 0).
        m_wet_kg: Initial wet mass (including propellant) in kilograms (> 0).
        m_dry_kg: Final dry mass (empty of propellant) in kilograms (> 0).

    Returns:
        Ideal velocity increment Delta-V in meters per second (m/s).

    Raises:
        ValueError: If inputs are non-positive or m_wet < m_dry.
    """
    if isp_s <= 0.0:
        raise ValueError(f"Specific impulse must be strictly positive, got {isp_s} s.")
    if m_dry_kg <= 0.0:
        raise ValueError(f"Dry mass must be strictly positive, got {m_dry_kg} kg.")
    if m_wet_kg < m_dry_kg:
        raise ValueError(
            f"Wet mass ({m_wet_kg} kg) cannot be less than dry mass ({m_dry_kg} kg)."
        )

    # If no propellant, Delta-V is exactly zero
    if m_wet_kg == m_dry_kg:
        return 0.0

    mass_ratio = m_wet_kg / m_dry_kg
    return float(isp_s * STANDARD_GRAVITY * math.log(mass_ratio))


def propellant_mass_required(isp_s: float, m_dry_kg: float, delta_v_mps: float) -> float:
    """
    Calculates propellant mass required to achieve a specified Delta-V.

    Formula:
        m_prop = m_dry * (exp(Delta-V / (Isp * g_0)) - 1)

    Args:
        isp_s: Specific impulse in seconds (> 0).
        m_dry_kg: Spacecraft dry mass in kilograms (> 0).
        delta_v_mps: Desired velocity change in m/s (>= 0).

    Returns:
        Required propellant mass in kilograms.

    Raises:
        ValueError: If isp_s <= 0, m_dry_kg <= 0, or delta_v_mps < 0.
    """
    if isp_s <= 0.0:
        raise ValueError(f"Specific impulse must be strictly positive, got {isp_s} s.")
    if m_dry_kg <= 0.0:
        raise ValueError(f"Dry mass must be strictly positive, got {m_dry_kg} kg.")
    if delta_v_mps < 0.0:
        raise ValueError(f"Delta-V must be non-negative, got {delta_v_mps} m/s.")

    if delta_v_mps == 0.0:
        return 0.0

    exponent = delta_v_mps / (isp_s * STANDARD_GRAVITY)
    return float(m_dry_kg * (math.exp(exponent) - 1.0))


def electric_propulsion_power(thrust_n: float, isp_s: float, efficiency: float = 0.65) -> float:
    """
    Calculates electrical beam power required for an electrostatic / ion thruster.

    Formula:
        P_beam = (Thrust * Isp * g_0) / (2 * efficiency)

    Args:
        thrust_n: Thrust in Newtons (> 0).
        isp_s: Specific impulse in seconds (> 0).
        efficiency: Thruster electrical-to-kinetic efficiency (0 < efficiency <= 1.0).

    Returns:
        Electrical input power in Watts.
    """
    if thrust_n <= 0.0:
        raise ValueError(f"Thrust must be positive, got {thrust_n} N.")
    if isp_s <= 0.0:
        raise ValueError(f"Isp must be positive, got {isp_s} s.")
    if not (0.0 < efficiency <= 1.0):
        raise ValueError(f"Efficiency must be in (0, 1], got {efficiency}.")

    exhaust_velocity = isp_s * STANDARD_GRAVITY
    return float((thrust_n * exhaust_velocity) / (2.0 * efficiency))


def compare_propulsion_technologies(m_dry_kg: float, delta_v_mps: float) -> Dict[str, Any]:
    """
    Provides a systems engineering trade-off comparison between Chemical Bipropellant
    and Hall-Effect / Gridded Ion Electric Propulsion.
    """
    if m_dry_kg <= 0.0:
        raise ValueError(f"Dry mass must be strictly positive, got {m_dry_kg} kg.")
    if delta_v_mps < 0.0:
        raise ValueError(f"Delta-V must be non-negative, got {delta_v_mps} m/s.")

    # Chemical baseline: Hydrazine / NTO (Isp = 315 s)
    chem_isp = 315.0
    chem_prop = propellant_mass_required(chem_isp, m_dry_kg, delta_v_mps)
    chem_wet = m_dry_kg + chem_prop

    # Electric baseline: NEXT-C Ion Thruster (Isp = 3500 s, Thrust = 0.236 N, P_elec = 2500 W)
    ep_isp = 3500.0
    ep_prop = propellant_mass_required(ep_isp, m_dry_kg, delta_v_mps)
    ep_wet = m_dry_kg + ep_prop
    ep_power = electric_propulsion_power(thrust_n=0.236, isp_s=ep_isp, efficiency=0.68)

    mass_saved_kg = chem_prop - ep_prop
    mass_reduction_percent = (mass_saved_kg / chem_prop * 100.0) if chem_prop > 0 else 0.0

    return {
        "m_dry_kg": m_dry_kg,
        "delta_v_mps": delta_v_mps,
        "chemical_bipropellant": {
            "isp_seconds": chem_isp,
            "propellant_mass_kg": round(chem_prop, 2),
            "wet_mass_kg": round(chem_wet, 2),
            "mass_fraction": round(chem_prop / chem_wet, 4) if chem_wet > 0 else 0.0,
            "burn_type": "IMPULSIVE_FAST",
            "electrical_power_w": 25.0,
        },
        "electric_ion_propulsion": {
            "isp_seconds": ep_isp,
            "propellant_mass_kg": round(ep_prop, 2),
            "wet_mass_kg": round(ep_wet, 2),
            "mass_fraction": round(ep_prop / ep_wet, 4) if ep_wet > 0 else 0.0,
            "burn_type": "CONTINUOUS_LOW_THRUST",
            "electrical_power_w": round(ep_power, 1),
        },
        "trade_off_analysis": {
            "propellant_mass_saved_kg": round(mass_saved_kg, 2),
            "propellant_reduction_percent": round(mass_reduction_percent, 1),
            "key_friction": (
                "Electric propulsion reduces propellant mass by ~90%, "
                "but demands continuous kW-class power and long multi-month burn durations."
            ),
        },
    }
