"""
Deterministic FDIR Rule Definitions, Hysteresis, and Fault Classifications
Mission Forge — Phase 5
"""

import abc
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.app.fdir.telemetry import (
    TelemetryQuality,
    TelemetryReading,
    TelemetrySubsystem,
)

FDIR_ADVISORY_DISCLAIMER = (
    "ADVISORY NOTICE: Mission Forge FDIR is an engineering simulation and advisory "
    "analysis system. It does not control, command, or interface directly with any "
    "physical spacecraft flight computers or live operational hardware."
)


def _safe_float(
    reading: Optional[TelemetryReading], default: Optional[float] = None
) -> Optional[float]:
    """Extracts valid float metric value if reading is present, non-null, and not invalid/stale."""
    if (
        reading is not None
        and reading.value is not None
        and reading.quality not in (TelemetryQuality.INVALID, TelemetryQuality.STALE)
    ):
        return float(reading.value)
    return default


class FDIRSeverity(str, Enum):
    """Severity classification for FDIR findings."""
    NOMINAL = "NOMINAL"
    CAUTION = "CAUTION"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class FDIRFindingStatus(str, Enum):
    """Operational status of an evaluated condition."""
    NOMINAL = "NOMINAL"
    ACTIVE_ANOMALY = "ACTIVE_ANOMALY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class FDIRFinding(BaseModel):
    """Deterministic, actionable FDIR finding returned by a rule evaluation."""
    rule_id: str
    rule_version: str
    severity: FDIRSeverity
    status: FDIRFindingStatus
    affected_subsystem: TelemetrySubsystem
    input_evidence: Dict[str, Any]
    thresholds: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    explanation: str
    confidence_status: str  # "VERIFIED", "PROVISIONAL", "INSUFFICIENT_DATA"
    triage_guidance: str
    advisory_notice: str = FDIR_ADVISORY_DISCLAIMER


class FDIRRule(abc.ABC):
    """Abstract base class for versioned deterministic FDIR rules with hysteresis."""

    def __init__(
        self,
        rule_id: str,
        rule_version: str,
        subsystem: TelemetrySubsystem,
        thresholds: Optional[Dict[str, float]] = None,
    ) -> None:
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.subsystem = subsystem
        self.thresholds: Dict[str, float] = thresholds or {}
        self.last_severity: FDIRSeverity = FDIRSeverity.NOMINAL
        self.consecutive_severity_count: int = 0

    @abc.abstractmethod
    def evaluate(self, readings: Dict[str, TelemetryReading]) -> FDIRFinding:
        """Evaluates sensor readings deterministically and returns a structured finding."""
        pass


