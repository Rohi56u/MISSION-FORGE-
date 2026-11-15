"""
Lambert Boundary-Value Orbital Trajectory Solver
Mission Forge — Phase 3 Astrodynamics Core

Mathematical Formulation:
Universal Variable Formulation with Stumpff Functions (Curtis, H.D., Orbital
Mechanics for Engineering Students, 4th ed., Section 5.3; Bate, Mueller, &
White, Fundamentals of Astrodynamics, Chapter 5; Battin, R.H., 1999).

Units Convention:
- Position: kilometers (km)
- Velocity: kilometers per second (km/s)
- Time of flight: seconds (s)
- Gravitational parameter: km^3 / s^2
- Specific orbital energy: km^2 / s^2

Scope:
- Solves zero-revolution (N = 0) two-body Lambert boundary-value problems.
- Explicitly rejects multi-revolution requests (N > 0) per phase specifications.
- Supports prograde, retrograde, short-way, and long-way transfer geometry.
- Enforces strict input validation, singularity detection (collinear vectors,
  transfer angles near 0 or pi), and safeguards against non-convergence.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, Sequence, Tuple, Union

from backend.app.integrations.horizons.models import Vector3D


class LambertError(Exception):
    """Base exception for Lambert solver failures."""
    pass


class LambertDomainError(LambertError, ValueError):
    """Raised when Lambert solver inputs violate physical or mathematical domain constraints."""
    pass


class LambertCollinearError(LambertError):
    """Raised when boundary position vectors are collinear (transfer plane undefined)."""
    pass


class LambertConvergenceError(LambertError):
    """Raised when numerical iteration fails to converge within specified tolerance."""
    pass


@dataclass(frozen=True)
class LambertSolution:
    """
    Typed, immutable result of a Lambert boundary-value problem solve.
    """
    v1: Vector3D
    v2: Vector3D
    converged: bool
    iterations: int
    residual: float
    semi_major_axis_km: float
    eccentricity: float
    transfer_angle_deg: float
    time_of_flight_s: float
    solution_branch: str
    stumpff_z: float
    units: Dict[str, str] = field(
        default_factory=lambda: {
            "position": "km",
            "velocity": "km/s",
            "time_of_flight": "seconds",
            "semi_major_axis": "km",
            "gravitational_parameter": "km^3/s^2",
            "energy": "km^2/s^2",
            "residual": "km^1.5",
        }
    )


def _stumpff_c(z: float) -> float:
    """
    Evaluates Stumpff function C(z) = (1 - cos(sqrt(z))) / z.
    Uses truncated Taylor series for |z| < 1e-4 to maintain machine precision.
    """
    if z > 1e-4:
        return (1.0 - math.cos(math.sqrt(z))) / z
    elif z < -1e-4:
        alpha = math.sqrt(-z)
        return (math.cosh(alpha) - 1.0) / (-z)
    else:
        # Taylor series: 1/2 - z/24 + z^2/720 - z^3/40320 + z^4/3628800
        return 0.5 - z / 24.0 + (z**2) / 720.0 - (z**3) / 40320.0 + (z**4) / 3628800.0


def _stumpff_s(z: float) -> float:
    """
    Evaluates Stumpff function S(z) = (sqrt(z) - sin(sqrt(z))) / (z^(3/2)).
    Uses truncated Taylor series for |z| < 1e-4 to maintain machine precision.
    """
    if z > 1e-4:
        sz = math.sqrt(z)
        return (sz - math.sin(sz)) / (z**1.5)
    elif z < -1e-4:
        alpha = math.sqrt(-z)
        return (math.sinh(alpha) - alpha) / ((-z)**1.5)
    else:
        # Taylor series: 1/6 - z/120 + z^2/5040 - z^3/362880 + z^4/39916800
        return 1.0 / 6.0 - z / 120.0 + (z**2) / 5040.0 - (z**3) / 362880.0 + (z**4) / 39916800.0


def _cross_product(
    a: Sequence[float], b: Sequence[float]
) -> Tuple[float, float, float]:
    """Calculates Cartesian cross product a x b."""
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot_product(a: Sequence[float], b: Sequence[float]) -> float:
    """Calculates Cartesian dot product a . b."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vector_norm(a: Sequence[float]) -> float:
    """Calculates Euclidean norm ||a||."""
    return math.sqrt(a[0]**2 + a[1]**2 + a[2]**2)


