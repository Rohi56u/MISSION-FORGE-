"""
Physical, Astronomical, and Aerospace Constants
All constants in SI units with authoritative sources and traceability.
"""

from typing import Final

# Fundamental Physical Constants (CODATA 2018 / NIST / BIPM)
STANDARD_GRAVITY: Final[float] = 9.80665
"""Standard acceleration of gravity g_0 in m/s^2 (3rd CGPM, 1901)."""

SPEED_OF_LIGHT: Final[float] = 299_792_458.0
"""Vacuum speed of light c in m/s (17th CGPM, 1983)."""

BOLTZMANN_CONSTANT: Final[float] = 1.380649e-23
"""Boltzmann constant k_B in J/K (26th CGPM, 2019)."""

# Astronomical Constants (IAU / NASA Planetary Fact Sheets)
ASTRONOMICAL_UNIT_M: Final[float] = 149_597_870_700.0
"""1 Astronomical Unit (AU) in meters (IAU 2012 Resolution B2)."""

SOLAR_CONSTANT_1AU: Final[float] = 1361.0
"""
Nominal Total Solar Irradiance (TSI) at 1 AU in W/m^2.
Source: Kopp & Lean (2011) / IAU 2015 Resolution B3 nominal solar irradiance.
Note: Older standard ASTM E490-00a specifies 1366.1 W/m^2. Modern satellite
radiometry (NASA SORCE/TIM) establishes the baseline as 1361.0 +/- 0.5 W/m^2.
Solar irradiance varies ~0.1% over the 11-year solar cycle.
"""

# Target Body Average Distances from Sun (in Astronomical Units)
BODY_DISTANCES_AU: Final[dict[str, float]] = {
    "SUN": 0.0,
    "MERCURY": 0.387,
    "VENUS": 0.723,
    "EARTH": 1.000,
    "MOON": 1.000,
    "MARS": 1.524,
    "CERES": 2.767,
    "PSYCHE": 2.921,
    "JUPITER": 5.204,
    "EUROPA": 5.204,
    "GANYMEDE": 5.204,
    "SATURN": 9.582,
    "TITAN": 9.582,
    "ENCELADUS": 9.582,
    "URANUS": 19.201,
    "NEPTUNE": 30.047,
    "PLUTO": 39.482,
}

# Radioisotope Thermoelectric Constants
PU238_HALF_LIFE_YEARS: Final[float] = 87.7
"""Plutonium-238 alpha decay half-life in years (NNDC NuDat 3.0)."""

PU238_DECAY_RATE_ANNUAL: Final[float] = 0.007904
"""Annual fractional radioactive decay rate lambda = ln(2) / 87.7 yr."""

TYPICAL_THERMOCOUPLE_DECAY_RATE: Final[float] = 0.008
"""
Nominal annual thermocouple degradation rate (~0.8%/year) for PbTe/TAGS
thermoelectric couples as observed on flight MMRTGs (MSL Curiosity).
This is an empirical engineering scenario, not a universal constant.
"""

# Deep Space Network (DSN) Ground Station Constants
DSN_ANTENNA_DIAMETER_M: Final[float] = 70.0
"""DSN 70-meter parabolic dish aperture diameter in meters (DSS-14/63/43)."""

DSN_SYSTEM_NOISE_TEMP_K: Final[float] = 20.0
"""Cryogenically cooled LNA equivalent noise temperature in Kelvin (DSN 810-005)."""

# Standard Frequency Bands in Hz (Space Operations)
FREQUENCY_BANDS_HZ: Final[dict[str, float]] = {
    "S_BAND": 2.295e9,
    "X_BAND": 8.425e9,
    "KA_BAND": 32.05e9,
    "OPTICAL": 1.934e14,
}