class RulePowerShortfall(FDIRRule):
    """
    FDIR-PWR-001 (v1.2.0): Power Generation Shortfall & Bus Undervoltage.
    Evaluates bus voltage, battery state-of-charge, and generation vs load balance.
    """

    def __init__(self, thresholds: Optional[Dict[str, float]] = None) -> None:
        default_thresholds = {
            "critical_bus_voltage_v": 24.0,
            "critical_battery_pct": 30.0,
            "warning_battery_pct": 50.0,
        }
        if thresholds:
            default_thresholds.update(thresholds)
        super().__init__(
            rule_id="FDIR-PWR-001",
            rule_version="1.2.0",
            subsystem=TelemetrySubsystem.POWER,
            thresholds=default_thresholds,
        )

    def evaluate(self, readings: Dict[str, TelemetryReading]) -> FDIRFinding:
        now = datetime.now(timezone.utc)
        v_reading = readings.get("bus_voltage_v")
        batt_reading = readings.get("battery_charge_percent")
        gen_reading = readings.get("power_generation_w")
        draw_reading = readings.get("power_draw_w")

        bus_v = _safe_float(v_reading)
        batt_pct = _safe_float(batt_reading)
        gen_w = _safe_float(gen_reading, default=0.0) or 0.0
        draw_w = _safe_float(draw_reading, default=0.0) or 0.0

        valid_v = bus_v is not None
        valid_batt = batt_pct is not None
        valid_gen = _safe_float(gen_reading) is not None
        valid_draw = _safe_float(draw_reading) is not None

        missing_fields: List[str] = []
        if not valid_v:
            missing_fields.append("bus_voltage_v")
        if not valid_batt:
            missing_fields.append("battery_charge_percent")

        # If both primary voltage and battery metrics are missing/invalid/stale:
        if not valid_v and not valid_batt:
            if valid_draw and valid_gen and draw_w > gen_w:
                return FDIRFinding(
                    rule_id=self.rule_id,
                    rule_version=self.rule_version,
                    severity=FDIRSeverity.WARNING,
                    status=FDIRFindingStatus.ACTIVE_ANOMALY,
                    affected_subsystem=self.subsystem,
                    input_evidence={
                        "power_generation_w": gen_w,
                        "power_draw_w": draw_w,
                        "missing_fields": missing_fields,
                    },
                    thresholds=self.thresholds,
                    timestamp=now,
                    explanation=(
                        f"WARNING: Power deficit detected "
                        f"(Load {draw_w:.1f} W > Gen {gen_w:.1f} W). "
                        "Bus voltage and battery telemetry missing or invalid."
                    ),
                    confidence_status="PROVISIONAL",
                    triage_guidance=(
                        "Duty-cycle science payloads and restore bus telemetry multiplexer."
                    ),
                )

            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CAUTION,
                status=FDIRFindingStatus.INSUFFICIENT_DATA,
                affected_subsystem=self.subsystem,
                input_evidence={"missing_fields": missing_fields},
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    "Insufficient telemetry: bus voltage and battery telemetry "
                    "missing, stale, or invalid."
                ),
                confidence_status="INSUFFICIENT_DATA",
                triage_guidance=(
                    "Verify telemetry ground station lock and power sensor multiplexer."
                ),
            )

        confidence = "VERIFIED" if (valid_v and valid_batt) else "PROVISIONAL"
        if valid_v and v_reading is not None:
            provenance = v_reading.provenance.value
        elif valid_batt and batt_reading is not None:
            provenance = batt_reading.provenance.value
        else:
            provenance = "UNKNOWN"
        evidence: Dict[str, Any] = {
            "bus_voltage_v": bus_v,
            "battery_charge_percent": batt_pct,
            "power_generation_w": gen_w,
            "power_draw_w": draw_w,
            "provenance": provenance,
        }
        if missing_fields:
            evidence["missing_fields"] = missing_fields

        crit_v = self.thresholds["critical_bus_voltage_v"]
        crit_batt = self.thresholds["critical_battery_pct"]
        warn_batt = self.thresholds["warning_battery_pct"]

        # Critical: severe undervoltage or battery depletion
        is_crit = (
            (bus_v is not None and bus_v < crit_v)
            or (batt_pct is not None and batt_pct < crit_batt)
        )
        if is_crit:
            reasons = []
            if bus_v is not None and bus_v < crit_v:
                reasons.append(f"bus voltage {bus_v:.1f} V < {crit_v:.1f} V")
            if batt_pct is not None and batt_pct < crit_batt:
                reasons.append(f"battery {batt_pct:.1f}% < {crit_batt:.1f}%")
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CRITICAL,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"CRITICAL: Electrical bus undervoltage or battery exhaustion "
                    f"({', '.join(reasons)}). Spacecraft safe-mode imminent."
                ),
                confidence_status=confidence,
                triage_guidance=(
                    "1. Immediately shed non-essential science payload loads. "
                    "2. Orient solar arrays toward Sun vector. 3. Configure batteries for charge."
                ),
            )

        # Warning: negative power margin or low battery
        is_warn = (
            (batt_pct is not None and batt_pct < warn_batt)
            or (draw_w > gen_w and batt_pct is not None and batt_pct < warn_batt)
            or (draw_w > gen_w and valid_draw and valid_gen)
        )
        if is_warn:
            reasons = []
            if draw_w > gen_w:
                reasons.append(f"Load {draw_w:.1f} W > Gen {gen_w:.1f} W")
            if batt_pct is not None and batt_pct < warn_batt:
                reasons.append(f"battery at {batt_pct:.1f}% < {warn_batt:.1f}%")
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.WARNING,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=f"WARNING: Power deficit detected ({'; '.join(reasons)}).",
                confidence_status=confidence,
                triage_guidance="Duty-cycle science payloads and monitor battery discharge rate.",
            )

        nominal_parts = []
        if bus_v is not None:
            nominal_parts.append(f"Bus at {bus_v:.1f} V")
        if batt_pct is not None:
            nominal_parts.append(f"battery at {batt_pct:.1f}%")
        return FDIRFinding(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            severity=FDIRSeverity.NOMINAL,
            status=FDIRFindingStatus.NOMINAL,
            affected_subsystem=self.subsystem,
            input_evidence=evidence,
            thresholds=self.thresholds,
            timestamp=now,
            explanation=f"Power subsystem nominal. {', '.join(nominal_parts)}.",
            confidence_status=confidence,
            triage_guidance="No action required. Continue nominal solar tracking.",
        )


