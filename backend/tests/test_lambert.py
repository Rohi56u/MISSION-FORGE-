"""
Unit and Integration Tests for Lambert Boundary-Value Solver
Mission Forge — Phase 3

Tests include:
1. Curtis Example 5.2 textbook validation (elliptical orbit).
2. Analytical Hohmann circular-orbit check.
3. Hyperbolic orbit convergence and consistency.
4. Specific orbital energy and angular momentum conservation.
5. Prograde vs retrograde transfer geometry.
6. Short-way vs long-way transfer angle selection.
7. Explicit multi-revolution rejection (N != 0).
8. Singularities: Collinear vectors (0 and 180 deg), zero vectors, negative TOF, negative mu.
9. Deterministic unconverged failure handling (never fabricated numbers).
10. FastAPI endpoint POST /api/v1/trajectory/lambert validation and error responses.
"""

import math
from typing import Sequence
import pytest
from httpx import AsyncClient, ASGITransport

from backend.app.astrodynamics.lambert import (
    LambertCollinearError,
    LambertDomainError,
    solve_lambert,
)
from backend.app.main import app


# =========================================================================
# 1. TEXTBOOK REFERENCE VALIDATION: CURTIS EXAMPLE 5.2
# =========================================================================

def test_curtis_example_5_2():
    """
    Validates against Curtis (Orbital Mechanics for Engineering Students, 4th ed., Example 5.2):
    r1 = [5000, 10000, 2100] km
    r2 = [-14600, 2500, 7000] km
    dt = 3600 s (1 hr)
    mu = 398600.4418 km^3/s^2 (Earth)
    Published results:
    v1 = [-5.9925, 1.9254, 3.2456] km/s
    v2 = [-3.3125, -4.1966, -0.3853] km/s
    a ~ 20000 km
    """
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]
    dt = 3600.0
    mu = 398600.4418

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, prograde=True)

    assert sol.converged is True
    assert sol.iterations <= 15
    assert sol.residual < 1e-2

    # Verify v1 against published solution
    assert pytest.approx(sol.v1.x, abs=1e-3) == -5.9925
    assert pytest.approx(sol.v1.y, abs=1e-3) == 1.9254
    assert pytest.approx(sol.v1.z, abs=1e-3) == 3.2456

    # Verify v2 against published solution
    assert pytest.approx(sol.v2.x, abs=1e-3) == -3.3125
    assert pytest.approx(sol.v2.y, abs=1e-3) == -4.1966
    assert pytest.approx(sol.v2.z, abs=1e-3) == -0.3853

    # Verify semi-major axis ~ 20000 km
    assert pytest.approx(sol.semi_major_axis_km, rel=1e-3) == 20000.0
    assert "prograde" in sol.solution_branch
    assert "short-way" in sol.solution_branch


def test_bmw_reference_validation():
    """
    Validates against Bate, Mueller, & White (Fundamentals of Astrodynamics, 1971, Section 5.3):
    r1 = [1591.80, 6241.42, 0.0] km
    r2 = [13210.0, 16000.0, 0.0] km
    dt = 2700.0 s (45 minutes)
    mu = 398600.4418 km^3/s^2 (Earth)
    Published results:
    v1 ~ [-4.24, -10.16, 0.0] km/s
    v2 ~ [3.42, 4.92, 0.0] km/s
    """
    r1 = [1591.80, 6241.42, 0.0]
    r2 = [13210.0, 16000.0, 0.0]
    dt = 2700.0
    mu = 398600.4418

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, prograde=True)

    assert sol.converged is True
    assert pytest.approx(sol.v1.x, abs=0.05) == -4.24
    assert pytest.approx(sol.v1.y, abs=0.05) == -10.16
    assert pytest.approx(sol.v1.z, abs=1e-5) == 0.0

    assert pytest.approx(sol.v2.x, abs=0.05) == 3.42
    assert pytest.approx(sol.v2.y, abs=0.05) == 4.92
    assert pytest.approx(sol.v2.z, abs=1e-5) == 0.0


