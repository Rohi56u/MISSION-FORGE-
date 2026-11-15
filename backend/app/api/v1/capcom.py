"""
Grounded CAPCOM AI Assistant REST API Endpoints
Mission Forge — Phase 5
"""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.capcom.gemini_adapter import capcom_adapter
from backend.app.cdf.service import get_latest_room_state
from backend.app.core.auth import get_current_user
from backend.app.core.database import get_db
from backend.app.fdir.engine import fdir_engine
from backend.app.models.auth import User
from backend.app.schemas.capcom import CAPCOMRequest, CAPCOMResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capcom", tags=["CAPCOM AI Assistant"])


@router.post(
    "/ask",
    response_model=CAPCOMResponse,
    status_code=status.HTTP_200_OK,
    summary="Query Grounded CAPCOM AI Assistant",
)
async def ask_capcom(
    payload: CAPCOMRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CAPCOMResponse:
    """
    Submits an engineering query to the CAPCOM AI assistant.
    Grounds context strictly in authoritative CDF state and deterministic FDIR findings.
    The assistant cannot alter or override deterministic calculations or FDIR findings.
    """
    bounded_context: Dict[str, Any] = {
        "user_name": current_user.full_name,
        "query": payload.query,
    }

    if payload.room_id:
        from backend.app.api.v1.cdf import assert_room_membership
        await assert_room_membership(db, payload.room_id, current_user.id)
        room_state = await get_latest_room_state(db, payload.room_id)
        await fdir_engine.restore_alert_state(
            db=db, room_id=payload.room_id, mission_id=room_state.mission_id
        )
        fdir_report = fdir_engine.evaluate_room_state(
            room_state, additional_telemetry=payload.telemetry_readings
        )
        bounded_context.update({
            "room_id": payload.room_id,
            "mission_id": room_state.mission_id,
            "version": room_state.version,
            "system_constraints": room_state.system_constraints.model_dump(),
            "flight_dynamics_and_comms": room_state.flight_dynamics_and_comms.model_dump(),
            "calculated_budgets": room_state.calculated_budgets.model_dump(),
            "rule_versions": {
                r["rule_id"]: r["rule_version"] for r in fdir_engine.get_registered_rules()
            },
            "fdir_report": {
                "overall_severity": fdir_report.overall_severity.value,
                "findings": [f.model_dump() for f in fdir_report.findings],
                "insufficient_data_findings": [
                    f.model_dump() for f in fdir_report.insufficient_data_findings
                ],
            },
            "provenance_map": room_state.provenance_map,
        })
    else:
        # Direct telemetry FDIR without room state
        readings = payload.telemetry_readings or []
        fdir_report = fdir_engine.evaluate_telemetry(readings)
        bounded_context.update({
            "rule_versions": {
                r["rule_id"]: r["rule_version"] for r in fdir_engine.get_registered_rules()
            },
            "fdir_report": {
                "overall_severity": fdir_report.overall_severity.value,
                "findings": [f.model_dump() for f in fdir_report.findings],
                "insufficient_data_findings": [
                    f.model_dump() for f in fdir_report.insufficient_data_findings
                ],
            },
        })

    return await capcom_adapter.generate_capcom_response(
        query=payload.query,
        bounded_context=bounded_context,
    )
