"""
FDIR API Request and Response Schemas
Mission Forge — Phase 5
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.app.fdir.rules import FDIRFinding, FDIRSeverity
from backend.app.fdir.telemetry import TelemetryReading


class FDIREvaluationRequest(BaseModel):
    """Payload to trigger FDIR evaluation."""
    room_id: Optional[str] = Field(None, description="Optional CDF room UUID")
    mission_id: Optional[str] = Field(None, description="Optional Mission UUID")
    readings: Optional[List[TelemetryReading]] = Field(
        None, description="Direct sensor telemetry readings"
    )
    scenario_id: Optional[str] = Field(
        None, description="Simulated test scenario identifier (e.g. POWER_DEFICIT, COMM_BLACKOUT)"
    )
    debounce_samples: int = Field(1, ge=1, le=10, description="Hysteresis sample count")


class FDIRReportResponse(BaseModel):
    """Consolidated FDIR evaluation report response."""
    eval_timestamp: datetime
    overall_severity: FDIRSeverity
    findings: List[FDIRFinding]
    active_anomalies: List[FDIRFinding]
    insufficient_data_findings: List[FDIRFinding]
    advisory_disclaimer: str


class FDIRAcknowledgeRequest(BaseModel):
    """Request to acknowledge an active finding in the audit trail."""
    finding_id: str = Field(..., description="UUID of the finding log record")


class FDIRRuleInfoResponse(BaseModel):
    """Metadata for a registered FDIR rule."""
    rule_id: str
    rule_version: str
    subsystem: str
    name: str


class FDIRFindingLogResponse(BaseModel):
    """Persistent audit log record of an FDIR anomaly detection."""
    id: str
    room_id: Optional[str]
    mission_id: Optional[str]
    rule_id: str
    rule_version: str
    severity: str
    status: str
    affected_subsystem: str
    explanation: str
    confidence_status: str
    triage_guidance: str
    acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[datetime]
    created_at: datetime
