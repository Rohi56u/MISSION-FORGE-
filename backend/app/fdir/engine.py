"""
Deterministic Fault Detection, Isolation, and Recovery (FDIR) Engine
Mission Forge — Phase 5
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.cdf.state import CDFAuthoritativeState
from backend.app.fdir.rules import (
    FDIR_ADVISORY_DISCLAIMER,
    FDIRFinding,
    FDIRFindingStatus,
    FDIRRule,
    FDIRSeverity,
    RuleCommLoss,
    RulePowerShortfall,
    RulePropellantMargin,
    RuleThermalLimit,
    RuleWheelSaturation,
)
from backend.app.fdir.telemetry import (
    TelemetryProvenanceType,
    TelemetryQuality,
    TelemetryReading,
    TelemetrySubsystem,
)
from backend.app.models.fdir import FDIRFindingLog

logger = logging.getLogger(__name__)


class FDIRReport(BaseModel):
    """Authoritative consolidated FDIR evaluation report."""
    eval_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_severity: FDIRSeverity
    findings: List[FDIRFinding]
    active_anomalies: List[FDIRFinding]
    insufficient_data_findings: List[FDIRFinding]
    advisory_disclaimer: str = FDIR_ADVISORY_DISCLAIMER


class FDIREngine:
    """
    Authoritative deterministic FDIR engine.
    The AI assistant NEVER creates, modifies, suppresses, or overrides findings from this engine.
    """

    def __init__(self) -> None:
        self.rules: List[FDIRRule] = [
            RulePowerShortfall(),
            RuleThermalLimit(),
            RuleCommLoss(),
            RulePropellantMargin(),
            RuleWheelSaturation(),
        ]
        # State tracker: scope -> (rule_id -> rolling history of severities)
        self._severity_history: Dict[str, Dict[str, List[FDIRSeverity]]] = {}
        self._stable_severity: Dict[str, Dict[str, FDIRSeverity]] = {}
        self._recovery_counter: Dict[str, Dict[str, int]] = {}

    def reset(self) -> None:
        """Resets debounce history and stable severity tracking across all scopes."""
        self._severity_history.clear()
        self._stable_severity.clear()
        self._recovery_counter.clear()

    def get_registered_rules(self) -> List[Dict[str, str]]:
        """Returns metadata for all registered FDIR rules and versions."""
        return [
            {
                "rule_id": r.rule_id,
                "rule_version": r.rule_version,
                "subsystem": r.subsystem.value,
                "name": r.__class__.__name__,
            }
            for r in self.rules
        ]

    def evaluate_telemetry(
        self,
        readings: List[TelemetryReading],
        debounce_samples: int = 1,
    ) -> FDIRReport:
        """
        Deterministically evaluates all active rules against the provided telemetry readings.
        Handles missing/stale/invalid inputs explicitly.
        """
        now = datetime.now(timezone.utc)
        readings_map: Dict[str, TelemetryReading] = {r.metric_name: r for r in readings}

        # Determine isolation scope (room_id, mission_id, spacecraft_id, source, or default)
        scope = "default"
        for r in readings:
            if r.room_id:
                scope = f"room:{r.room_id}"
                break
            elif r.mission_id:
                scope = f"mission:{r.mission_id}"
                break
            elif r.spacecraft_id:
                scope = f"spacecraft:{r.spacecraft_id}"
                break
            elif r.source:
                scope = f"source:{r.source}"
                break

        scope_history = self._severity_history.setdefault(scope, {})
        scope_stable = self._stable_severity.setdefault(scope, {})

        findings: List[FDIRFinding] = []
        for rule in self.rules:
            finding = rule.evaluate(readings_map)

            # Apply debounce/hysteresis tracking within this scope
            history = scope_history.setdefault(rule.rule_id, [])
            history.append(finding.severity)
            if len(history) > 20:
                history.pop(0)

            # Check debounce: require consecutive samples to confirm severity transition
            previous_stable = scope_stable.get(rule.rule_id, FDIRSeverity.NOMINAL)
            is_unresolved = (
                finding.status == FDIRFindingStatus.INSUFFICIENT_DATA
                or finding.confidence_status != "VERIFIED"
                or bool(finding.input_evidence.get("missing_fields"))
            )

            # Safety guarantee: absent/insufficient/provisional telemetry
            # cannot silently clear or downgrade active anomaly
            if previous_stable in (FDIRSeverity.WARNING, FDIRSeverity.CRITICAL):
                if finding.severity in (FDIRSeverity.WARNING, FDIRSeverity.CRITICAL):
                    # Active anomaly still present / detected
                    scope_stable[rule.rule_id] = finding.severity
                    self._recovery_counter.setdefault(scope, {})[rule.rule_id] = 0
                elif is_unresolved:
                    # Anomaly cannot be cleared by missing, stale, or provisional telemetry
                    finding.severity = previous_stable
                    if "[UNRESOLVED ANOMALY" not in finding.explanation:
                        finding.explanation += (
                            f" [UNRESOLVED ANOMALY: Prior active anomaly at severity "
                            f"{previous_stable.value} cannot be cleared while telemetry "
                            f"data is absent, provisional, or insufficient.]"
                        )
                    scope_stable[rule.rule_id] = previous_stable
                    self._recovery_counter.setdefault(scope, {})[rule.rule_id] = 0
                else:
                    # Verified nominal telemetry received: apply recovery hysteresis
                    scope_rec = self._recovery_counter.setdefault(scope, {})
                    rec_count = scope_rec.get(rule.rule_id, 0) + 1
                    self._recovery_counter[scope][rule.rule_id] = rec_count
                    if debounce_samples > 1 and rec_count < debounce_samples:
                        finding.severity = previous_stable
                        if "[Recovery hysteresis" not in finding.explanation:
                            finding.explanation += (
                                f" [Recovery hysteresis active: holding severity "
                                f"{previous_stable.value} until {debounce_samples} "
                                f"consecutive verified nominal samples confirm recovery "
                                f"({rec_count}/{debounce_samples})]"
                            )
                        scope_stable[rule.rule_id] = previous_stable
                    else:
                        # Recovery confirmed!
                        self._recovery_counter[scope][rule.rule_id] = 0
                        scope_stable[rule.rule_id] = FDIRSeverity.NOMINAL
            else:
                # System was NOMINAL or CAUTION
                if finding.severity in (FDIRSeverity.WARNING, FDIRSeverity.CRITICAL):
                    if debounce_samples > 1:
                        recent = (
                            history[-debounce_samples:]
                            if len(history) >= debounce_samples
                            else history
                        )
                        if (
                            len(recent) >= debounce_samples
                            and all(s == finding.severity for s in recent)
                        ):
                            scope_stable[rule.rule_id] = finding.severity
                        else:
                            finding.severity = previous_stable
                            finding.explanation += (
                                f" [Debounce filter active: holding stable severity "
                                f"{previous_stable.value} until {debounce_samples} "
                                f"consecutive samples confirm transition]"
                            )
                            scope_stable[rule.rule_id] = previous_stable
                    else:
                        scope_stable[rule.rule_id] = finding.severity
                else:
                    scope_stable[rule.rule_id] = finding.severity

            findings.append(finding)

        # Derive overall severity
        has_critical = any(f.severity == FDIRSeverity.CRITICAL for f in findings)
        has_warning = any(f.severity == FDIRSeverity.WARNING for f in findings)
        has_caution = any(f.severity == FDIRSeverity.CAUTION for f in findings)

        if has_critical:
            overall = FDIRSeverity.CRITICAL
        elif has_warning:
            overall = FDIRSeverity.WARNING
        elif has_caution:
            overall = FDIRSeverity.CAUTION
        else:
            overall = FDIRSeverity.NOMINAL

        active_anomalies = [
            f for f in findings
            if f.status == FDIRFindingStatus.ACTIVE_ANOMALY
            or "UNRESOLVED ANOMALY" in f.explanation
            or f.severity in (FDIRSeverity.WARNING, FDIRSeverity.CRITICAL)
        ]
        insufficient_data = [
            f for f in findings if f.status == FDIRFindingStatus.INSUFFICIENT_DATA
        ]

        return FDIRReport(
            eval_timestamp=now,
            overall_severity=overall,
            findings=findings,
            active_anomalies=active_anomalies,
            insufficient_data_findings=insufficient_data,
        )

    def evaluate_room_state(
        self,
        state: CDFAuthoritativeState,
        additional_telemetry: Optional[List[TelemetryReading]] = None,
        debounce_samples: int = 1,
    ) -> FDIRReport:
        """
        Translates authoritative CDF room design state into telemetry readings
        and executes deterministic FDIR rule evaluation.
        """
        now = datetime.now(timezone.utc)
        synthetic_readings: List[TelemetryReading] = []

        # Extract Propulsion & Trajectory metrics
        b = state.calculated_budgets
        synthetic_readings.append(
            TelemetryReading(
                subsystem=TelemetrySubsystem.PROPULSION,
                metric_name="available_delta_v_mps",
                value=b.available_delta_v_mps,
                unit="m/s",
                timestamp=now,
                source="CDF_STATE_SWAPC",
                provenance=TelemetryProvenanceType.CACHED,
                quality=TelemetryQuality.GOOD,
                room_id=state.room_id,
                mission_id=state.mission_id,
            )
        )
        synthetic_readings.append(
            TelemetryReading(
                subsystem=TelemetrySubsystem.PROPULSION,
                metric_name="required_delta_v_mps",
                value=state.flight_dynamics_and_comms.required_delta_v_mps,
                unit="m/s",
                timestamp=now,
                source="CDF_STATE_TRAJECTORY",
                provenance=TelemetryProvenanceType.CACHED,
                quality=TelemetryQuality.GOOD,
                room_id=state.room_id,
                mission_id=state.mission_id,
            )
        )

        # Extract Electrical Power metrics
        synthetic_readings.append(
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="power_generation_w",
                value=b.total_power_generated_w,
                unit="W",
                timestamp=now,
                source="CDF_STATE_SWAPC",
                provenance=TelemetryProvenanceType.CACHED,
                quality=TelemetryQuality.GOOD,
                room_id=state.room_id,
                mission_id=state.mission_id,
            )
        )
        synthetic_readings.append(
            TelemetryReading(
                subsystem=TelemetrySubsystem.POWER,
                metric_name="power_draw_w",
                value=b.total_power_draw_w,
                unit="W",
                timestamp=now,
                source="CDF_STATE_SWAPC",
                provenance=TelemetryProvenanceType.CACHED,
                quality=TelemetryQuality.GOOD,
                room_id=state.room_id,
                mission_id=state.mission_id,
            )
        )

        # Extract Telecom link metrics
        if b.link_margin_db is not None:
            synthetic_readings.append(
                TelemetryReading(
                    subsystem=TelemetrySubsystem.COMMUNICATIONS,
                    metric_name="downlink_snr_db",
                    value=b.link_margin_db,
                    unit="dB",
                    timestamp=now,
                    source="CDF_STATE_TELECOM",
                    provenance=TelemetryProvenanceType.CACHED,
                    quality=TelemetryQuality.GOOD,
                    room_id=state.room_id,
                    mission_id=state.mission_id,
                )
            )

        if additional_telemetry:
            synthetic_readings.extend(additional_telemetry)

        return self.evaluate_telemetry(synthetic_readings, debounce_samples=debounce_samples)

    async def restore_alert_state(
        self,
        db: AsyncSession,
        room_id: Optional[str] = None,
        mission_id: Optional[str] = None,
    ) -> None:
        """
        Restores active unacknowledged anomaly states from the persistent database audit log.
        Ensures safety invariant that active anomalies persist across process restarts.
        """
        if not room_id and not mission_id:
            return

        from sqlalchemy import select, or_
        conditions = [FDIRFindingLog.acknowledged == False]  # noqa: E712
        if room_id and mission_id:
            conditions.append(
                or_(FDIRFindingLog.room_id == room_id, FDIRFindingLog.mission_id == mission_id)
            )
        elif room_id:
            conditions.append(FDIRFindingLog.room_id == room_id)
        elif mission_id:
            conditions.append(FDIRFindingLog.mission_id == mission_id)

        stmt = (
            select(FDIRFindingLog)
            .where(*conditions)
            .order_by(FDIRFindingLog.created_at.desc())
        )
        try:
            res = await db.execute(stmt)
            for log in res.scalars().all():
                try:
                    sev = FDIRSeverity(log.severity)
                    if sev in (FDIRSeverity.WARNING, FDIRSeverity.CRITICAL):
                        if room_id:
                            self._stable_severity.setdefault(
                                f"room:{room_id}", {}
                            )[log.rule_id] = sev
                        if mission_id:
                            self._stable_severity.setdefault(
                                f"mission:{mission_id}", {}
                            )[log.rule_id] = sev
                        if log.room_id:
                            self._stable_severity.setdefault(
                                f"room:{log.room_id}", {}
                            )[log.rule_id] = sev
                        if log.mission_id:
                            self._stable_severity.setdefault(
                                f"mission:{log.mission_id}", {}
                            )[log.rule_id] = sev
                except ValueError:
                    pass
        except Exception as exc:
            logger.warning("Failed to restore FDIR state from database: %s", exc)

    async def persist_findings(
        self,
        db: AsyncSession,
        report: FDIRReport,
        room_id: Optional[str] = None,
        mission_id: Optional[str] = None,
    ) -> List[FDIRFindingLog]:
        """Persists evaluated findings in the database audit log with transaction safety."""
        logs: List[FDIRFindingLog] = []
        for f in report.findings:
            log_entry = FDIRFindingLog(
                room_id=room_id,
                mission_id=mission_id,
                rule_id=f.rule_id,
                rule_version=f.rule_version,
                severity=f.severity.value,
                status=f.status.value,
                affected_subsystem=f.affected_subsystem.value,
                input_evidence=f.input_evidence,
                thresholds=f.thresholds,
                explanation=f.explanation,
                confidence_status=f.confidence_status,
                triage_guidance=f.triage_guidance,
                acknowledged=False,
            )
            db.add(log_entry)
            logs.append(log_entry)

        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("Failed persisting FDIR findings audit log: %s", exc)
        return logs


# Singleton FDIR Engine
fdir_engine = FDIREngine()