class RuleThermalLimit(FDIRRule):
    """
    FDIR-THM-001 (v1.1.0): Thermal & Radiation Limit Exceedance.
    Evaluates temperature sensors and radiation dosimeters ONLY when valid telemetry exists.
    """

    def __init__(self, thresholds: Optional[Dict[str, float]] = None) -> None:
        default_thresholds = {
            "max_critical_c": 85.0,
            "min_critical_c": -30.0,
            "max_warning_c": 70.0,
            "min_warning_c": -15.0,
            "max_rad_dose_rad": 100_000.0,
            "warning_rad_dose_rad": 50_000.0,
        }
        if thresholds:
            default_thresholds.update(thresholds)
        super().__init__(
            rule_id="FDIR-THM-001",
            rule_version="1.1.0",
            subsystem=TelemetrySubsystem.THERMAL,
            thresholds=default_thresholds,
        )

    def evaluate(self, readings: Dict[str, TelemetryReading]) -> FDIRFinding:
        now = datetime.now(timezone.utc)
        temp_reading = readings.get("component_temp_c") or readings.get("sensor_temp_c")
        rad_reading = readings.get("total_dose_rad")

        temp_val = _safe_float(temp_reading)
        if temp_val is None or temp_reading is None:
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CAUTION,
                status=FDIRFindingStatus.INSUFFICIENT_DATA,
                affected_subsystem=self.subsystem,
                input_evidence={"missing_fields": ["component_temp_c"]},
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    "Insufficient telemetry: Thermal sensor telemetry unavailable, "
                    "stale, or invalid."
                ),
                confidence_status="INSUFFICIENT_DATA",
                triage_guidance=(
                    "Check thermal harness telemetry multiplexer and RTD sensor health."
                ),
            )

        temp_c = temp_val
        rad_val = _safe_float(rad_reading)
        valid_rad = rad_val is not None
        rad_dose = rad_val if rad_val is not None else 0.0

        confidence = "VERIFIED" if valid_rad else "PROVISIONAL"
        evidence: Dict[str, Any] = {
            "component_temp_c": temp_c,
            "total_dose_rad": rad_val,
            "provenance": temp_reading.provenance.value,
        }
        if not valid_rad and rad_reading is not None:
            evidence["unreliable_fields"] = ["total_dose_rad"]
            evidence["missing_fields"] = ["total_dose_rad"]

        max_crit = self.thresholds["max_critical_c"]
        min_crit = self.thresholds["min_critical_c"]
        max_warn = self.thresholds["max_warning_c"]
        min_warn = self.thresholds["min_warning_c"]
        max_rad = self.thresholds["max_rad_dose_rad"]

        if temp_c > max_crit or temp_c < min_crit or (valid_rad and rad_dose > max_rad):
            reasons = []
            if temp_c > max_crit:
                reasons.append(f"temperature {temp_c:.1f} °C > {max_crit:.1f} °C")
            if temp_c < min_crit:
                reasons.append(f"temperature {temp_c:.1f} °C < {min_crit:.1f} °C")
            if valid_rad and rad_dose > max_rad:
                reasons.append(f"radiation dose {rad_dose:.0f} rad > {max_rad:.0f} rad")
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CRITICAL,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"CRITICAL: Component envelope exceedance ({', '.join(reasons)}). "
                    "Spacecraft survivability envelope violated."
                ),
                confidence_status=confidence,
                triage_guidance=(
                    "1. Activate survival heaters if cold, or activate heat-pipe louvers. "
                    "2. Adjust spacecraft attitude to shade overheat sensors."
                ),
            )

        warn_rad = self.thresholds.get("warning_rad_dose_rad", 50_000.0)
        is_warn = (
            (temp_c > max_warn or temp_c < min_warn)
            or (valid_rad and rad_dose > warn_rad)
        )
        if is_warn:
            reasons = []
            if temp_c > max_warn:
                reasons.append(f"temperature {temp_c:.1f} °C > {max_warn:.1f} °C")
            if temp_c < min_warn:
                reasons.append(f"temperature {temp_c:.1f} °C < {min_warn:.1f} °C")
            if valid_rad and rad_dose > warn_rad:
                reasons.append(f"radiation dose {rad_dose:.0f} rad > {warn_rad:.0f} rad")
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.WARNING,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"WARNING: Temperature or radiation outside nominal operating range "
                    f"({', '.join(reasons)})."
                ),
                confidence_status=confidence,
                triage_guidance=(
                    "Monitor thermal trends, consider solar shading or safe orientation."
                ),
            )

        return FDIRFinding(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            severity=FDIRSeverity.NOMINAL,
            status=FDIRFindingStatus.NOMINAL,
            affected_subsystem=self.subsystem,
            input_evidence=evidence,
            thresholds=self.thresholds,
            timestamp=now,
            explanation=f"Thermal subsystem nominal ({temp_c:.1f} °C).",
            confidence_status=confidence,
            triage_guidance="No action required.",
        )