# =========================================================================
# 2. ANALYTICAL CONSERVATION OF ENERGY AND ANGULAR MOMENTUM
# =========================================================================

def test_orbital_invariants_conservation():
    """
    Verifies that the orbit determined by the Lambert solver strictly conserves
    specific mechanical energy (E1 == E2) and orbital angular momentum (h1 == h2).
    """
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]
    dt = 3600.0
    mu = 398600.4418

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, prograde=True)

    r1_mag = math.sqrt(sum(x**2 for x in r1))
    r2_mag = math.sqrt(sum(x**2 for x in r2))
    v1_mag = math.sqrt(sol.v1.x**2 + sol.v1.y**2 + sol.v1.z**2)
    v2_mag = math.sqrt(sol.v2.x**2 + sol.v2.y**2 + sol.v2.z**2)

    # Specific mechanical energy: E = v^2 / 2 - mu / r
    energy1 = (v1_mag**2) / 2.0 - mu / r1_mag
    energy2 = (v2_mag**2) / 2.0 - mu / r2_mag
    assert pytest.approx(energy1, abs=1e-8) == energy2

    # Angular momentum: h = r x v
    h1 = (
        r1[1] * sol.v1.z - r1[2] * sol.v1.y,
        r1[2] * sol.v1.x - r1[0] * sol.v1.z,
        r1[0] * sol.v1.y - r1[1] * sol.v1.x,
    )
    h2 = (
        r2[1] * sol.v2.z - r2[2] * sol.v2.y,
        r2[2] * sol.v2.x - r2[0] * sol.v2.z,
        r2[0] * sol.v2.y - r2[1] * sol.v2.x,
    )
    for comp1, comp2 in zip(h1, h2):
        assert pytest.approx(comp1, abs=1e-5) == comp2


# =========================================================================
# 3. ANALYTICAL CIRCULAR/HOHMANN HALF-ORBIT CASE
# =========================================================================

def test_analytical_hohmann_transfer_velocities():
    """
    Tests an analytical coplanar transfer between Earth and Mars circular orbits:
    r1 = 1.0 AU, r2 = 1.524 AU, delta_nu = 180 deg (or 179.9 deg to avoid singularity).
    Verifies that departure velocity matches analytical vis-viva equation.
    """
    mu_sun = 1.32712440018e11  # km^3/s^2
    r1_val = 149597870.7  # 1 AU in km
    r2_val = 149597870.7 * 1.524  # 1.524 AU

    # 179.0 degrees to stay clear of exact collinear singularity
    theta_rad = math.radians(179.0)
    r1 = [r1_val, 0.0, 0.0]
    r2 = [r2_val * math.cos(theta_rad), r2_val * math.sin(theta_rad), 0.0]

    # Analytical Hohmann semi-major axis and TOF
    a_hohmann = (r1_val + r2_val) / 2.0
    tof_hohmann = math.pi * math.sqrt((a_hohmann**3) / mu_sun)  # ~ 258.9 days

    sol = solve_lambert(
        r1=r1,
        r2=r2,
        time_of_flight_s=tof_hohmann,
        mu_km3_s2=mu_sun,
        prograde=True,
    )

    assert sol.converged is True
    # Analytical departure speed from vis-viva: v1 = sqrt(mu * (2/r1 - 1/a))
    v1_analytical = math.sqrt(mu_sun * (2.0 / r1_val - 1.0 / a_hohmann))  # ~ 32.73 km/s
    v1_mag = math.sqrt(sol.v1.x**2 + sol.v1.y**2 + sol.v1.z**2)
    assert pytest.approx(v1_mag, rel=1e-2) == v1_analytical


# =========================================================================
# 4. HYPERBOLIC AND RETROGRADE TRANSFERS
# =========================================================================

def test_hyperbolic_transfer():
    """Tests high-speed / short TOF trajectory resulting in hyperbolic orbit (z < 0)."""
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]
    dt = 1200.0  # 20 minutes (extremely fast -> hyperbolic)
    mu = 398600.4418

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, prograde=True)

    assert sol.converged is True
    assert sol.stumpff_z < 0.0  # Hyperbolic branch
    assert sol.eccentricity > 1.0  # Hyperbolic orbit


