"""
Astrodynamics and Trajectory Optimization Package
Mission Forge — Phase 3
Authoritative boundary-value Lambert solvers, ephemeris-driven porkchop analysis,
and mission trajectory optimization services.
"""

from backend.app.astrodynamics.lambert import (
    LambertCollinearError,
    LambertConvergenceError,
    LambertDomainError,
    LambertError,
    LambertSolution,
    solve_lambert,
)
from backend.app.astrodynamics.porkchop import (
    BODY_REGISTRY,
    CelestialBodyInfo,
    PorkchopGenerator,
    PorkchopMinima,
    compute_hyperbolic_burn_delta_v,
    normalize_body_name,
)

__all__ = [
    "LambertError",
    "LambertDomainError",
    "LambertCollinearError",
    "LambertConvergenceError",
    "LambertSolution",
    "solve_lambert",
    "BODY_REGISTRY",
    "CelestialBodyInfo",
    "PorkchopGenerator",
    "PorkchopMinima",
    "compute_hyperbolic_burn_delta_v",
    "normalize_body_name",
]