class RuleCommLoss(FDIRRule):
    """
    FDIR-COM-001 (v1.2.0): Communication Loss & Degraded Downlink Margin.
    Evaluates downlink carrier lock, SNR, and contact freshness from genuine comms data.
    """

    def __init__(self, thresholds: Optional[Dict[str, float]] = None) -> None:
        default_thresholds = {
            "min_carrier_snr_db": 0.0,
            "warning_snr_db": 3.0,
            "critical_blackout_seconds": 86400.0,
        }
        if thresholds:
            default_thresholds.update(thresholds)
        super().__init__(
            rule_id="FDIR-COM-001",
            rule_version="1.2.0",
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            thresholds=default_thresholds,
        )

    def evaluate(self, readings: Dict[str, TelemetryReading]) -> FDIRFinding:
        now = datetime.now(timezone.utc)
        lock_reading = readings.get("carrier_lock")
        snr_reading = readings.get("downlink_snr_db")
        contact_reading = readings.get("time_since_last_contact_s")

        lock_val = _safe_float(lock_reading)
        snr_db = _safe_float(snr_reading)
        time_contact_s = _safe_float(contact_reading, default=0.0) or 0.0

        valid_lock = lock_val is not None
        valid_snr = snr_db is not None

        missing_fields: List[str] = []
        if not valid_lock:
            missing_fields.append("carrier_lock")
        if not valid_snr:
            missing_fields.append("downlink_snr_db")

        # Insufficient data if neither lock nor SNR is valid:
        if not valid_lock and not valid_snr:
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CAUTION,
                status=FDIRFindingStatus.INSUFFICIENT_DATA,
                affected_subsystem=self.subsystem,
                input_evidence={"missing_fields": missing_fields},
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    "Insufficient telemetry: No valid RF carrier or link budget "
                    "metrics available."
                ),
                confidence_status="INSUFFICIENT_DATA",
                triage_guidance="Verify DSN tracking schedule and ground station pointing.",
            )

        is_locked = bool(lock_val > 0.5) if lock_val is not None else None

        confidence = "VERIFIED" if (valid_lock and valid_snr) else "PROVISIONAL"
        evidence: Dict[str, Any] = {
            "carrier_lock": is_locked,
            "downlink_snr_db": snr_db,
            "time_since_last_contact_s": time_contact_s,
        }
        if missing_fields:
            evidence["missing_fields"] = missing_fields

        min_snr = self.thresholds["min_carrier_snr_db"]
        warn_snr = self.thresholds["warning_snr_db"]
        blackout_s = self.thresholds["critical_blackout_seconds"]

        # Critical: sustained loss of contact or negative SNR
        is_critical = (
            (is_locked is False and time_contact_s > blackout_s)
            or (snr_db is not None and snr_db < min_snr)
        )
        if is_critical:
            reasons = []
            if is_locked is False and time_contact_s > blackout_s:
                reasons.append(f"carrier unlocked for {time_contact_s:.0f}s > {blackout_s:.0f}s")
            if snr_db is not None and snr_db < min_snr:
                reasons.append(f"SNR {snr_db:.1f} dB < {min_snr:.1f} dB")
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CRITICAL,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=f"CRITICAL: Downlink blackout detected ({', '.join(reasons)}).",
                confidence_status=confidence,
                triage_guidance=(
                    "1. Spacecraft autonomously switches to low-gain omnidirectional antenna. "
                    "2. Transmit blind acquisition sweep on Emergency Turnaround Transponder."
                ),
            )

        # Warning: carrier unlocked or degraded SNR
        is_warning = (
            (is_locked is False)
            or (snr_db is not None and snr_db < warn_snr)
        )
        if is_warning:
            reasons = []
            if is_locked is False:
                reasons.append("carrier unlocked")
            if snr_db is not None and snr_db < warn_snr:
                reasons.append(f"SNR {snr_db:.1f} dB < {warn_snr:.1f} dB")
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.WARNING,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=f"WARNING: Link margin degraded ({', '.join(reasons)}).",
                confidence_status=confidence,
                triage_guidance="Reduce downlink symbol rate or command DSN 70m dish handover.",
            )

        return FDIRFinding(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            severity=FDIRSeverity.NOMINAL,
            status=FDIRFindingStatus.NOMINAL,
            affected_subsystem=self.subsystem,
            input_evidence=evidence,
            thresholds=self.thresholds,
            timestamp=now,
            explanation=f"Communication link nominal. Carrier locked with SNR {snr_db:.1f} dB.",
            confidence_status=confidence,
            triage_guidance="No action required.",
        )