def test_retrograde_transfer_geometry():
    """Tests retrograde transfer geometry produces opposite angular momentum sense."""
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]
    dt = 3600.0
    mu = 398600.4418

    sol_prog = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, prograde=True)
    sol_ret = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, prograde=False)

    assert sol_prog.converged is True
    assert sol_ret.converged is True
    # Velocities should be distinct
    assert sol_prog.v1.x != sol_ret.v1.x
    assert "retrograde" in sol_ret.solution_branch


def test_long_way_transfer_geometry():
    """
    Verifies long-way transfer (transfer_angle_type='long') produces
    transfer angle delta_nu > 180 deg and correct branch classification.
    """
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]
    dt = 72000.0  # 20 hours
    mu = 398600.4418

    sol = solve_lambert(
        r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, transfer_angle_type="long"
    )

    assert sol.converged is True
    assert sol.transfer_angle_deg > 180.0
    assert "long-way" in sol.solution_branch


# =========================================================================
# 5. MULTI-REVOLUTION EXPLICIT REJECTION
# =========================================================================

def test_multi_revolution_rejected():
    """Verifies that requesting multi-revolution transfers (N > 0) is explicitly rejected."""
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]

    with pytest.raises(LambertDomainError, match="Multi-revolution transfers.*are not supported"):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, n_revolutions=1)

    with pytest.raises(LambertDomainError, match="Multi-revolution transfers.*are not supported"):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, n_revolutions=2)


# =========================================================================
# 6. SINGULARITIES AND INVALID INPUT SAFEGUARDS
# =========================================================================

def test_collinear_vectors_singularity():
    """Verifies collinear boundary vectors (transfer angle 180 deg) raise LambertCollinearError."""
    r1 = [10000.0, 0.0, 0.0]
    r2 = [-20000.0, 0.0, 0.0]  # Exactly opposite (180 deg)

    with pytest.raises(LambertCollinearError):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, raise_on_failure=True)

    # When raise_on_failure is False, returns unconverged solution with NaNs
    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, raise_on_failure=False)
    assert sol.converged is False
    assert math.isnan(sol.v1.x)
    assert math.isnan(sol.v2.x)


def test_invalid_tof_and_mu():
    """Verifies negative or zero TOF and non-positive mu raise LambertDomainError."""
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]

    with pytest.raises(LambertDomainError, match="Time of flight must be strictly positive"):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=0.0)

    with pytest.raises(LambertDomainError, match="Time of flight must be strictly positive"):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=-1000.0)

    with pytest.raises(
        LambertDomainError,
        match="Gravitational parameter mu must be strictly positive",
    ):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, mu_km3_s2=-1.0)


def test_zero_and_infinite_vectors():
    """Verifies zero magnitude or non-finite position vectors raise LambertDomainError."""
    r1 = [0.0, 0.0, 0.0]
    r2 = [10000.0, 5000.0, 2000.0]

    with pytest.raises(LambertDomainError, match="Position vectors cannot be zero-magnitude"):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0)

    with pytest.raises(LambertDomainError, match="Position vector components must be finite"):
        solve_lambert(r1=[float("inf"), 0.0, 0.0], r2=r2, time_of_flight_s=3600.0)


def test_collinear_parallel_zero_deg_singularity():
    """Verifies parallel collinear vectors (0 deg) raise LambertCollinearError."""
    r1 = [10000.0, 0.0, 0.0]
    r2 = [20000.0, 0.0, 0.0]  # Parallel, delta_nu = 0 deg

    with pytest.raises(LambertCollinearError):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, raise_on_failure=True)

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, raise_on_failure=False)
    assert sol.converged is False
    assert math.isnan(sol.v1.x)