def solve_lambert(
    r1: Union[Vector3D, Sequence[float]],
    r2: Union[Vector3D, Sequence[float]],
    time_of_flight_s: float,
    mu_km3_s2: float = 132712440018.0,
    prograde: bool = True,
    transfer_angle_type: str = "auto",
    n_revolutions: int = 0,
    max_iterations: int = 100,
    tolerance: float = 1e-7,
    raise_on_failure: bool = True,
) -> LambertSolution:
    """
    Solves the two-body Lambert boundary-value orbital problem.

    Given initial position r1 and final position r2 at time separation dt
    around a central body with gravitational parameter mu, determines the
    unique zero-revolution Keplerian transfer velocities v1 and v2.

    Parameters:
    -----------
    r1 : Vector3D or 3-element Sequence[float]
        Cartesian position vector at departure (km).
    r2 : Vector3D or 3-element Sequence[float]
        Cartesian position vector at arrival (km).
    time_of_flight_s : float
        Elapsed transfer duration (seconds). Must be strictly positive.
    mu_km3_s2 : float
        Central gravitational parameter (km^3/s^2). Default is Sun (1.32712440018e11).
    prograde : bool
        Transfer direction. True for prograde (inclination <= 90 deg / c_z >= 0),
        False for retrograde.
    transfer_angle_type : str
        Transfer angle selection:
        - "auto": dynamically selects short/long way based on prograde/retrograde inclination
        - "short": short-way transfer (0 < delta_nu < pi)
        - "long": long-way transfer (pi < delta_nu < 2*pi)
    n_revolutions : int
        Number of complete orbital revolutions. Only N = 0 (zero-revolution)
        is supported. Any N != 0 raises LambertDomainError.
    max_iterations : int
        Maximum Newton-Raphson / bisection iterations (default 100).
    tolerance : float
        Relative convergence tolerance on universal variable time-of-flight equation
        residual |F(z)| / (sqrt(mu) * dt) (dimensionless, default 1e-7).
    raise_on_failure : bool
        If True, raises LambertConvergenceError on failure. If False, returns
        a LambertSolution marked converged=False.

    Returns:
    --------
    LambertSolution: Typed solution containing v1, v2, orbital elements, and diagnostics.
    """
    # 1. Validation of multi-revolution constraint
    if n_revolutions != 0:
        raise LambertDomainError(
            f"Multi-revolution transfers (N={n_revolutions}) are not supported in Phase 3. "
            "Only zero-revolution transfers (N=0) are physically modeled."
        )

    # 2. Validation of time of flight and gravitational parameter
    if not math.isfinite(time_of_flight_s) or time_of_flight_s <= 0.0:
        raise LambertDomainError(
            f"Time of flight must be strictly positive and finite. Received: {time_of_flight_s} s"
        )
    if not math.isfinite(mu_km3_s2) or mu_km3_s2 <= 0.0:
        raise LambertDomainError(
            f"Gravitational parameter mu must be strictly positive and finite. "
            f"Received: {mu_km3_s2}"
        )

    # 3. Vector parsing and coordinate validation
    if isinstance(r1, Vector3D):
        r1_vec = (r1.x, r1.y, r1.z)
    elif len(r1) == 3:
        r1_vec = (float(r1[0]), float(r1[1]), float(r1[2]))
    else:
        raise LambertDomainError(f"r1 must be 3-dimensional. Received: {r1}")

    if isinstance(r2, Vector3D):
        r2_vec = (r2.x, r2.y, r2.z)
    elif len(r2) == 3:
        r2_vec = (float(r2[0]), float(r2[1]), float(r2[2]))
    else:
        raise LambertDomainError(f"r2 must be 3-dimensional. Received: {r2}")

    for val in r1_vec + r2_vec:
        if not math.isfinite(val):
            raise LambertDomainError(f"Position vector components must be finite. Received: {val}")

    norm_r1 = _vector_norm(r1_vec)
    norm_r2 = _vector_norm(r2_vec)
    if norm_r1 <= 0.0 or norm_r2 <= 0.0:
        raise LambertDomainError("Position vectors cannot be zero-magnitude.")

    # 4. Geometry and transfer angle computation
    dot_r1_r2 = _dot_product(r1_vec, r2_vec)
    cos_delta_nu = dot_r1_r2 / (norm_r1 * norm_r2)
    # Clamp to [-1, 1] to avoid float precision domain errors in acos
    cos_delta_nu = max(-1.0, min(1.0, cos_delta_nu))

    cross_r1_r2 = _cross_product(r1_vec, r2_vec)
    cross_mag = _vector_norm(cross_r1_r2)

    # Singularity check: near-collinear boundary vectors
    collinear_ratio = cross_mag / (norm_r1 * norm_r2)
    if collinear_ratio < 1e-7 or abs(abs(cos_delta_nu) - 1.0) < 1e-7:
        if raise_on_failure:
            raise LambertCollinearError(
                f"Position vectors r1 and r2 are collinear or near-collinear "
                f"(transfer angle ~ 0 or 180 deg, sin(nu)={cross_mag / (norm_r1 * norm_r2):.2e}). "
                "Orbital transfer plane is physically undefined."
            )
        return _unconverged_solution(
            r1_vec, r2_vec, time_of_flight_s, "collinear vectors singularity"
        )

    # Determine transfer angle delta_nu
    theta = math.acos(cos_delta_nu)
    if transfer_angle_type == "short":
        delta_nu = theta
    elif transfer_angle_type == "long":
        delta_nu = 2.0 * math.pi - theta
    elif transfer_angle_type == "auto":
        c_z = cross_r1_r2[2]
        if prograde:
            delta_nu = theta if c_z >= 0.0 else 2.0 * math.pi - theta
        else:
            delta_nu = theta if c_z < 0.0 else 2.0 * math.pi - theta
    else:
        raise LambertDomainError(
            f"Invalid transfer_angle_type: '{transfer_angle_type}'. "
            "Must be 'auto', 'short', or 'long'."
        )

    # 5. Curtis geometric constant A
    sin_delta_nu = math.sin(delta_nu)
    denom = 1.0 - cos_delta_nu
    if denom <= 0.0 or abs(sin_delta_nu) < 1e-12:
        if raise_on_failure:
            raise LambertCollinearError(
                "Transfer angle causes geometric singularity in Lambert parameter A."
            )
        return _unconverged_solution(r1_vec, r2_vec, time_of_flight_s, "singularity in A")

    A = sin_delta_nu * math.sqrt(norm_r1 * norm_r2 / denom)

    # 6. Evaluation helper functions for y(z), F(z), and dF(z)
    def calc_y(z: float) -> float:
        cz = _stumpff_c(z)
        sz = _stumpff_s(z)
        if cz <= 0.0:
            return -1.0
        return norm_r1 + norm_r2 + A * (z * sz - 1.0) / math.sqrt(cz)

    def calc_F(z: float) -> Tuple[float, float]:
        """Calculates F(z) and y(z). Returns (F(z), y(z))."""
        cz = _stumpff_c(z)
        sz = _stumpff_s(z)
        yz = calc_y(z)
        if yz <= 0.0:
            return float("nan"), yz
        tof_eval = (yz / cz)**1.5 * sz + A * math.sqrt(yz)
        fz = tof_eval - math.sqrt(mu_km3_s2) * time_of_flight_s
        return fz, yz

    def calc_dF(z: float, yz: float) -> float:
        """Evaluates derivative dF/dz using closed-form analytical expression."""
        cz = _stumpff_c(z)
        sz = _stumpff_s(z)
        if yz <= 0.0 or cz <= 0.0:
            return float("nan")

        if abs(z) < 1e-4:
            term1 = (yz / cz)**1.5 * (1.0 / 80.0)
        else:
            bracket = (1.0 / (2.0 * z)) * (cz - 1.5 * sz / cz) + 0.75 * (sz**2) / cz
            term1 = (yz / cz)**1.5 * bracket

        term2 = (A / 8.0) * (3.0 * (sz / cz) * math.sqrt(yz) + A * math.sqrt(cz / yz))
        return term1 + term2

    # 7. Root-Finding with Safeguarded Hybrid Newton-Raphson / Bisection
    # For zero-revolution, z < 4*pi^2 is the physical upper bound.
    # Physical lower bound requires y(z) > 0.
    z_min = -100.0
    if calc_y(z_min) <= 0.0:
        lo, hi = z_min, 0.0
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if calc_y(mid) <= 0.0:
                lo = mid
            else:
                hi = mid
        z_min = hi + 1e-4

    z_low = z_min
    z_high = 4.0 * (math.pi**2) - 1e-4
    scale = math.sqrt(mu_km3_s2) * time_of_flight_s
    tol_scaled = max(tolerance * scale, tolerance)

    # Initialize z at 0 (parabolic baseline)
    z = 0.0
    converged = False
    final_residual = 0.0
    iteration = 0
    final_yz = norm_r1 + norm_r2 - A * math.sqrt(2.0)

    for iteration in range(1, max_iterations + 1):
        fz, yz = calc_F(z)
        if math.isnan(fz):
            # Step into illegal domain; fall back to bisection midpoint
            z = 0.5 * (z_low + z_high)
            continue

        final_residual = abs(fz)
        final_yz = yz

        # Check convergence using scale-aware tolerance
        if final_residual <= tol_scaled:
            converged = True
            break

        # Update root-bracketing bounds based on monotonicity of F(z)
        if fz < 0.0:
            z_low = max(z_low, z)
        else:
            z_high = min(z_high, z)

        dfz = calc_dF(z, yz)
        if dfz != 0.0 and math.isfinite(dfz):
            z_step = z - fz / dfz
            # Accept Newton step if inside bracket and y > 0
            if z_low < z_step < z_high and calc_y(z_step) > 0.0:
                z = z_step
                continue

        # Safeguard fallback: bisection
        z = 0.5 * (z_low + z_high)

    if not converged:
        if raise_on_failure:
            raise LambertConvergenceError(
                f"Lambert solver failed to converge within {max_iterations} iterations. "
                f"Final residual: {final_residual:.3e} (tolerance: {tolerance:.3e})"
            )
        return _unconverged_solution(
            r1_vec, r2_vec, time_of_flight_s, f"non-convergence (residual={final_residual:.2e})"
        )

    # 8. Compute Lagrange coefficients f, g, g_dot
    if final_yz <= 0.0:
        if raise_on_failure:
            raise LambertConvergenceError(f"Non-physical intermediate state y={final_yz} <= 0.")
        return _unconverged_solution(r1_vec, r2_vec, time_of_flight_s, "non-physical y")

    f = 1.0 - final_yz / norm_r1
    g = A * math.sqrt(final_yz / mu_km3_s2)
    g_dot = 1.0 - final_yz / norm_r2

    if abs(g) < 1e-12:
        if raise_on_failure:
            raise LambertConvergenceError("Lagrange coefficient g is singular.")
        return _unconverged_solution(r1_vec, r2_vec, time_of_flight_s, "singular g")

    # 9. Velocity vectors v1 and v2
    v1_x = (r2_vec[0] - f * r1_vec[0]) / g
    v1_y = (r2_vec[1] - f * r1_vec[1]) / g
    v1_z = (r2_vec[2] - f * r1_vec[2]) / g

    v2_x = (g_dot * r2_vec[0] - r1_vec[0]) / g
    v2_y = (g_dot * r2_vec[1] - r1_vec[1]) / g
    v2_z = (g_dot * r2_vec[2] - r1_vec[2]) / g

    # 10. Orbital mechanics derived diagnostics
    v1_mag = math.sqrt(v1_x**2 + v1_y**2 + v1_z**2)
    specific_energy = (v1_mag**2) / 2.0 - mu_km3_s2 / norm_r1
    if abs(specific_energy) > 1e-12:
        semi_major_axis = -mu_km3_s2 / (2.0 * specific_energy)
    else:
        semi_major_axis = float("inf")

    # Eccentricity vector e = ((v^2 - mu/r)*r - (r.v)*v) / mu
    r1_dot_v1 = r1_vec[0] * v1_x + r1_vec[1] * v1_y + r1_vec[2] * v1_z
    e_factor1 = v1_mag**2 - mu_km3_s2 / norm_r1
    e_vec = (
        (e_factor1 * r1_vec[0] - r1_dot_v1 * v1_x) / mu_km3_s2,
        (e_factor1 * r1_vec[1] - r1_dot_v1 * v1_y) / mu_km3_s2,
        (e_factor1 * r1_vec[2] - r1_dot_v1 * v1_z) / mu_km3_s2,
    )
    eccentricity = _vector_norm(e_vec)

    branch = (
        f"zero-revolution, {'prograde' if prograde else 'retrograde'}, "
        f"{'short-way' if delta_nu <= math.pi else 'long-way'}"
    )

    return LambertSolution(
        v1=Vector3D(x=v1_x, y=v1_y, z=v1_z),
        v2=Vector3D(x=v2_x, y=v2_y, z=v2_z),
        converged=True,
        iterations=iteration,
        residual=final_residual,
        semi_major_axis_km=semi_major_axis,
        eccentricity=eccentricity,
        transfer_angle_deg=math.degrees(delta_nu),
        time_of_flight_s=time_of_flight_s,
        solution_branch=branch,
        stumpff_z=z,
    )


def _unconverged_solution(
    r1: Tuple[float, float, float],
    r2: Tuple[float, float, float],
    tof: float,
    reason: str,
) -> LambertSolution:
    """Constructs a deterministic unconverged LambertSolution without bogus numerical velocity."""
    return LambertSolution(
        v1=Vector3D(x=float("nan"), y=float("nan"), z=float("nan")),
        v2=Vector3D(x=float("nan"), y=float("nan"), z=float("nan")),
        converged=False,
        iterations=0,
        residual=float("inf"),
        semi_major_axis_km=float("nan"),
        eccentricity=float("nan"),
        transfer_angle_deg=float("nan"),
        time_of_flight_s=tof,
        solution_branch=f"unconverged: {reason}",
        stumpff_z=float("nan"),
    )