class RulePropellantMargin(FDIRRule):
    """
    FDIR-PRP-001 (v1.0.0): Propellant & Delta-V Margin Shortfall.
    Evaluates available Delta-V and propellant tank pressure against mission requirements.
    """

    def __init__(self, thresholds: Optional[Dict[str, float]] = None) -> None:
        default_thresholds = {
            "min_tank_pressure_bar": 10.0,
            "critical_margin_pct": 0.0,
            "warning_margin_pct": 5.0,
        }
        if thresholds:
            default_thresholds.update(thresholds)
        super().__init__(
            rule_id="FDIR-PRP-001",
            rule_version="1.0.0",
            subsystem=TelemetrySubsystem.PROPULSION,
            thresholds=default_thresholds,
        )

    def evaluate(self, readings: Dict[str, TelemetryReading]) -> FDIRFinding:
        now = datetime.now(timezone.utc)
        av_dv = readings.get("available_delta_v_mps")
        req_dv = readings.get("required_delta_v_mps")
        press_reading = readings.get("tank_pressure_bar")

        avail_num = _safe_float(av_dv)
        req_num = _safe_float(req_dv)
        press_val = _safe_float(press_reading)

        valid_av = avail_num is not None
        valid_req = req_num is not None
        valid_press = press_val is not None

        if not valid_av or not valid_req or avail_num is None or req_num is None:
            missing = [
                m for m, v in [
                    ("available_delta_v_mps", valid_av),
                    ("required_delta_v_mps", valid_req),
                ]
                if not v
            ]
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CAUTION,
                status=FDIRFindingStatus.INSUFFICIENT_DATA,
                affected_subsystem=self.subsystem,
                input_evidence={"missing_fields": missing},
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    "Insufficient trajectory and propellant budget parameters: "
                    "Delta-V values missing or invalid."
                ),
                confidence_status="INSUFFICIENT_DATA",
                triage_guidance=(
                    "Ensure trajectory baseline and thruster propellant load are configured."
                ),
            )

        avail_val = avail_num
        req_val = req_num

        margin_pct = ((avail_val - req_val) / req_val) * 100.0 if req_val > 0 else 0.0
        confidence = "VERIFIED" if valid_press else "PROVISIONAL"
        evidence: Dict[str, Any] = {
            "available_delta_v_mps": avail_val,
            "required_delta_v_mps": req_val,
            "delta_v_margin_pct": round(margin_pct, 2),
            "tank_pressure_bar": press_val,
        }
        if not valid_press:
            evidence["missing_fields"] = ["tank_pressure_bar"]

        min_press = self.thresholds["min_tank_pressure_bar"]
        warn_margin = self.thresholds["warning_margin_pct"]

        if avail_val < req_val or (press_val is not None and press_val < min_press):
            reasons = []
            if avail_val < req_val:
                reasons.append(f"Delta-V shortfall: {avail_val:.1f} m/s < {req_val:.1f} m/s")
            if press_val is not None and press_val < min_press:
                reasons.append(f"tank pressure {press_val:.1f} bar < {min_press:.1f} bar")
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CRITICAL,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"CRITICAL: Mission Delta-V shortfall or tank pressure breach "
                    f"({', '.join(reasons)})."
                ),
                confidence_status=confidence,
                triage_guidance=(
                    "Trajectory cannot be completed. Descope maneuvers or abort to parking orbit."
                ),
            )

        if margin_pct < warn_margin:
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.WARNING,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"WARNING: Delta-V margin ({margin_pct:.1f}%) is dangerously "
                    f"thin (< {warn_margin:.1f}%)."
                ),
                confidence_status=confidence,
                triage_guidance=(
                    "Recalculate TCMs (Trajectory Correction Maneuvers) and optimize Lambert arcs."
                ),
            )

        return FDIRFinding(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            severity=FDIRSeverity.NOMINAL,
            status=FDIRFindingStatus.NOMINAL,
            affected_subsystem=self.subsystem,
            input_evidence=evidence,
            thresholds=self.thresholds,
            timestamp=now,
            explanation=f"Propulsion budget nominal with {margin_pct:.1f}% Delta-V reserve.",
            confidence_status=confidence,
            triage_guidance="No action required.",
        )