def test_nan_tof_and_mu():
    """Verifies NaN in TOF or mu raises LambertDomainError."""
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]

    with pytest.raises(LambertDomainError, match="Time of flight must be strictly positive"):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=float("nan"))

    with pytest.raises(
        LambertDomainError,
        match="Gravitational parameter mu must be strictly positive",
    ):
        solve_lambert(r1=r1, r2=r2, time_of_flight_s=3600.0, mu_km3_s2=float("nan"))


# =========================================================================
# 7. FASTAPI API ROUTE VERIFICATION: POST /api/v1/trajectory/lambert
# =========================================================================

@pytest.mark.asyncio
async def test_api_lambert_solve_success():
    """Tests successful solve via FastAPI route POST /api/v1/trajectory/lambert."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        payload = {
            "r1_km": {"x": 5000.0, "y": 10000.0, "z": 2100.0},
            "r2_km": {"x": -14600.0, "y": 2500.0, "z": 7000.0},
            "time_of_flight_s": 3600.0,
            "mu_km3_s2": 398600.4418,
            "prograde": True,
        }
        resp = await client.post("/api/v1/trajectory/lambert", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["converged"] is True
        assert pytest.approx(data["v1_kms"]["x"], abs=1e-3) == -5.9925
        assert pytest.approx(data["v2_kms"]["x"], abs=1e-3) == -3.3125
        assert data["units"]["velocity"] == "km/s"
        assert data["units"]["position"] == "km"


@pytest.mark.asyncio
async def test_api_lambert_solve_validation_error():
    """Tests validation error on invalid / non-positive TOF."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        payload = {
            "r1_km": {"x": 5000.0, "y": 10000.0, "z": 2100.0},
            "r2_km": {"x": -14600.0, "y": 2500.0, "z": 7000.0},
            "time_of_flight_s": -3600.0,  # Invalid
        }
        resp = await client.post("/api/v1/trajectory/lambert", json=payload)
        assert resp.status_code == 422


# =========================================================================
# 8. INDEPENDENT MATHEMATICAL AUDIT: CIRCULAR ORBIT, RESIDUAL, RK4, BMW
# =========================================================================

def test_circular_orbit_quarter_transfer_exact():
    """
    Independently validates a true circular-orbit quarter-transfer (90 degrees).

    Central body: Earth (mu = 398600.4418 km^3/s^2).
    Orbit: Circular orbit at radius r = 7000.0 km.
    Boundary vectors: r1 = [7000, 0, 0] km, r2 = [0, 7000, 0] km.
    Expected orbital velocity: v_circ = sqrt(mu / r) = 7.5460533 km/s.
    Orbital period: T = 2 * pi * sqrt(r^3 / mu) = 5828.51656 s.
    Quarter-orbit flight time: dt = T / 4 = 1457.12914 s (NOT 1383.17 s).

    Verifies:
    - Departure velocity v1 = [0.0, 7.5460533, 0.0] km/s.
    - Arrival velocity v2 = [-7.5460533, 0.0, 0.0] km/s.
    - Semi-major axis = 7000.0 km.
    - Eccentricity = 0.0 (circular).
    - Residual has units 'km^1.5' in units dictionary.
    """
    mu_earth = 398600.4418
    r_val = 7000.0
    r1 = [r_val, 0.0, 0.0]
    r2 = [0.0, r_val, 0.0]

    v_circ_expected = math.sqrt(mu_earth / r_val)
    t_period = 2.0 * math.pi * math.sqrt((r_val**3) / mu_earth)
    dt_quarter = t_period / 4.0  # 1457.1291404... s

    sol = solve_lambert(
        r1=r1,
        r2=r2,
        time_of_flight_s=dt_quarter,
        mu_km3_s2=mu_earth,
        prograde=True,
    )

    assert sol.converged is True
    # Initial velocity is purely transverse (+Y)
    assert pytest.approx(sol.v1.x, abs=1e-5) == 0.0
    assert pytest.approx(sol.v1.y, abs=1e-5) == v_circ_expected
    assert pytest.approx(sol.v1.z, abs=1e-5) == 0.0

    # Arrival velocity is purely transverse (-X)
    assert pytest.approx(sol.v2.x, abs=1e-5) == -v_circ_expected
    assert pytest.approx(sol.v2.y, abs=1e-5) == 0.0
    assert pytest.approx(sol.v2.z, abs=1e-5) == 0.0

    # Verify circular orbit invariants
    assert pytest.approx(sol.semi_major_axis_km, abs=0.1) == 7000.0
    assert sol.eccentricity < 1e-6
    assert sol.units["residual"] == "km^1.5"


