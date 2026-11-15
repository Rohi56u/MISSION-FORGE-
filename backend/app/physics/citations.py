"""
Authoritative Scientific and Engineering Citations for Mission Forge
NASA Space Apps Challenge 2026

This module provides traceability, source provenance, and exact claims supported
for all physics constants, standards, and engineering models used in Mission Forge.
"""

from typing import Dict, Any, Final

SCIENTIFIC_CITATIONS: Final[Dict[str, Dict[str, Any]]] = {
    "SOLAR_IRRADIANCE_1AU": {
        "title": "A new, lower value of total solar irradiance: Evidence and climate significance",
        "authors": "Kopp, G. and Lean, J. L.",
        "publication": "Geophysical Research Letters, Vol. 38, L01706",
        "year": 2011,
        "doi": "10.1029/2011GL047513",
        "url": "https://doi.org/10.1029/2011GL047513",
        "reaffirmed_by": "IAU 2015 Resolution B3 on Recommended Nominal Conversion Constants",
        "value": 1361.0,
        "unit": "W/m^2",
        "notes": (
            "Total solar irradiance at 1 AU based on SORCE/TIM radiometry. "
            "Replaces older solar constants such as ASTM E490-00a which specified 1366.1 W/m^2. "
            "Actual solar irradiance varies ~0.1% over the 11-year solar cycle."
        ),
        "access_date": "2026-11-14",
    },
    "STANDARD_GRAVITY": {
        "title": "CODATA Recommended Values of the Fundamental Physical Constants",
        "organization": "NIST / CODATA",
        "year": 2018,
        "url": "https://physics.nist.gov/cuu/Constants/",
        "value": 9.80665,
        "unit": "m/s^2",
        "notes": "Standard acceleration of gravity g_0 by international convention (CGPM 1901).",
        "access_date": "2026-11-14",
    },
    "SPEED_OF_LIGHT": {
        "title": "Resolution 1 of the 17th CGPM",
        "organization": "BIPM / CGPM",
        "year": 1983,
        "url": "https://www.bipm.org/en/committees/cg/cgpm/17-1983/resolution-1",
        "value": 299792458.0,
        "unit": "m/s",
        "notes": "Exact defined speed of light in vacuum.",
        "access_date": "2026-11-14",
    },
    "BOLTZMANN_CONSTANT": {
        "title": "Resolution 1 of the 26th CGPM",
        "organization": "BIPM / CGPM (SI Redefinition)",
        "year": 2019,
        "url": "https://www.bipm.org/en/committees/cg/cgpm/26-2018/resolution-1",
        "value": 1.380649e-23,
        "unit": "J/K",
        "notes": "Exact defined Boltzmann constant k_B.",
        "access_date": "2026-11-14",
    },
    "ASTRONOMICAL_UNIT": {
        "title": "Resolution B2 on the re-definition of the astronomical unit of length",
        "organization": "International Astronomical Union (IAU)",
        "year": 2012,
        "url": "https://www.iau.org/static/resolutions/IAU2012_English.pdf",
        "value": 149597870700.0,
        "unit": "m",
        "notes": "Exact defined distance of 1 Astronomical Unit (AU).",
        "access_date": "2026-11-14",
    },
    "PU238_HALF_LIFE": {
        "title": "NuDat 3.0 Nuclear Structure and Decay Data",
        "organization": "National Nuclear Data Center, Brookhaven National Laboratory",
        "year": 2023,
        "url": "https://www.nndc.bnl.gov/nudat3/",
        "value": 87.7,
        "unit": "years",
        "notes": "Half-life of Plutonium-238 alpha decay to Uranium-234.",
        "access_date": "2026-11-14",
    },
    "MMRTG_DEGRADATION_MODEL": {
        "title": "Multi-Mission Radioisotope Thermoelectric Generator (MMRTG) Overview",
        "organization": "NASA / US Department of Energy Radioisotope Power Systems",
        "url": "https://rps.nasa.gov/power-and-thermal-systems/radioisotope-power-systems/mmrtg/",
        "notes": (
            "MMRTG BOL power is ~110 W electrical from ~2000 W thermal (~5.5% efficiency). "
            "Power output decreases due to two distinct physical mechanisms: "
            "(1) Isotopic decay of Pu-238 (~0.787%/yr from 87.7 yr half-life), and "
            "(2) Thermoelectric material degradation of PbTe/TAGS couples "
            "(~0.8%/yr empirical on MSL/Perseverance). "
            "This empirical model is an engineering planning scenario, not a universal constant."
        ),
        "access_date": "2026-11-14",
    },
    "POWER_MARGIN_STANDARD": {
        "title": "NASA Systems Engineering Handbook (NASA/SP-2016-6105 Rev 2)",
        "organization": "National Aeronautics and Space Administration (NASA)",
        "year": 2016,
        "url": "https://www.nasa.gov/connect/ebooks/nasa-systems-engineering-handbook",
        "cross_reference": "GSFC-STD-1000 (Gold Rules), Rule 1.05 / 1.06 Electrical Power Margins",
        "notes": (
            "Power margins are engineering guidelines that evolve with lifecycle phase: "
            "Phase A: 25-30%, Phase B: 15-20%, Phase C/D: 10-15%. "
            "NASA-HDBK-4008 is a PLD handbook and does NOT govern power margins. "
            "Mission Forge treats 15% as a configurable engineering design assumption."
        ),
        "access_date": "2026-11-14",
    },
    "MULTI_THRUSTER_EFFECTIVE_ISP": {
        "title": "Space Propulsion Analysis and Design",
        "authors": "Humble, R. W., Henry, G. N., and Larson, W. J.",
        "publisher": "McGraw-Hill",
        "year": 1995,
        "isbn": "978-0070313200",
        "url": "https://openlibrary.org/books/OL1079366M/Space_propulsion_analysis_and_design",
        "formula": "Isp_eff = sum(F_i) / sum(F_i / Isp_i)",
        "notes": (
            "Derived from total thrust F_tot = sum(F_i) and total mass flow rate "
            "m_dot_tot = sum(F_i / (g0 * Isp_i)). Valid only for thrusters operating "
            "simultaneously in compatible propellant/firing modes."
        ),
        "access_date": "2026-11-14",
    },
    "DSN_TELECOM_STANDARDS": {
        "title": "DSN Telecommunications Link Design Handbook (810-005)",
        "organization": "NASA Jet Propulsion Laboratory (JPL)",
        "url": "https://deepspace.jpl.nasa.gov/dsndocs/810-005/",
        "modules": ["Module 101 (70-m Subnet)", "Module 104 (34-m BWG Subnet)"],
        "notes": "Standard RF carrier frequencies, dish gains, system noise temperatures for DSN.",
        "access_date": "2026-11-14",
    },
}
