"""
Ephemeris-Driven Porkchop Trajectory Analysis Engine
Mission Forge — Phase 3 Astrodynamics Core

Physical Models & Assumptions:
1. Heliocentric Interplanetary Transfers (e.g. Earth -> Mars, Earth -> Europa):
   - Central body: Sun (mu_sun = 1.32712440018e11 km^3/s^2).
   - Reference frame: ICRF / J2000 Equatorial (REF_PLANE='FRAME'). Coordinate center: Sun (500@10).
   - Ephemerides: Official JPL Horizons state vectors at departure and arrival epochs.
   - Departure excess velocity: v_inf,dep = v_transfer,dep - v_origin(t_dep).
   - Characteristic energy: C3 = |v_inf,dep|^2 (km^2/s^2).
   - Arrival excess velocity: v_inf,arr = v_transfer,arr - v_target(t_arr).
   - Departure injection Delta-V (from circular parking orbit r_park = R_body + h_park):
     Delta-V_inj = sqrt(v_inf,dep^2 + 2*mu_body/r_park) - sqrt(mu_body/r_park).
   - Target capture Delta-V (into circular parking orbit):
     Delta-V_cap = sqrt(v_inf,arr^2 + 2*mu_target/r_target_park) - sqrt(mu_target/r_target_park).
   - Total Delta-V = Delta-V_inj + Delta-V_cap ONLY when parking orbit parameters are specified.
     Otherwise injection/capture Delta-Vs remain uncalculated and excess velocities are reported.
   - Earth-to-Europa Limitations: Sun-centered two-body Lambert transfer computes the heliocentric
     interplanetary transfer arc and excess velocity relative to Europa's heliocentric orbit.
     Europa is a moon of Jupiter orbiting at ~670,900 km. Jovian multi-body capture, Jovian orbit
     insertion, and Europa orbit insertion require 3-body/4-body Jovian gravitational dynamics
     and are NOT modeled in a two-body heliocentric Lambert solve.

2. Geocentric Lunar Transfers (Earth -> Moon):
   - Central body: Earth (mu_earth = 398600.4418 km^3/s^2, R_earth = 6378.137 km).
   - Reference frame: Geocentric ICRF / J2000. Coordinate center: Geocenter (500@399).
   - Moon state vectors relative to Earth retrieved from JPL Horizons (target: 301).
   - Spacecraft departure from Earth parking orbit (default 200 km altitude).
   - Trans-Lunar Injection (TLI): Delta-V_tli = |v1| - sqrt(mu_earth / r_park).
   - Lunar arrival excess velocity: v_inf,arr = v2 - v_moon(t_arr).
   - Lunar Orbit Insertion (LOI): Delta-V_loi = sqrt(v_inf,arr^2 + 2*mu_moon/r_lunar_park)
     - sqrt(mu_moon/r_lunar_park).
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.app.astrodynamics.lambert import solve_lambert
from backend.app.core.cache import CacheStatus
from backend.app.integrations.horizons import (
    HorizonsClient,
    HorizonsEphemType,
    HorizonsQueryRequest,
    HorizonsQueryResponse,
    HorizonsRefPlane,
    HorizonsRefSystem,
    HorizonsTimeScale,
    horizons_client,
)
from backend.app.integrations.horizons.models import Vector3D

logger = logging.getLogger(__name__)

# Fixed English month abbreviations for locale-independent Horizons date parsing
_MONTH_NAMES = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


# Standard Astrodynamic Body Parameters (IAU / NASA Planetary Fact Sheets)
@dataclass(frozen=True)
class CelestialBodyInfo:
    """Astrodynamic physical constants and Horizons identifiers for a celestial body."""
    name: str
    horizons_id: str
    mu_km3_s2: float
    equatorial_radius_km: float
    is_moon_of: Optional[str] = None


BODY_REGISTRY: Dict[str, CelestialBodyInfo] = {
    "SUN": CelestialBodyInfo(
        name="Sun",
        horizons_id="10",
        mu_km3_s2=1.32712440018e11,
        equatorial_radius_km=696340.0,
    ),
    "EARTH": CelestialBodyInfo(
        name="Earth",
        horizons_id="399",
        mu_km3_s2=398600.4418,
        equatorial_radius_km=6378.137,
    ),
    "MARS": CelestialBodyInfo(
        name="Mars",
        horizons_id="499",
        mu_km3_s2=42828.375214,
        equatorial_radius_km=3389.5,
    ),
    "MOON": CelestialBodyInfo(
        name="Moon",
        horizons_id="301",
        mu_km3_s2=4902.800066,
        equatorial_radius_km=1737.4,
        is_moon_of="EARTH",
    ),
    "VENUS": CelestialBodyInfo(
        name="Venus",
        horizons_id="299",
        mu_km3_s2=324858.592,
        equatorial_radius_km=6051.8,
    ),
    "JUPITER": CelestialBodyInfo(
        name="Jupiter",
        horizons_id="599",
        mu_km3_s2=1.26686534e8,
        equatorial_radius_km=69911.0,
    ),
    "EUROPA": CelestialBodyInfo(
        name="Europa",
        horizons_id="502",
        mu_km3_s2=3202.72,
        equatorial_radius_km=1560.8,
        is_moon_of="JUPITER",
    ),
}

# Aliases for flexible input normalization
BODY_ALIASES: Dict[str, str] = {
    "EARTH": "EARTH",
    "399": "EARTH",
    "3": "EARTH",
    "MARS": "MARS",
    "499": "MARS",
    "4": "MARS",
    "MOON": "MOON",
    "301": "MOON",
    "LUNA": "MOON",
    "EUROPA": "EUROPA",
    "502": "EUROPA",
    "JUPITER": "JUPITER",
    "599": "JUPITER",
    "5": "JUPITER",
    "VENUS": "VENUS",
    "299": "VENUS",
    "2": "VENUS",
    "SUN": "SUN",
    "10": "SUN",
}


def normalize_body_name(body_input: str) -> str:
    """Normalizes body input to uppercase standard registry key."""
    cleaned = body_input.strip().upper()
    if cleaned in BODY_ALIASES:
        return BODY_ALIASES[cleaned]
    if cleaned in BODY_REGISTRY:
        return cleaned
    raise ValueError(
        f"Unsupported celestial body '{body_input}'. "
        f"Supported bodies: {list(BODY_REGISTRY.keys())}"
    )


def compute_hyperbolic_burn_delta_v(
    v_inf: float,
    mu_body: float,
    body_radius_km: float,
    parking_orbit_alt_km: float,
) -> float:
    """
    Computes tangential impulsive velocity increment Delta-V to/from a circular
    parking orbit of altitude h_park:
    Delta-V = sqrt(v_inf^2 + 2*mu/r_park) - sqrt(mu/r_park).
    """
    r_park = body_radius_km + parking_orbit_alt_km
    if r_park <= 0.0 or mu_body <= 0.0:
        return float("nan")
    v_circ = math.sqrt(mu_body / r_park)
    v_peri = math.sqrt(v_inf**2 + 2.0 * mu_body / r_park)
    return v_peri - v_circ


@dataclass
class PorkchopMinima:
    """Minimum trajectory metric record."""
    metric_name: str
    value: float
    departure_date: str
    arrival_date: str
    time_of_flight_days: float
    units: str


@dataclass
class EphemerisState:
    """Position and velocity state vector at a specific epoch."""
    epoch_jd: float
    calendar_date: str
    position_km: Vector3D
    velocity_kms: Vector3D


class PorkchopGenerator:
    """
    Ephemeris-driven porkchop analysis generator.
    Queries JPL Horizons for accurate planetary/lunar states, computes
    zero-revolution Lambert transfers across a departure-arrival date mesh,
    and returns structured grids ready for 2D contour plotting.
    """

    def __init__(
        self,
        client: Optional[HorizonsClient] = None,
        max_grid_points: int = 10000,
    ) -> None:
        self.horizons = client or horizons_client
        self.max_grid_points = max_grid_points

    def _generate_date_range(
        self,
        start_date_str: str,
        end_date_str: str,
        step_days: float,
    ) -> List[date]:
        """Generates list of dates from start_date to end_date with step_days."""
        try:
            d_start = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
            d_end = datetime.strptime(end_date_str[:10], "%Y-%m-%d").date()
        except Exception as exc:
            raise ValueError(f"Invalid date format: must be YYYY-MM-DD. Error: {exc}") from exc

        if d_start > d_end:
            raise ValueError(
                f"Start date ({d_start}) cannot be after end date ({d_end})."
            )

        step_int = max(1, int(round(step_days)))
        dates: List[date] = []
        curr = d_start
        while curr <= d_end:
            dates.append(curr)
            curr += timedelta(days=step_int)

        return dates

    async def _fetch_body_ephemerides(
        self,
        body_key: str,
        dates: List[date],
        center: str,
        ref_plane: HorizonsRefPlane = HorizonsRefPlane.FRAME,
    ) -> Tuple[Dict[str, EphemerisState], HorizonsQueryResponse]:
        """
        Fetches Cartesian state vectors from JPL Horizons for a body across a date range.
        Returns a tuple of (states_by_date dictionary, raw HorizonsQueryResponse).
        """
        body_info = BODY_REGISTRY[body_key]
        start_str = dates[0].strftime("%Y-%m-%d")

        # Step size in days
        step_days = max(1, (dates[1] - dates[0]).days) if len(dates) > 1 else 1
        step_str = f"{step_days}d"

        # Ensure stop_time extends past the last requested date by step_days so
        # Horizons output inclusive range guarantees coverage of dates[-1]
        stop_date = dates[-1] + timedelta(days=step_days)
        stop_str = stop_date.strftime("%Y-%m-%d")

        req = HorizonsQueryRequest(
            target=body_info.horizons_id,
            center=center,
            ephem_type=HorizonsEphemType.VECTORS,
            start_time=start_str,
            stop_time=stop_str,
            step_size=step_str,
            ref_plane=ref_plane,
            ref_system=HorizonsRefSystem.J2000,
            time_scale=HorizonsTimeScale.TDB,
        )

        resp = await self.horizons.query(req, allow_stale=True)
        if not resp.vectors:
            raise ValueError(
                f"No ephemeris vectors returned by JPL Horizons for body '{body_key}' "
                f"(ID: {body_info.horizons_id}) between {start_str} and {stop_str}."
            )
        states_by_date: Dict[str, EphemerisState] = {}

        for vec in resp.vectors:
            cal_sub = vec.calendar_date
            for d in dates:
                d_str_iso = f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
                d_str_mon = f"{d.year:04d}-{_MONTH_NAMES[d.month]}-{d.day:02d}"
                if d_str_iso in cal_sub or d_str_mon in cal_sub:
                    states_by_date[d_str_iso] = EphemerisState(
                        epoch_jd=vec.epoch_jd,
                        calendar_date=vec.calendar_date,
                        position_km=vec.position_km,
                        velocity_kms=vec.velocity_kms,
                    )
                    break

        # Fallback: if Horizons date matching missed, map linearly by index
        if len(states_by_date) < len(dates) and len(resp.vectors) >= len(dates):
            for i, d in enumerate(dates):
                d_key = f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
                if d_key not in states_by_date and i < len(resp.vectors):
                    vec = resp.vectors[i]
                    states_by_date[d_key] = EphemerisState(
                        epoch_jd=vec.epoch_jd,
                        calendar_date=vec.calendar_date,
                        position_km=vec.position_km,
                        velocity_kms=vec.velocity_kms,
                    )

        return states_by_date, resp

    def compute_grid_synchronous(
        self,
        origin_body_norm: str,
        target_body_norm: str,
        departure_dates: List[date],
        arrival_dates: List[date],
        origin_states: Dict[str, EphemerisState],
        target_states: Dict[str, EphemerisState],
        dep_parking_alt_km: Optional[float] = None,
        arr_parking_alt_km: Optional[float] = None,
        prograde: bool = True,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Pure CPU-bound grid calculation loop.
        Evaluates zero-revolution Lambert solutions for all valid (dep, arr) pairs.
        """
        is_lunar = (origin_body_norm == "EARTH" and target_body_norm == "MOON")
        central_body_key = "EARTH" if is_lunar else "SUN"
        central_mu = BODY_REGISTRY[central_body_key].mu_km3_s2

        origin_info = BODY_REGISTRY[origin_body_norm]
        target_info = BODY_REGISTRY[target_body_norm]

        n_arr = len(arrival_dates)
        n_dep = len(departure_dates)

        # Initialize 2D grid arrays (indexed [arrival_idx][departure_idx])
        c3_grid: List[List[Optional[float]]] = [[None for _ in range(n_dep)] for _ in range(n_arr)]
        vinf_dep_grid: List[List[Optional[float]]] = [
            [None for _ in range(n_dep)] for _ in range(n_arr)
        ]
        vinf_arr_grid: List[List[Optional[float]]] = [
            [None for _ in range(n_dep)] for _ in range(n_arr)
        ]
        tof_days_grid: List[List[Optional[float]]] = [
            [None for _ in range(n_dep)] for _ in range(n_arr)
        ]
        dv_inj_grid: List[List[Optional[float]]] = [
            [None for _ in range(n_dep)] for _ in range(n_arr)
        ]
        dv_arr_grid: List[List[Optional[float]]] = [
            [None for _ in range(n_dep)] for _ in range(n_arr)
        ]
        dv_total_grid: List[List[Optional[float]]] = [
            [None for _ in range(n_dep)] for _ in range(n_arr)
        ]
        valid_mask: List[List[bool]] = [[False for _ in range(n_dep)] for _ in range(n_arr)]

        total_evaluations = 0
        valid_count = 0
        failed_convergence_count = 0
        total_iterations = 0
        max_residual = 0.0

        min_c3_val = float("inf")
        min_c3_point: Optional[Tuple[str, str, float, float]] = None

        min_vinf_dep_val = float("inf")
        min_vinf_dep_point: Optional[Tuple[str, str, float, float]] = None

        min_vinf_arr_val = float("inf")
        min_vinf_arr_point: Optional[Tuple[str, str, float, float]] = None

        min_dv_total_val = float("inf")
        min_dv_total_point: Optional[Tuple[str, str, float, float]] = None

        for i, d_arr in enumerate(arrival_dates):
            arr_key = d_arr.strftime("%Y-%m-%d")
            target_state = target_states.get(arr_key)
            if not target_state:
                continue

            for j, d_dep in enumerate(departure_dates):
                dep_key = d_dep.strftime("%Y-%m-%d")
                origin_state = origin_states.get(dep_key)
                if not origin_state:
                    continue

                tof_days = (d_arr - d_dep).days
                # Reject negative or zero time of flight
                if tof_days <= 0:
                    continue

                total_evaluations += 1
                tof_seconds = float(tof_days) * 86400.0
                tof_days_grid[i][j] = float(tof_days)

                # Set up boundary position vectors
                if is_lunar:
                    # Earth-centered lunar transfer:
                    # target is Moon geocentric vector
                    r2_vec = (
                        target_state.position_km.x,
                        target_state.position_km.y,
                        target_state.position_km.z,
                    )
                    v2_moon = (
                        target_state.velocity_kms.x,
                        target_state.velocity_kms.y,
                        target_state.velocity_kms.z,
                    )
                    # Spacecraft departs from circular parking orbit around Earth
                    # (nominal reference radius is 200 km if altitude unspecified)
                    r_dep_alt = dep_parking_alt_km if dep_parking_alt_km is not None else 200.0
                    r_park_dep = origin_info.equatorial_radius_km + r_dep_alt

                    # Orientation in the lunar transfer plane:
                    # Moon orbital angular momentum h = r_moon x v_moon
                    hx = r2_vec[1] * v2_moon[2] - r2_vec[2] * v2_moon[1]
                    hy = r2_vec[2] * v2_moon[0] - r2_vec[0] * v2_moon[2]
                    hz = r2_vec[0] * v2_moon[1] - r2_vec[1] * v2_moon[0]
                    h_norm = math.sqrt(hx**2 + hy**2 + hz**2)
                    if h_norm < 1e-6:
                        continue
                    h_unit = (hx / h_norm, hy / h_norm, hz / h_norm)

                    # Moon position unit vector
                    r2_norm = math.sqrt(sum(x**2 for x in r2_vec))
                    u2 = (r2_vec[0] / r2_norm, r2_vec[1] / r2_norm, r2_vec[2] / r2_norm)

                    # Transfer angle for lunar transfer (nominal coplanar arc ~ 150 deg)
                    theta_rad = math.radians(150.0)
                    # Cross product h_unit x u2
                    h_cross_u2 = (
                        h_unit[1] * u2[2] - h_unit[2] * u2[1],
                        h_unit[2] * u2[0] - h_unit[0] * u2[2],
                        h_unit[0] * u2[1] - h_unit[1] * u2[0],
                    )
                    # Rotate backwards in lunar orbit plane
                    if prograde:
                        u1 = (
                            math.cos(theta_rad) * u2[0] - math.sin(theta_rad) * h_cross_u2[0],
                            math.cos(theta_rad) * u2[1] - math.sin(theta_rad) * h_cross_u2[1],
                            math.cos(theta_rad) * u2[2] - math.sin(theta_rad) * h_cross_u2[2],
                        )
                    else:
                        u1 = (
                            math.cos(theta_rad) * u2[0] + math.sin(theta_rad) * h_cross_u2[0],
                            math.cos(theta_rad) * u2[1] + math.sin(theta_rad) * h_cross_u2[1],
                            math.cos(theta_rad) * u2[2] + math.sin(theta_rad) * h_cross_u2[2],
                        )
                    r1_vec = (r_park_dep * u1[0], r_park_dep * u1[1], r_park_dep * u1[2])

                else:
                    # Heliocentric transfer:
                    r1_vec = (
                        origin_state.position_km.x,
                        origin_state.position_km.y,
                        origin_state.position_km.z,
                    )
                    r2_vec = (
                        target_state.position_km.x,
                        target_state.position_km.y,
                        target_state.position_km.z,
                    )

                # Solve Lambert problem
                sol = solve_lambert(
                    r1=r1_vec,
                    r2=r2_vec,
                    time_of_flight_s=tof_seconds,
                    mu_km3_s2=central_mu,
                    prograde=prograde,
                    raise_on_failure=False,
                )

                if not sol.converged:
                    failed_convergence_count += 1
                    continue

                total_iterations += sol.iterations
                if sol.residual > max_residual:
                    max_residual = sol.residual

                # Compute relative excess velocities
                if is_lunar:
                    v1_mag = math.sqrt(sol.v1.x**2 + sol.v1.y**2 + sol.v1.z**2)
                    # Specific energy of geocentric transfer orbit: C3 = v1^2 - 2*mu/r
                    c3 = v1_mag**2 - 2.0 * central_mu / r_park_dep
                    v_inf_dep = math.sqrt(max(0.0, c3))

                    # Arrival excess velocity relative to Moon
                    v_inf_arr_vec = (
                        sol.v2.x - target_state.velocity_kms.x,
                        sol.v2.y - target_state.velocity_kms.y,
                        sol.v2.z - target_state.velocity_kms.z,
                    )
                    v_inf_arr = math.sqrt(sum(x**2 for x in v_inf_arr_vec))

                    # Departure injection Delta-V (TLI) ONLY when parking altitude provided
                    if dep_parking_alt_km is not None:
                        v_circ_dep = math.sqrt(central_mu / r_park_dep)
                        dv_inj = v1_mag - v_circ_dep
                    else:
                        dv_inj = None

                    # Lunar capture Delta-V (LOI) ONLY when arrival parking altitude provided
                    if arr_parking_alt_km is not None:
                        dv_cap = compute_hyperbolic_burn_delta_v(
                            v_inf=v_inf_arr,
                            mu_body=target_info.mu_km3_s2,
                            body_radius_km=target_info.equatorial_radius_km,
                            parking_orbit_alt_km=arr_parking_alt_km,
                        )
                    else:
                        dv_cap = None

                    if dv_inj is not None and dv_cap is not None:
                        dv_total = dv_inj + dv_cap
                    else:
                        dv_total = None

                else:
                    # Heliocentric transfer excess velocities
                    v_inf_dep_vec = (
                        sol.v1.x - origin_state.velocity_kms.x,
                        sol.v1.y - origin_state.velocity_kms.y,
                        sol.v1.z - origin_state.velocity_kms.z,
                    )
                    v_inf_dep = math.sqrt(sum(x**2 for x in v_inf_dep_vec))
                    c3 = v_inf_dep**2

                    v_inf_arr_vec = (
                        sol.v2.x - target_state.velocity_kms.x,
                        sol.v2.y - target_state.velocity_kms.y,
                        sol.v2.z - target_state.velocity_kms.z,
                    )
                    v_inf_arr = math.sqrt(sum(x**2 for x in v_inf_arr_vec))

                    # Parking orbit insertion and capture burns (if parameters specified)
                    if dep_parking_alt_km is not None:
                        dv_inj = compute_hyperbolic_burn_delta_v(
                            v_inf=v_inf_dep,
                            mu_body=origin_info.mu_km3_s2,
                            body_radius_km=origin_info.equatorial_radius_km,
                            parking_orbit_alt_km=dep_parking_alt_km,
                        )
                    else:
                        dv_inj = None

                    # For Europa, multi-body Jovian capture is unmodeled in 2-body heliocentric;
                    # capture Delta-V is omitted per scientific model requirements.
                    if target_body_norm == "EUROPA":
                        dv_cap = None
                        dv_total = None
                    else:
                        if arr_parking_alt_km is not None:
                            dv_cap = compute_hyperbolic_burn_delta_v(
                                v_inf=v_inf_arr,
                                mu_body=target_info.mu_km3_s2,
                                body_radius_km=target_info.equatorial_radius_km,
                                parking_orbit_alt_km=arr_parking_alt_km,
                            )
                        else:
                            dv_cap = None

                        if dv_inj is not None and dv_cap is not None:
                            dv_total = dv_inj + dv_cap
                        else:
                            dv_total = None

                # Record results
                c3_grid[i][j] = round(c3, 4)
                vinf_dep_grid[i][j] = round(v_inf_dep, 4)
                vinf_arr_grid[i][j] = round(v_inf_arr, 4)
                dv_inj_grid[i][j] = round(dv_inj, 4) if dv_inj is not None else None
                dv_arr_grid[i][j] = round(dv_cap, 4) if dv_cap is not None else None
                dv_total_grid[i][j] = round(dv_total, 4) if dv_total is not None else None
                valid_mask[i][j] = True
                valid_count += 1

                # Track valid minima
                if c3 < min_c3_val:
                    min_c3_val = c3
                    min_c3_point = (dep_key, arr_key, tof_days, c3)

                if v_inf_dep < min_vinf_dep_val:
                    min_vinf_dep_val = v_inf_dep
                    min_vinf_dep_point = (dep_key, arr_key, tof_days, v_inf_dep)

                if v_inf_arr < min_vinf_arr_val:
                    min_vinf_arr_val = v_inf_arr
                    min_vinf_arr_point = (dep_key, arr_key, tof_days, v_inf_arr)

                if dv_total is not None and dv_total < min_dv_total_val:
                    min_dv_total_val = dv_total
                    min_dv_total_point = (dep_key, arr_key, tof_days, dv_total)

            if on_progress is not None:
                row_progress = 15.0 + 80.0 * (i + 1) / n_arr
                try:
                    on_progress(row_progress)
                except Exception as exc:
                    logger.debug("Progress callback error: %s", exc)

        # Build minima metadata
        minima_dict: Dict[str, Optional[Dict[str, Any]]] = {
            "min_c3": (
                {
                    "metric_name": "Departure Characteristic Energy (C3)",
                    "value": round(min_c3_point[3], 4),
                    "departure_date": min_c3_point[0],
                    "arrival_date": min_c3_point[1],
                    "time_of_flight_days": min_c3_point[2],
                    "units": "km^2/s^2",
                }
                if min_c3_point
                else None
            ),
            "min_vinf_dep": (
                {
                    "metric_name": "Departure Hyperbolic Excess Velocity (v_inf)",
                    "value": round(min_vinf_dep_point[3], 4),
                    "departure_date": min_vinf_dep_point[0],
                    "arrival_date": min_vinf_dep_point[1],
                    "time_of_flight_days": min_vinf_dep_point[2],
                    "units": "km/s",
                }
                if min_vinf_dep_point
                else None
            ),
            "min_vinf_arr": (
                {
                    "metric_name": "Arrival Hyperbolic Excess Velocity (v_inf)",
                    "value": round(min_vinf_arr_point[3], 4),
                    "departure_date": min_vinf_arr_point[0],
                    "arrival_date": min_vinf_arr_point[1],
                    "time_of_flight_days": min_vinf_arr_point[2],
                    "units": "km/s",
                }
                if min_vinf_arr_point
                else None
            ),
            "min_total_delta_v": (
                {
                    "metric_name": "Total Mission Delta-V (Injection + Capture)",
                    "value": round(min_dv_total_point[3], 4),
                    "departure_date": min_dv_total_point[0],
                    "arrival_date": min_dv_total_point[1],
                    "time_of_flight_days": min_dv_total_point[2],
                    "units": "km/s",
                }
                if min_dv_total_point
                else None
            ),
        }

        solver_diagnostics = {
            "solver_method": (
                "Universal Variable Formulation with Stumpff Functions (Curtis 4th ed., Sec 5.3)"
            ),
            "converged_cells_count": valid_count,
            "failed_convergence_cells_count": failed_convergence_count,
            "convergence_rate_percent": (
                round(100.0 * valid_count / total_evaluations, 2)
                if total_evaluations > 0
                else 0.0
            ),
            "mean_iterations": (
                round(total_iterations / valid_count, 2)
                if valid_count > 0
                else 0.0
            ),
            "max_residual": round(max_residual, 6) if max_residual > 0.0 else 0.0,
        }

        return {
            "valid_cells_count": valid_count,
            "total_cells_count": n_dep * n_arr,
            "c3_grid": c3_grid,
            "vinf_dep_grid": vinf_dep_grid,
            "vinf_arr_grid": vinf_arr_grid,
            "tof_days_grid": tof_days_grid,
            "dv_inj_grid": dv_inj_grid,
            "dv_arr_grid": dv_arr_grid,
            "dv_total_grid": dv_total_grid,
            "valid_mask": valid_mask,
            "minima": minima_dict,
            "solver_diagnostics": solver_diagnostics,
        }

    async def generate_porkchop(
        self,
        origin_body: str,
        target_body: str,
        departure_start_date: str,
        departure_end_date: str,
        arrival_start_date: str,
        arrival_end_date: str,
        step_days: float = 2.0,
        dep_parking_alt_km: Optional[float] = None,
        arr_parking_alt_km: Optional[float] = None,
        prograde: bool = True,
        origin_states_override: Optional[Dict[str, EphemerisState]] = None,
        target_states_override: Optional[Dict[str, EphemerisState]] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end ephemeris-driven porkchop analysis.
        """
        origin_norm = normalize_body_name(origin_body)
        target_norm = normalize_body_name(target_body)

        if origin_norm == target_norm:
            raise ValueError(
                f"Origin body '{origin_body}' and target body '{target_body}' cannot be identical."
            )

        dep_dates = self._generate_date_range(departure_start_date, departure_end_date, step_days)
        arr_dates = self._generate_date_range(arrival_start_date, arrival_end_date, step_days)

        total_points = len(dep_dates) * len(arr_dates)
        if total_points > self.max_grid_points:
            raise ValueError(
                f"Requested grid size ({total_points} cells: {len(dep_dates)} dep x "
                f"{len(arr_dates)} arr) exceeds maximum permitted limit ({self.max_grid_points}). "
                "Increase step_days or narrow the date window."
            )

        # Determine Horizons center:
        # For Earth-to-Moon: Geocenter 500@399
        # For heliocentric transfers: Sun 500@10
        if origin_norm == "EARTH" and target_norm == "MOON":
            horizons_center = "500@399"
            dyn_model = (
                "Earth-centered two-body astrodynamic transfer model with Moon state vectors "
                "relative to Geocenter from JPL Horizons (DE441). Spacecraft departure is "
                "modeled from circular Earth parking orbit in the Moon's instantaneous orbital "
                "plane using nominal translunar transfer geometry (~150 deg). Trans-Lunar "
                "Injection (TLI) and Lunar Orbit Insertion (LOI) calculated only when explicit "
                "parking orbit altitudes are provided."
            )
        else:
            horizons_center = "500@10"
            if target_norm == "EUROPA":
                dyn_model = (
                    "Sun-centered two-body heliocentric Lambert transfer model using Europa and "
                    "Earth state vectors relative to the Sun (JPL Horizons DE441). "
                    "Europa is a moon of Jupiter orbiting at ~670,900 km. "
                    "Arrival excess velocity v_inf is relative to Europa's heliocentric motion. "
                    "LIMITATION: Jovian multi-body capture and Europa orbit insertion require "
                    "restricted 3-body/4-body Jovian numerical dynamics and are omitted from "
                    "this two-body heliocentric Lambert analysis."
                )
            else:
                dyn_model = (
                    "Sun-centered two-body heliocentric Lambert transfer model using official "
                    "JPL Horizons DE441 Cartesian state vectors relative to the Sun (500@10). "
                    "Excess velocities v_inf are relative to respective planetary body centers."
                )

        retrieval_timestamp = datetime.now(timezone.utc).isoformat()
        source_url = "https://ssd.jpl.nasa.gov/api/horizons.api"
        origin_query_params: Dict[str, Any] = {}
        target_query_params: Dict[str, Any] = {}
        cache_status_val = CacheStatus.LIVE.value

        # Fetch ephemerides (or use deterministic fixtures if provided)
        if origin_states_override is not None:
            origin_states = origin_states_override
            cache_status_val = "FIXTURE"
        else:
            origin_states, resp_orig = await self._fetch_body_ephemerides(
                origin_norm, dep_dates, center=horizons_center
            )
            source_url = resp_orig.source_url
            origin_query_params = resp_orig.query_params
            retrieval_timestamp = resp_orig.retrieved_at.isoformat()
            cache_status_val = resp_orig.cache_status.value

        if target_states_override is not None:
            target_states = target_states_override
            cache_status_val = "FIXTURE"
        else:
            target_states, resp_targ = await self._fetch_body_ephemerides(
                target_norm, arr_dates, center=horizons_center
            )
            target_query_params = resp_targ.query_params
            if cache_status_val != "FIXTURE":
                if resp_orig.cache_status == resp_targ.cache_status:
                    cache_status_val = resp_targ.cache_status.value
                else:
                    cache_status_val = "MIXED"

        # Offload CPU-bound grid calculation to worker thread to avoid blocking event loop
        grid_data = await asyncio.to_thread(
            self.compute_grid_synchronous,
            origin_body_norm=origin_norm,
            target_body_norm=target_norm,
            departure_dates=dep_dates,
            arrival_dates=arr_dates,
            origin_states=origin_states,
            target_states=target_states,
            dep_parking_alt_km=dep_parking_alt_km,
            arr_parking_alt_km=arr_parking_alt_km,
            prograde=prograde,
            on_progress=on_progress,
        )

        dep_date_strings = [d.strftime("%Y-%m-%d") for d in dep_dates]
        arr_date_strings = [d.strftime("%Y-%m-%d") for d in arr_dates]

        return {
            "origin_body": origin_norm,
            "target_body": target_norm,
            "departure_dates": dep_date_strings,
            "arrival_dates": arr_date_strings,
            "step_size_days": step_days,
            "total_grid_points": total_points,
            "valid_cells_count": grid_data["valid_cells_count"],
            "c3_grid": grid_data["c3_grid"],
            "vinf_dep_grid": grid_data["vinf_dep_grid"],
            "vinf_arr_grid": grid_data["vinf_arr_grid"],
            "tof_days_grid": grid_data["tof_days_grid"],
            "dv_inj_grid": grid_data["dv_inj_grid"],
            "dv_arr_grid": grid_data["dv_arr_grid"],
            "dv_total_grid": grid_data["dv_total_grid"],
            "valid_mask": grid_data["valid_mask"],
            "minima": grid_data["minima"],
            "units": {
                "c3": "km^2/s^2",
                "velocity": "km/s",
                "delta_v": "km/s",
                "time_of_flight": "days",
                "altitude": "km",
            },
            "solver_diagnostics": grid_data["solver_diagnostics"],
            "provenance": {
                "ephemeris_source": "NASA/JPL Solar System Dynamics Horizons API",
                "reference_frame": "ICRF / J2000 (FRAME)",
                "coordinate_center": horizons_center,
                "time_scale": "TDB (Barycentric Dynamical Time)",
                "solver_formulation": (
                    "Universal Variable Lambert Formulation (Curtis 4th ed., Sec 5.3)"
                ),
                "physical_model": dyn_model,
                "limitations": (
                    "Two-body Lambert transfer does not model launch windows' complete "
                    "operational constraints, planetary perturbations during transfer, "
                    "finite burns, navigation uncertainty, launch-vehicle limits, "
                    "atmospheric entry, or multi-body capture. When parking orbit altitudes "
                    "are omitted, insertion/capture delta-v maneuvers are uncalculated and "
                    "excess velocities (v_inf) / characteristic energy (C3) are provided."
                ),
                "source_url": source_url,
                "target_ids": {
                    "origin": BODY_REGISTRY[origin_norm].horizons_id,
                    "target": BODY_REGISTRY[target_norm].horizons_id,
                },
                "query_parameters": {
                    "origin": origin_query_params,
                    "target": target_query_params,
                },
                "retrieved_at": retrieval_timestamp,
                "cache_status": cache_status_val,
            },
        }
