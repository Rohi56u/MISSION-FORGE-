"""
Authoritative Component Catalog Seeding Script
Populates verified flight-proven components into the Mission Forge database
with field-level source provenance.

Idempotency & Non-Destructive Update:
  - Checks existing component names before inserting.
  - Does NOT delete or overwrite user records.
  - Updates field_provenance on existing seeded records if previously unpopulated.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal, engine
from backend.app.core.provenance import compute_payload_hash
from backend.app.models.component import (
    Component,
    SubsystemType,
    VerificationStatus,
)

_MMRTG_URL = "https://rps.nasa.gov/power-and-thermal-systems/radioisotope-power-systems/mmrtg/"
_DESCANSO_URL = "https://descanso.jpl.nasa.gov/monograph/series2/Descanso2_all.pdf"

# Authoritative flight hardware catalog with verified specifications and field-level provenance
VERIFIED_SEED_COMPONENTS: List[Dict[str, Any]] = [
    {
        "name": "NASA NEXT-C Gridded Ion Thruster",
        "subsystem": SubsystemType.PROPULSION,
        "description": (
            "NASA's Evolutionary Xenon Thruster - Commercial (NEXT-C) gridded ion propulsion "
            "system developed by NASA Glenn Research Center and Aerojet Rocketdyne. "
            "Flight demonstrated on the NASA DART mission (2022)."
        ),
        "mass_kg": 13.5,  # Thruster body dry mass per NASA/TM-2010-216772
        "power_draw_w": 7200.0,  # Peak throttling input power (operating range 0.54 - 7.2 kW)
        "power_generation_w": 0.0,
        "cost_usd": 0.0,  # Cost withheld / not published in unclassified NASA baseline
        "isp_seconds": 4190.0,  # Max specific impulse (operating range 1400 - 4190 s)
        "thrust_newtons": 0.236,  # Nominal peak thrust: 236 mN
        "propellant_type": "Xenon",
        "trl": 9,
        "flight_heritage": "NASA DART (Double Asteroid Redirection Test, 2022)",
        "source_url": "https://ntrs.nasa.gov/citations/20100021677",
        "source_system": "NASA_NTRS",
        "verification_status": VerificationStatus.VERIFIED_AUTHORITATIVE,
        "specifications": {
            "beam_diameter_cm": 36.0,
            "max_input_power_kw": 7.2,
            "min_input_power_kw": 0.54,
            "qualification_status": "Flight proven",
        },
        "field_provenance": {
            "mass_kg": {
                "source_system": "NASA_NTRS",
                "citation": "NASA/TM-2010-216772 Table 2",
                "canonical_url": "https://ntrs.nasa.gov/citations/20100021677",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Thruster mechanical assembly dry mass (13.5 kg nominal)",
            },
            "isp_seconds": {
                "source_system": "NASA_NTRS",
                "citation": "NASA/TM-2010-216772 Table 1",
                "canonical_url": "https://ntrs.nasa.gov/citations/20100021677",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Maximum specific impulse at high-power throttling point (4190 s)",
            },
            "thrust_newtons": {
                "source_system": "NASA_NTRS",
                "citation": "NASA/TM-2010-216772",
                "canonical_url": "https://ntrs.nasa.gov/citations/20100021677",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Peak thrust output of 236 mN at 7.2 kW throttle level",
            },
            "power_draw_w": {
                "source_system": "NASA_NTRS",
                "citation": "NASA/TM-2010-216772",
                "canonical_url": "https://ntrs.nasa.gov/citations/20100021677",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Peak power processing unit input load (7200 W)",
            },
            "trl": {
                "source_system": "NASA_DART_MISSION",
                "citation": "NASA Planetary Defense Coordination Office DART Results",
                "canonical_url": "https://www.nasa.gov/planetary-defense/dart",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": (
                    "TRL 9 achieved following operational deep-space demonstration on DART (2022)"
                ),
            },
        },
        "is_active": True,
    },
    {
        "name": "NASA/DOE Multi-Mission Radioisotope Thermoelectric Generator (MMRTG)",
        "subsystem": SubsystemType.POWER,
        "description": (
            "Space radioisotope power system developed by the US Department of Energy and NASA. "
            "Converts decay heat from Plutonium-238 dioxide (PuO2) into electricity using "
            "PbTe/TAGS thermoelectric couples."
        ),
        "mass_kg": 44.0,  # Nominal system dry mass per NASA/DOE fact sheet
        "power_draw_w": 0.0,
        "power_generation_w": 110.0,  # Beginning-of-life electrical power output
        "cost_usd": 0.0,  # Government furnished equipment; no standard commercial price
        "decay_rate_annual": 0.008,  # ~0.8%/year empirical thermocouple degradation
        "trl": 9,
        "flight_heritage": (
            "Mars Science Laboratory (Curiosity, 2011), Mars 2020 (Perseverance, 2020)"
        ),
        "source_url": (
            "https://rps.nasa.gov/power-and-thermal-systems/radioisotope-power-systems/mmrtg/"
        ),
        "source_system": "DOE_NASA_RPS",
        "verification_status": VerificationStatus.VERIFIED_AUTHORITATIVE,
        "specifications": {
            "thermal_power_bol_w": 2000.0,
            "electrical_efficiency_bol_percent": 5.5,
            "isotope": "Plutonium-238",
            "fuel_mass_puo2_kg": 4.8,
            "design_life_years": 14.0,
        },
        "field_provenance": {
            "mass_kg": {
                "source_system": "DOE_NASA_RPS",
                "citation": "NASA RPS MMRTG Technical Specification Sheet",
                "canonical_url": _MMRTG_URL,
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "System mass including thermoelectric converter and casing (44 kg)",
            },
            "power_generation_w": {
                "source_system": "DOE_NASA_RPS",
                "citation": "NASA RPS MMRTG Technical Specification Sheet",
                "canonical_url": _MMRTG_URL,
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Nominal electrical output beginning-of-life (~110 W electric)",
            },
            "decay_rate_annual": {
                "source_system": "NASA_JPL",
                "citation": "Curiosity and Perseverance telemetry analysis (JPL/DOE)",
                "canonical_url": "https://rps.nasa.gov",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": (
                    "Empirical coupled isotopic decay + thermocouple degradation rate "
                    "(~0.8% per year)"
                ),
            },
            "trl": {
                "source_system": "NASA_JPL",
                "citation": "MSL Curiosity & Mars 2020 Mission Heritage",
                "canonical_url": "https://mars.nasa.gov/msl/",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": (
                    "TRL 9 flight-proven on Martian surface across >10 years continuous operation"
                ),
            },
        },
        "is_active": True,
    },
    {
        "name": "UltraFlex Circular Solar Array (2.1m Diameter)",
        "subsystem": SubsystemType.POWER,
        "description": (
            "High specific power, ultra-lightweight deployable accordion-style circular "
            "photovoltaic solar array developed by Northrop Grumman Space Systems."
        ),
        "mass_kg": 8.5,  # Dry mass per 2.1 m wing
        "power_draw_w": 0.0,
        "power_generation_w": 0.0,  # Derived dynamically from solar flux and area
        "cost_usd": 0.0,
        "solar_area_m2": 3.46,  # Circular aperture area pi * (1.05)^2 m^2
        "solar_efficiency": 0.30,  # Triple-junction GaInP/GaAs/Ge cells (~30% AM0)
        "trl": 9,
        "flight_heritage": "Mars Phoenix Lander (2007), Mars InSight Lander (2018), Orion EFT-1",
        "source_url": "https://www.northropgrumman.com/space/ultraflex-solar-array",
        "source_system": "NORTHROP_GRUMMAN_SPACE",
        "verification_status": VerificationStatus.VERIFIED_AUTHORITATIVE,
        "specifications": {
            "aperture_diameter_m": 2.1,
            "specific_power_w_per_kg": 150.0,
            "stowed_envelope_cm": "10 x 20 x 110",
        },
        "field_provenance": {
            "mass_kg": {
                "source_system": "NORTHROP_GRUMMAN_SPACE",
                "citation": "Northrop Grumman UltraFlex Product Datasheet",
                "canonical_url": "https://www.northropgrumman.com/space/ultraflex-solar-array",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Wing structural and blanket mass for 2.1m diameter wing (8.5 kg)",
            },
            "solar_area_m2": {
                "source_system": "NORTHROP_GRUMMAN_SPACE",
                "citation": "Northrop Grumman UltraFlex Product Datasheet",
                "canonical_url": "https://www.northropgrumman.com/space/ultraflex-solar-array",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Active circular collection area: pi * (1.05)^2 = 3.46 m^2",
            },
            "solar_efficiency": {
                "source_system": "NORTHROP_GRUMMAN_SPACE",
                "citation": "Spectrolab NeXt Triple Junction AM0 standard cell data",
                "canonical_url": "https://www.northropgrumman.com/space/ultraflex-solar-array",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Triple-junction photovoltaic conversion efficiency at 1 AU AM0 (30.0%)",
            },
            "trl": {
                "source_system": "NASA_JPL",
                "citation": "Mars Phoenix (2007) and InSight (2018) Mission Operations",
                "canonical_url": "https://mars.nasa.gov/insight/",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "TRL 9 flight-proven on multiple NASA Mars surface lander missions",
            },
        },
        "is_active": True,
    },
    {
        "name": "JPL Small Deep Space Transponder (SDST)",
        "subsystem": SubsystemType.TELECOM,
        "description": (
            "Multi-band software-configurable deep-space telecommunications transponder "
            "developed by NASA JPL and General Dynamics for interplanetary missions."
        ),
        "mass_kg": 3.0,  # Dry mass in kilograms per JPL SDST documentation
        "power_draw_w": 15.0,  # Receive-only DC consumption (~15 W; up to 30 W full duplex)
        "power_generation_w": 0.0,
        "cost_usd": 0.0,
        "frequency_band": "X_BAND",
        "antenna_diameter_m": None,  # Transponder interfaces to external antenna
        "tx_power_w": 5.0,  # Internal RF exciter drive output
        "trl": 9,
        "flight_heritage": (
            "Deep Space 1 (1998), MRO (2005), Dawn (2007), MSL Curiosity (2011)"
        ),
        "source_url": "https://descanso.jpl.nasa.gov/monograph/series2/Descanso2_all.pdf",
        "source_system": "JPL_DESCANSO",
        "verification_status": VerificationStatus.VERIFIED_AUTHORITATIVE,
        "specifications": {
            "tx_frequency_ghz": 8.4,
            "rx_frequency_ghz": 7.1,
            "modulation": "BPSK / QPSK",
            "coherent_turnaround_ratio": "880/749",
        },
        "field_provenance": {
            "mass_kg": {
                "source_system": "JPL_DESCANSO",
                "citation": "JPL Deep-Space Communications Monograph Series Vol 2, Ch 2",
                "canonical_url": _DESCANSO_URL,
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Integrated chassis dry mass excluding diplexer (3.0 kg)",
            },
            "power_draw_w": {
                "source_system": "JPL_DESCANSO",
                "citation": "JPL Deep-Space Communications Monograph Series Vol 2, Ch 2",
                "canonical_url": _DESCANSO_URL,
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Receiver-only quiescent power consumption (15.0 W)",
            },
            "frequency_band": {
                "source_system": "JPL_DESCANSO",
                "citation": "JPL Deep-Space Communications Monograph Series Vol 2, Ch 2",
                "canonical_url": _DESCANSO_URL,
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "Deep space X-band: uplink 7.1 GHz, downlink 8.4 GHz",
            },
            "trl": {
                "source_system": "NASA_JPL",
                "citation": "Deep Space 1 & MRO Flight Documentation",
                "canonical_url": "https://descanso.jpl.nasa.gov",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "notes": "TRL 9 flight proven across multiple NASA interplanetary missions",
            },
        },
        "is_active": True,
    },
]


async def seed_components(session: AsyncSession) -> Dict[str, int]:
    """
    Seeds verified components into the database idempotently.
    Updates provenance on existing records without overwriting user data.

    Returns:
        Summary dict: {"inserted": count, "updated": count, "skipped": count, "total": total}
    """
    inserted = 0
    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc)

    for item in VERIFIED_SEED_COMPONENTS:
        name = item["name"]
        stmt = select(Component).where(Component.name == name)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Check if field_provenance needs updating on existing record
            needs_update = False
            if not existing.field_provenance or existing.field_provenance == {}:
                existing.field_provenance = item.get("field_provenance", {})
                needs_update = True
            if not existing.source_system:
                existing.source_system = item.get("source_system", "NASA_SEED")
                needs_update = True
            if not existing.raw_source_hash:
                existing.raw_source_hash = compute_payload_hash(item)
                needs_update = True
            if needs_update:
                existing.last_synced_at = now
                updated += 1
            else:
                skipped += 1
        else:
            comp_data = dict(item)
            comp_data["raw_source_hash"] = compute_payload_hash(item)
            comp_data["last_synced_at"] = now
            comp = Component(**comp_data)
            session.add(comp)
            inserted += 1

    if inserted > 0 or updated > 0:
        await session.commit()

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "total": len(VERIFIED_SEED_COMPONENTS),
    }


async def main() -> None:
    """
    CLI entrypoint to seed catalog.
    Assumes database schema has been created via Alembic migrations.
    Never uses create_all() to bypass migrations.
    """
    try:
        async with AsyncSessionLocal() as session:
            summary = await seed_components(session)
            print(
                f"Component Seeding Complete: {summary['inserted']} inserted, "
                f"{summary['updated']} provenance updated, "
                f"{summary['skipped']} already present (total {summary['total']})."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