def test_circular_orbit_1383s_discrepancy_analysis():
    """
    Rigorously scrutinizes the report's claimed 1383.17 s circular orbit transfer time.
    Proves mathematically that dt = 1383.17 s between [7000, 0, 0] and [0, 7000, 0]
    produces a faster elliptic orbit (a ~ 7404.25 km, e ~ 0.0736, v1_mag ~ 7.749 km/s),
    and CANNOT represent circular velocity (7.546 km/s) or a circular orbit (a = 7000 km).
    """
    mu_earth = 398600.4418
    r_val = 7000.0
    r1 = [r_val, 0.0, 0.0]
    r2 = [0.0, r_val, 0.0]
    dt_claimed = 1383.17  # Reported flight time

    sol = solve_lambert(
        r1=r1,
        r2=r2,
        time_of_flight_s=dt_claimed,
        mu_km3_s2=mu_earth,
        prograde=True,
    )

    assert sol.converged is True
    # The orbit is an ellipse, NOT circular:
    assert sol.eccentricity > 0.05  # e ~ 0.0736
    assert sol.semi_major_axis_km > 7300.0  # a ~ 7404.25 km != 7000 km
    v1_mag = math.sqrt(sol.v1.x**2 + sol.v1.y**2 + sol.v1.z**2)
    assert v1_mag > 7.70  # ~ 7.749 km/s > v_circ (7.546 km/s)


def test_lambert_residual_units_and_physical_meaning():
    """
    Validates the physical meaning and units of the Lambert residual.
    - Residual |F(z)| has units km^1.5 (Curtis universal variable equation).
    - Physical time-of-flight error: Delta_t = residual / sqrt(mu) in seconds.
    - Convergence criterion: residual <= max(tolerance * sqrt(mu) * dt, tolerance).
    """
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]
    dt = 3600.0
    mu = 398600.4418

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, tolerance=1e-7)

    assert sol.converged is True
    assert sol.units["residual"] == "km^1.5"

    # Time residual in seconds
    time_residual_s = sol.residual / math.sqrt(mu)
    assert time_residual_s < 1e-4  # < 0.1 milliseconds error!

    # Scale-aware tolerance check
    scale = math.sqrt(mu) * dt
    tol_scaled = max(1e-7 * scale, 1e-7)
    assert sol.residual <= tol_scaled


