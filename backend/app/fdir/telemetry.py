"""
Telemetry Ingestion, Provenance Attribution, and Quality Classification
Mission Forge — Phase 5
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TelemetryProvenanceType(str, Enum):
    """Rigorous classification of telemetry data origin."""
    LIVE_SATELLITE = "LIVE_SATELLITE"
    GROUND_NETWORK = "GROUND_NETWORK"  # e.g. DSN station status/carrier
    CACHED = "CACHED"
    SIMULATED_SCENARIO = "SIMULATED_SCENARIO"
    FIXTURE = "FIXTURE"


class TelemetryQuality(str, Enum):
    """Validity and freshness indicators for sensor measurements."""
    GOOD = "GOOD"
    SUSPECT = "SUSPECT"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class TelemetrySubsystem(str, Enum):
    """Spacecraft subsystems evaluated by FDIR."""
    POWER = "POWER"
    THERMAL = "THERMAL"
    PROPULSION = "PROPULSION"
    COMMUNICATIONS = "COMMUNICATIONS"
    GNC_ATTITUDE = "GNC_ATTITUDE"


class TelemetryReading(BaseModel):
    """Typed sensor measurement with explicit provenance, mission identity, and quality metadata."""
    subsystem: TelemetrySubsystem
    metric_name: str
    value: Optional[float] = None
    unit: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    provenance: TelemetryProvenanceType
    quality: TelemetryQuality = TelemetryQuality.GOOD
    room_id: Optional[str] = None
    mission_id: Optional[str] = None
    spacecraft_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def convert_dsn_feed_to_telemetry(
    dsn_data: Any,
    mission_id: Optional[str] = None,
    spacecraft_id: Optional[str] = None,
) -> List[TelemetryReading]:
    """
    Extracts genuine ground-network communications telemetry from NASA DSN Now data.
    Supports DSNFeedResponse models or raw dictionaries with 'stations' or 'dishes'.
    IMPORTANT NOTE: DSN Now is a ground station tracking feed. It provides carrier locks,
    uplink/downlink status, dish pointing, and RTLT. It does NOT provide internal
    spacecraft temperatures, wheel speeds, or bus voltages.
    """
    readings: List[TelemetryReading] = []
    now = datetime.now(timezone.utc)

    # Convert Pydantic model to dict if needed
    if hasattr(dsn_data, "model_dump"):
        data = dsn_data.model_dump()
    elif isinstance(dsn_data, dict):
        data = dsn_data
    else:
        return readings

    # 1. Handle nested 'stations' structure (real DSN feed)
    all_dishes: List[Dict[str, Any]] = []
    if "stations" in data and isinstance(data["stations"], list):
        for station in data["stations"]:
            if isinstance(station, dict):
                st_dishes = station.get("dishes", [])
                st_name = station.get("name", "")
                for d in st_dishes:
                    if isinstance(d, dict):
                        d_copy = dict(d)
                        d_copy["_station"] = st_name
                        all_dishes.append(d_copy)
    # 2. Handle flat 'dishes' structure (fixtures / legacy)
    elif "dishes" in data and isinstance(data["dishes"], list):
        all_dishes = data["dishes"]

    for dish in all_dishes:
        if not isinstance(dish, dict):
            continue
        dish_name = dish.get("name", "DSN_DISH")

        # Check for legacy single-dict signals
        if "down_signal" in dish and isinstance(dish["down_signal"], dict):
            down_dict = dish["down_signal"]
            down_lock = down_dict.get("carrier_lock", False) or down_dict.get("active", False)
            down_freq = down_dict.get("frequency_hz")
            readings.append(
                TelemetryReading(
                    subsystem=TelemetrySubsystem.COMMUNICATIONS,
                    metric_name=f"{dish_name}_downlink_carrier_lock",
                    value=1.0 if down_lock else 0.0,
                    unit="boolean",
                    timestamp=now,
                    source=f"DSN_{dish_name}",
                    provenance=TelemetryProvenanceType.GROUND_NETWORK,
                    quality=TelemetryQuality.GOOD,
                    mission_id=mission_id,
                    spacecraft_id=spacecraft_id,
                    metadata={"frequency_hz": down_freq},
                )
            )

        # Check for real DSN feed down_signals list
        down_signals = dish.get("down_signals", [])
        if isinstance(down_signals, list):
            for idx, sig in enumerate(down_signals):
                if isinstance(sig, dict):
                    is_active = sig.get("active", False)
                    sc_target = sig.get("spacecraft") or spacecraft_id
                    freq = sig.get("frequency_hz")
                    pwr = sig.get("power_dbm_or_kw")
                    rate = sig.get("data_rate_bps")
                    readings.append(
                        TelemetryReading(
                            subsystem=TelemetrySubsystem.COMMUNICATIONS,
                            metric_name=f"{dish_name}_down_signal_{idx}_carrier_active",
                            value=1.0 if is_active else 0.0,
                            unit="boolean",
                            timestamp=now,
                            source=f"DSN_{dish_name}",
                            provenance=TelemetryProvenanceType.GROUND_NETWORK,
                            quality=TelemetryQuality.GOOD,
                            mission_id=mission_id,
                            spacecraft_id=sc_target,
                            metadata={
                                "frequency_hz": freq,
                                "power_dbm": pwr,
                                "data_rate_bps": rate,
                                "band": sig.get("band"),
                            },
                        )
                    )

        # Check for target tracking RTLT and range distance
        targets = dish.get("targets", [])
        if isinstance(targets, list):
            for tgt in targets:
                if isinstance(tgt, dict):
                    t_name = tgt.get("name", "TARGET")
                    rtlt = tgt.get("rtlt_seconds")
                    if rtlt is not None and rtlt > 0:
                        readings.append(
                            TelemetryReading(
                                subsystem=TelemetrySubsystem.COMMUNICATIONS,
                                metric_name=f"{dish_name}_{t_name}_rtlt_s",
                                value=float(rtlt),
                                unit="s",
                                timestamp=now,
                                source=f"DSN_{dish_name}",
                                provenance=TelemetryProvenanceType.GROUND_NETWORK,
                                quality=TelemetryQuality.GOOD,
                                mission_id=mission_id,
                                spacecraft_id=t_name,
                                metadata={
                                    "target": t_name,
                                    "range_km": tgt.get("downleg_range_km"),
                                },
                            )
                        )

    return readings


def create_simulated_scenario(scenario_id: str) -> List[TelemetryReading]:
    """
    Generates explicitly labelled test scenarios for FDIR verification.
    NEVER masquerades as live satellite telemetry.
    """
    now = datetime.now(timezone.utc)
    readings: List[TelemetryReading] = []

    if scenario_id == "POWER_DEFICIT":
        # Critical power failure: bus voltage drop and negative generation balance
        readings.extend([
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="bus_voltage_v",
                value=21.4,  # Below 24V threshold
                unit="V",
                timestamp=now,
                source="SIM_POWER_BUS_A",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="battery_charge_percent",
                value=28.5,  # Below 30% critical
                unit="%",
                timestamp=now,
                source="SIM_BATTERY_MGMT",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="power_generation_w",
                value=120.0,
                unit="W",
                timestamp=now,
                source="SIM_SOLAR_ARRAY",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="power_draw_w",
                value=250.0,
                unit="W",
                timestamp=now,
                source="SIM_PDU",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
        ])

    elif scenario_id == "THERMAL_EXCEEDANCE":
        # Avionics thermal runaway
        readings.extend([
            TelemetryReading(
                subsystem=TelemetrySubsystem.THERMAL,
                metric_name="component_temp_c",
                value=88.5,  # Exceeds 85C critical max
                unit="degC",
                timestamp=now,
                source="SIM_THERMAL_SENSOR_BAY_1",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.THERMAL,
                metric_name="total_dose_rad",
                value=150_000.0,  # Exceeds 100k rad
                unit="rad",
                timestamp=now,
                source="SIM_RAD_DOSIMETER",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
        ])

    elif scenario_id == "COMM_BLACKOUT":
        # Lost carrier lock and high time since last contact
        readings.extend([
            TelemetryReading(
                subsystem=TelemetrySubsystem.COMMUNICATIONS,
                metric_name="carrier_lock",
                value=0.0,  # Lost lock
                unit="boolean",
                timestamp=now,
                source="SIM_TRANSPONDER_X_BAND",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.COMMUNICATIONS,
                metric_name="downlink_snr_db",
                value=-4.2,  # Negative SNR
                unit="dB",
                timestamp=now,
                source="SIM_TRANSPONDER_X_BAND",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.COMMUNICATIONS,
                metric_name="time_since_last_contact_s",
                value=92_000.0,  # Over 24 hours
                unit="s",
                timestamp=now,
                source="SIM_COMMS_SCHEDULE",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
        ])

    elif scenario_id == "WHEEL_SATURATION":
        # Reaction wheel exceeding 5500 RPM
        readings.extend([
            TelemetryReading(
                subsystem=TelemetrySubsystem.GNC_ATTITUDE,
                metric_name="reaction_wheel_rpm_x",
                value=5720.0,
                unit="rpm",
                timestamp=now,
                source="SIM_RWA_WHEEL_1",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.GNC_ATTITUDE,
                metric_name="reaction_wheel_rpm_y",
                value=4200.0,
                unit="rpm",
                timestamp=now,
                source="SIM_RWA_WHEEL_2",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
        ])

    elif scenario_id == "PROPULSION_SHORTFALL":
        # Low Delta-V and tank pressure
        readings.extend([
            TelemetryReading(
                subsystem=TelemetrySubsystem.PROPULSION,
                metric_name="available_delta_v_mps",
                value=2800.0,  # Below 3800 required
                unit="m/s",
                timestamp=now,
                source="SIM_PROP_CALC",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.PROPULSION,
                metric_name="required_delta_v_mps",
                value=3800.0,
                unit="m/s",
                timestamp=now,
                source="SIM_MISSION_PLAN",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.PROPULSION,
                metric_name="tank_pressure_bar",
                value=8.5,  # Below 12 bar operating limit
                unit="bar",
                timestamp=now,
                source="SIM_PRESSURE_TRANSDUCER_1",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
        ])

    elif scenario_id == "NOMINAL_CRUISE":
        # All subsystems fully within operating limits
        readings.extend([
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="bus_voltage_v",
                value=28.1,
                unit="V",
                timestamp=now,
                source="SIM_POWER_BUS_A",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="battery_charge_percent",
                value=94.0,
                unit="%",
                timestamp=now,
                source="SIM_BATTERY_MGMT",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="power_generation_w",
                value=420.0,
                unit="W",
                timestamp=now,
                source="SIM_SOLAR_ARRAY",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="power_draw_w",
                value=280.0,
                unit="W",
                timestamp=now,
                source="SIM_PDU",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.THERMAL,
                metric_name="component_temp_c",
                value=22.0,
                unit="degC",
                timestamp=now,
                source="SIM_THERMAL_SENSOR_BAY_1",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.COMMUNICATIONS,
                metric_name="carrier_lock",
                value=1.0,
                unit="boolean",
                timestamp=now,
                source="SIM_TRANSPONDER_X_BAND",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.COMMUNICATIONS,
                metric_name="downlink_snr_db",
                value=8.4,
                unit="dB",
                timestamp=now,
                source="SIM_TRANSPONDER_X_BAND",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.COMMUNICATIONS,
                metric_name="time_since_last_contact_s",
                value=120.0,
                unit="s",
                timestamp=now,
                source="SIM_COMMS_SCHEDULE",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.PROPULSION,
                metric_name="available_delta_v_mps",
                value=4150.0,
                unit="m/s",
                timestamp=now,
                source="SIM_PROP_CALC",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.PROPULSION,
                metric_name="required_delta_v_mps",
                value=3800.0,
                unit="m/s",
                timestamp=now,
                source="SIM_MISSION_PLAN",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
            TelemetryReading(
                subsystem=TelemetrySubsystem.GNC_ATTITUDE,
                metric_name="reaction_wheel_rpm_x",
                value=1850.0,
                unit="rpm",
                timestamp=now,
                source="SIM_RWA_WHEEL_1",
                provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
                quality=TelemetryQuality.GOOD,
            ),
        ])

    return readings
