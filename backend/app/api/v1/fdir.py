"""
Deterministic FDIR REST API Endpoints
Mission Forge — Phase 5
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.cdf.service import get_latest_room_state
from backend.app.core.auth import get_current_user
from backend.app.core.database import get_db
from backend.app.fdir.engine import fdir_engine
from backend.app.fdir.telemetry import create_simulated_scenario
from backend.app.models.auth import User
from backend.app.models.fdir import FDIRFindingLog
from backend.app.schemas.fdir import (
    FDIRAcknowledgeRequest,
    FDIREvaluationRequest,
    FDIRFindingLogResponse,
    FDIRReportResponse,
    FDIRRuleInfoResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fdir", tags=["Deterministic FDIR Engine"])


@router.post(
    "/evaluate",
    response_model=FDIRReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Telemetry against Deterministic FDIR Rules",
)
async def evaluate_fdir(
    payload: FDIREvaluationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> FDIRReportResponse:
    """
    Evaluates sensor readings, simulated scenarios, or CDF room design state
    against versioned deterministic FDIR rules. Persists findings in audit log.
    """
    readings = payload.readings or []

    # 1. If scenario requested, generate labelled simulation readings
    if payload.scenario_id:
        scenario_readings = create_simulated_scenario(payload.scenario_id)
        readings.extend(scenario_readings)

    # 2. If room_id supplied, pull latest authoritative state (strictly asserting room membership)
    if payload.room_id:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to evaluate CDF room state.",
            )
        from backend.app.api.v1.cdf import assert_room_membership
        await assert_room_membership(db, payload.room_id, current_user.id)
        room_state = await get_latest_room_state(db, payload.room_id)
        # Restore any unacknowledged anomaly state across process restarts
        await fdir_engine.restore_alert_state(
            db=db, room_id=payload.room_id, mission_id=room_state.mission_id
        )
        report = fdir_engine.evaluate_room_state(
            room_state, additional_telemetry=readings, debounce_samples=payload.debounce_samples
        )
        await fdir_engine.persist_findings(
            db=db,
            report=report,
            room_id=payload.room_id,
            mission_id=room_state.mission_id,
        )
    else:
        report = fdir_engine.evaluate_telemetry(readings, debounce_samples=payload.debounce_samples)
        m_id = payload.mission_id or next((r.mission_id for r in readings if r.mission_id), None)
        # 3. Persist audit trail of findings
        await fdir_engine.persist_findings(
            db=db,
            report=report,
            mission_id=m_id,
        )

    return FDIRReportResponse(
        eval_timestamp=report.eval_timestamp,
        overall_severity=report.overall_severity,
        findings=report.findings,
        active_anomalies=report.active_anomalies,
        insufficient_data_findings=report.insufficient_data_findings,
        advisory_disclaimer=report.advisory_disclaimer,
    )


@router.get(
    "/rules",
    response_model=List[FDIRRuleInfoResponse],
    status_code=status.HTTP_200_OK,
    summary="List Registered Deterministic FDIR Rules and Versions",
)
async def list_fdir_rules() -> List[FDIRRuleInfoResponse]:
    """Returns rule IDs, semantic versions, subsystems, and descriptors."""
    rules_meta = fdir_engine.get_registered_rules()
    return [FDIRRuleInfoResponse(**r) for r in rules_meta]


@router.post(
    "/scenarios/{scenario_id}",
    response_model=FDIRReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Pre-Configured Simulated FDIR Test Scenario",
)
async def run_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
) -> FDIRReportResponse:
    """
    Executes a labelled simulation scenario (e.g. POWER_DEFICIT, THERMAL_EXCEEDANCE,
    COMM_BLACKOUT, WHEEL_SATURATION, PROPULSION_SHORTFALL, NOMINAL_CRUISE)
    for reproducible deterministic verification.
    """
    readings = create_simulated_scenario(scenario_id)
    if not readings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown scenario '{scenario_id}'. Available scenarios: POWER_DEFICIT, "
                "THERMAL_EXCEEDANCE, COMM_BLACKOUT, WHEEL_SATURATION, PROPULSION_SHORTFALL, "
                "NOMINAL_CRUISE."
            ),
        )
    report = fdir_engine.evaluate_telemetry(readings)
    await fdir_engine.persist_findings(db=db, report=report)

    return FDIRReportResponse(
        eval_timestamp=report.eval_timestamp,
        overall_severity=report.overall_severity,
        findings=report.findings,
        active_anomalies=report.active_anomalies,
        insufficient_data_findings=report.insufficient_data_findings,
        advisory_disclaimer=report.advisory_disclaimer,
    )


@router.post(
    "/acknowledge",
    status_code=status.HTTP_200_OK,
    summary="Acknowledge Active FDIR Finding",
)
async def acknowledge_finding(
    payload: FDIRAcknowledgeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Records operator acknowledgement of an active anomaly in the audit log."""
    stmt = (
        update(FDIRFindingLog)
        .where(FDIRFindingLog.id == payload.finding_id)
        .values(
            acknowledged=True,
            acknowledged_by=current_user.id,
            acknowledged_at=datetime.now(timezone.utc),
        )
    )
    res = await db.execute(stmt)
    if getattr(res, "rowcount", 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FDIR finding '{payload.finding_id}' not found.",
        )
    await db.commit()
    return {"message": "Finding successfully acknowledged."}


@router.get(
    "/history",
    response_model=List[FDIRFindingLogResponse],
    status_code=status.HTTP_200_OK,
    summary="Get FDIR Findings Audit Trail",
)
async def get_fdir_history(
    room_id: Optional[str] = Query(None),
    mission_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[FDIRFindingLogResponse]:
    """Retrieves immutable audit history of FDIR evaluations and state transitions."""
    stmt = select(FDIRFindingLog)
    if room_id:
        from backend.app.api.v1.cdf import assert_room_membership
        await assert_room_membership(db, room_id, current_user.id)
        stmt = stmt.where(FDIRFindingLog.room_id == room_id)
    if mission_id:
        stmt = stmt.where(FDIRFindingLog.mission_id == mission_id)
    stmt = stmt.order_by(FDIRFindingLog.created_at.desc()).limit(limit)

    res = await db.execute(stmt)
    findings = res.scalars().all()
    return [
        FDIRFindingLogResponse(
            id=f.id,
            room_id=f.room_id,
            mission_id=f.mission_id,
            rule_id=f.rule_id,
            rule_version=f.rule_version,
            severity=f.severity,
            status=f.status,
            affected_subsystem=f.affected_subsystem,
            explanation=f.explanation,
            confidence_status=f.confidence_status,
            triage_guidance=f.triage_guidance,
            acknowledged=f.acknowledged,
            acknowledged_by=f.acknowledged_by,
            acknowledged_at=f.acknowledged_at,
            created_at=f.created_at,
        )
        for f in findings
    ]