def test_lambert_independent_rk4_propagation_verification():
    """
    Independent numerical verification of Lambert solutions using a separate
    Runge-Kutta 4th-order (RK4) two-body orbit propagator.

    Propagates the initial velocity v1 over the flight time dt using:
      d(r)/dt = v
      d(v)/dt = -mu * r / ||r||^3

    Verifies:
    1. Curtis 5.2 (dt = 3600 s, step = 1.0 s):
       Terminal position miss ||r_final - r2|| < 0.01 m (sub-centimeter accuracy).
    2. Long transfer (dt = 72000 s / 20 hours, step = 2.0 s, 36000 steps):
       Terminal position miss ||r_final - r2|| < 7.0 m (specifically reproducing
       and confirming the 6.36 m terminal miss claim over 72,000 s).
    """
    def rk4_propagate(
        r0: Sequence[float],
        v0: Sequence[float],
        dt: float,
        mu: float,
        step_size: float = 1.0,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        def derivs(st: Sequence[float]) -> tuple[float, float, float, float, float, float]:
            rx, ry, rz, vx, vy, vz = st[0], st[1], st[2], st[3], st[4], st[5]
            r_mag = math.sqrt(rx**2 + ry**2 + rz**2)
            factor = -mu / (r_mag**3)
            return (vx, vy, vz, factor * rx, factor * ry, factor * rz)

        state = (r0[0], r0[1], r0[2], v0[0], v0[1], v0[2])
        t = 0.0
        while t < dt:
            h = min(step_size, dt - t)
            k1 = derivs(state)
            s1 = [state[i] + 0.5 * h * k1[i] for i in range(6)]
            k2 = derivs(s1)
            s2 = [state[i] + 0.5 * h * k2[i] for i in range(6)]
            k3 = derivs(s2)
            s3 = [state[i] + h * k3[i] for i in range(6)]
            k4 = derivs(s3)
            ds = [
                state[i] + (h / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
                for i in range(6)
            ]
            state = (ds[0], ds[1], ds[2], ds[3], ds[4], ds[5])
            t += h
        return (state[0], state[1], state[2]), (state[3], state[4], state[5])

    # Case 1: Curtis Example 5.2 (dt = 3600 s)
    r1 = [5000.0, 10000.0, 2100.0]
    r2 = [-14600.0, 2500.0, 7000.0]
    dt1 = 3600.0
    mu = 398600.4418

    sol1 = solve_lambert(r1, r2, dt1, mu_km3_s2=mu, prograde=True)
    v1_vec = (sol1.v1.x, sol1.v1.y, sol1.v1.z)
    r_prop1, _ = rk4_propagate(r1, v1_vec, dt1, mu, step_size=1.0)
    miss_km1 = math.sqrt(sum((r_prop1[i] - r2[i])**2 for i in range(3)))
    miss_meters1 = miss_km1 * 1000.0
    assert miss_meters1 < 0.01  # Less than 10 millimeters!

    # Case 2: 72,000 s transfer (20 hours, 36,000 numerical integration steps)
    dt2 = 72000.0
    sol2 = solve_lambert(r1, r2, dt2, mu_km3_s2=mu, transfer_angle_type="long")
    v2_vec = (sol2.v1.x, sol2.v1.y, sol2.v1.z)
    r_prop2, _ = rk4_propagate(r1, v2_vec, dt2, mu, step_size=2.0)
    miss_km2 = math.sqrt(sum((r_prop2[i] - r2[i])**2 for i in range(3)))
    miss_meters2 = miss_km2 * 1000.0
    # Confirms the ~ 6.36 m terminal miss claim
    assert miss_meters2 < 7.0
    assert pytest.approx(miss_meters2, abs=1.0) == 6.36


def test_vallado_example_5_1_exact():
    """
    Validates against Bate, Mueller, White (1971) / Vallado (4th ed., Example 5.1):
    r1 = [1591.80, 6241.42, 0.0] km
    r2 = [13210.0, 16000.0, 0.0] km
    dt = 2700.0 s (45 minutes)
    mu = 398600.4418 km^3/s^2 (Earth)

    Exact numerical solution:
    v1 = [-4.2411, -10.1603, 0.0] km/s
    v2 = [3.4176, 4.9189, 0.0] km/s
    """
    r1 = [1591.80, 6241.42, 0.0]
    r2 = [13210.0, 16000.0, 0.0]
    dt = 2700.0
    mu = 398600.4418

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu, prograde=True)

    assert sol.converged is True
    assert pytest.approx(sol.v1.x, abs=1e-3) == -4.2411
    assert pytest.approx(sol.v1.y, abs=1e-3) == -10.1603
    assert pytest.approx(sol.v1.z, abs=1e-5) == 0.0

    assert pytest.approx(sol.v2.x, abs=1e-3) == 3.4176
    assert pytest.approx(sol.v2.y, abs=1e-3) == 4.9189
    assert pytest.approx(sol.v2.z, abs=1e-5) == 0.0


def test_exact_parabolic_transfer_barker_equation():
    """
    Independently validates an exact parabolic trajectory (e = 1.0, z = 0.0)
    using Barker's analytical equation for parabolic motion:
      dt = 0.5 * sqrt(p^3 / mu) * (B2 + B2^3 / 3 - B1 - B1^3 / 3)
    where B = tan(nu / 2).

    Setup:
      mu = 398600.4418 km^3/s^2 (Earth)
      p = 14000.0 km (semi-latus rectum), periapsis rp = p / 2 = 7000.0 km
      At true anomaly nu1 = 0 deg: r1 = [7000.0, 0.0, 0.0] km, B1 = 0
      At true anomaly nu2 = 90 deg: r2 = [0.0, 14000.0, 0.0] km, B2 = tan(45 deg) = 1.0
      dt = 0.5 * sqrt(14000^3 / 398600.4418) * (1 + 1/3) = 1749.1695426 s

    Verifies:
      - Solves to exact parabolic root z = 0.0
      - Eccentricity e = 1.0 (within 1e-8)
      - Semi-major axis = inf
      - Converges within 2 iterations with residual < 1e-7
    """
    mu_earth = 398600.4418
    p = 14000.0
    dt_parabolic = 0.5 * math.sqrt(p**3 / mu_earth) * (4.0 / 3.0)

    r1 = [7000.0, 0.0, 0.0]
    r2 = [0.0, 14000.0, 0.0]

    sol = solve_lambert(
        r1=r1,
        r2=r2,
        time_of_flight_s=dt_parabolic,
        mu_km3_s2=mu_earth,
        prograde=True,
    )

    assert sol.converged is True
    assert sol.iterations <= 2
    assert pytest.approx(sol.stumpff_z, abs=1e-8) == 0.0
    assert pytest.approx(sol.eccentricity, abs=1e-8) == 1.0
    assert math.isinf(sol.semi_major_axis_km)
    assert sol.residual < 1e-7


def test_near_parabolic_elliptical_and_hyperbolic_transfers():
    """
    Validates solver stability and branch selection in the immediate vicinity
    of the parabolic boundary (z = 0):
    1. Slower transfer (dt = dt_parabolic + 5 s): elliptic branch, z > 0, e < 1.0
    2. Faster transfer (dt = dt_parabolic - 5 s): hyperbolic branch, z < 0, e > 1.0
    """
    mu_earth = 398600.4418
    p = 14000.0
    dt_parabolic = 0.5 * math.sqrt(p**3 / mu_earth) * (4.0 / 3.0)

    r1 = [7000.0, 0.0, 0.0]
    r2 = [0.0, 14000.0, 0.0]

    # Elliptic near-parabolic
    sol_ell = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt_parabolic + 5.0, mu_km3_s2=mu_earth)
    assert sol_ell.converged is True
    assert sol_ell.stumpff_z > 0.0
    assert 0.99 < sol_ell.eccentricity < 1.0
    assert sol_ell.semi_major_axis_km > 0.0

    # Hyperbolic near-parabolic
    sol_hyp = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt_parabolic - 5.0, mu_km3_s2=mu_earth)
    assert sol_hyp.converged is True
    assert sol_hyp.stumpff_z < 0.0
    assert 1.0 < sol_hyp.eccentricity < 1.01
    assert sol_hyp.semi_major_axis_km < 0.0


def test_very_short_tof_small_angle_transfer():
    """
    Validates solver behavior for very short flight times with small angular separation:
    dt = 10.0 s, delta_nu = 0.5 deg.
    Verifies rapid convergence without numerical divergence or false collinearity detection.
    """
    mu_earth = 398600.4418
    r1 = [7000.0, 0.0, 0.0]
    rad = math.radians(0.5)
    r2 = [7000.0 * math.cos(rad), 7000.0 * math.sin(rad), 0.0]
    dt = 10.0

    sol = solve_lambert(r1=r1, r2=r2, time_of_flight_s=dt, mu_km3_s2=mu_earth)
    assert sol.converged is True
    assert sol.iterations <= 6
    v1_mag = math.sqrt(sol.v1.x**2 + sol.v1.y**2 + sol.v1.z**2)
    assert pytest.approx(v1_mag, rel=0.05) == 6.108