class RuleWheelSaturation(FDIRRule):
    """
    FDIR-ATT-001 (v1.1.0): Reaction-Wheel Saturation & Momentum Management.
    Evaluates wheel angular velocities (RPM) ONLY when valid wheel telemetry is supplied.
    """

    def __init__(self, thresholds: Optional[Dict[str, float]] = None) -> None:
        default_thresholds = {
            "max_critical_rpm": 5500.0,
            "max_warning_rpm": 4800.0,
            "max_caution_rpm": 4000.0,
        }
        if thresholds:
            default_thresholds.update(thresholds)
        super().__init__(
            rule_id="FDIR-ATT-001",
            rule_version="1.1.0",
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            thresholds=default_thresholds,
        )

    def evaluate(self, readings: Dict[str, TelemetryReading]) -> FDIRFinding:
        now = datetime.now(timezone.utc)
        wheel_x = readings.get("reaction_wheel_rpm_x")
        wheel_y = readings.get("reaction_wheel_rpm_y")
        wheel_z = readings.get("reaction_wheel_rpm_z")

        wheel_list = [("wheel_x", wheel_x), ("wheel_y", wheel_y), ("wheel_z", wheel_z)]
        valid_wheels: List[Tuple[str, float]] = []
        rpm_dict: Dict[str, Optional[float]] = {}
        for name, r in wheel_list:
            val = _safe_float(r)
            rpm_dict[name] = val
            if val is not None:
                valid_wheels.append((name, val))

        if not valid_wheels:
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CAUTION,
                status=FDIRFindingStatus.INSUFFICIENT_DATA,
                affected_subsystem=self.subsystem,
                input_evidence={"missing_fields": ["reaction_wheel_rpm"]},
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    "Insufficient telemetry: Reaction wheel tachometer data "
                    "unavailable, stale, or invalid."
                ),
                confidence_status="INSUFFICIENT_DATA",
                triage_guidance="Verify RWA tachometer CAN bus bridge status.",
            )

        rpms = [val for _, val in valid_wheels]
        max_rpm = max([abs(val) for val in rpms])

        confidence = "VERIFIED" if len(valid_wheels) == 3 else "PROVISIONAL"
        evidence: Dict[str, Any] = {
            "max_wheel_rpm": max_rpm,
            "rpm_readings": rpm_dict,
        }
        if len(valid_wheels) < 3:
            missing_w = [
                ("reaction_wheel_rpm_x", wheel_x),
                ("reaction_wheel_rpm_y", wheel_y),
                ("reaction_wheel_rpm_z", wheel_z),
            ]
            evidence["missing_fields"] = [
                m for m, r in missing_w
                if (
                    r is None
                    or r.value is None
                    or r.quality in (TelemetryQuality.INVALID, TelemetryQuality.STALE)
                )
            ]

        crit_rpm = self.thresholds["max_critical_rpm"]
        warn_rpm = self.thresholds["max_warning_rpm"]
        caution_rpm = self.thresholds.get("max_caution_rpm", 4000.0)

        if max_rpm > crit_rpm:
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CRITICAL,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"CRITICAL: Reaction wheel saturation "
                    f"({max_rpm:.0f} RPM > {crit_rpm:.0f} RPM). "
                    "Attitude control authority compromised."
                ),
                confidence_status=confidence,
                triage_guidance=(
                    "1. Immediately initiate RCS thruster momentum dumping maneuver. "
                    "2. Decouple high-inertia fine pointing maneuvers."
                ),
            )

        if max_rpm > warn_rpm:
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.WARNING,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"WARNING: Reaction wheel momentum high "
                    f"({max_rpm:.0f} RPM > {warn_rpm:.0f} RPM)."
                ),
                confidence_status=confidence,
                triage_guidance="Schedule automated RCS momentum desaturation pass.",
            )

        if max_rpm > caution_rpm:
            return FDIRFinding(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                severity=FDIRSeverity.CAUTION,
                status=FDIRFindingStatus.ACTIVE_ANOMALY,
                affected_subsystem=self.subsystem,
                input_evidence=evidence,
                thresholds=self.thresholds,
                timestamp=now,
                explanation=(
                    f"CAUTION: Reaction wheel momentum elevated "
                    f"({max_rpm:.0f} RPM > {caution_rpm:.0f} RPM)."
                ),
                confidence_status=confidence,
                triage_guidance=(
                    "Monitor reaction wheel angular velocity and plan momentum dumping."
                ),
            )

        return FDIRFinding(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            severity=FDIRSeverity.NOMINAL,
            status=FDIRFindingStatus.NOMINAL,
            affected_subsystem=self.subsystem,
            input_evidence=evidence,
            thresholds=self.thresholds,
            timestamp=now,
            explanation=f"Attitude wheel momentum nominal (Peak: {max_rpm:.0f} RPM).",
            confidence_status=confidence,
            triage_guidance="No action required.",
        )
