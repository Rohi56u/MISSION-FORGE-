"""
Physics engine exports — key functions from each physics sub-module.
"""

from backend.app.physics.propulsion import (
    tsiolkovsky_delta_v,
    propellant_mass_required,
    electric_propulsion_power,
    compare_propulsion_technologies,
    calculate_multithruster_effective_isp,
    calculate_staged_propulsion_systems,
    ThrusterOperatingSpec,
)
from backend.app.physics.power import (
    solar_irradiance,
    solar_array_power,
    mmrtg_power_at_time,
    evaluate_power_balance,
)
from backend.app.physics.telecom import (
    free_space_path_loss_db,
    parabolic_antenna_gain_dbi,
    deep_space_link_budget,
    round_trip_light_time_seconds,
)
from backend.app.physics.swapc import calculate_swapc

__all__ = [
    "tsiolkovsky_delta_v",
    "propellant_mass_required",
    "electric_propulsion_power",
    "compare_propulsion_technologies",
    "calculate_multithruster_effective_isp",
    "calculate_staged_propulsion_systems",
    "ThrusterOperatingSpec",
    "solar_irradiance",
    "solar_array_power",
    "mmrtg_power_at_time",
    "evaluate_power_balance",
    "free_space_path_loss_db",
    "parabolic_antenna_gain_dbi",
    "deep_space_link_budget",
    "round_trip_light_time_seconds",
    "calculate_swapc",
]
