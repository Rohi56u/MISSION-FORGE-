"""
Mission Concept Dossier REST API Endpoints
Mission Forge — Phase 6
"""

import asyncio
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.cdf import assert_room_membership
from backend.app.core.auth import get_current_user
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.dossier.builder import sanitize_filename, sanitize_text
from backend.app.dossier.storage import dossier_storage, is_supabase_configured
from backend.app.dossier.service import (
    _DOSSIER_PROGRESS,
    check_dossier_rate_limit,
    cleanup_expired_dossiers,
    is_dossier_expired,
    run_dossier_generation_job,
)
from backend.app.models.auth import User
from backend.app.models.cdf import CDFRoom, CDFRoomParticipant
from backend.app.models.dossier import DossierJob, DossierReport, DossierReportStatus
from backend.app.models.mission import Mission
from backend.app.schemas.dossier import (
    DossierGenerateRequest,
    DossierJobResponse,
    DossierReportListResponse,
    DossierReportMetadataResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dossiers", tags=["Mission Dossiers & Scientific Reports"])

_UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def validate_uuid(val: str, field_name: str = "Identifier") -> str:
    """Validates that a string is a standard UUID to prevent path traversal and injection."""
    if not _UUID_REGEX.match(val):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format: must be a canonical RFC 4122 UUID.",
        )
    return val


async def assert_dossier_access(
    db: AsyncSession,
    user_id: str,
    owner_id: str,
    room_id: Optional[str] = None,
) -> None:
    """
    Enforces RBAC authorization: grants access only to the dossier creator
    or verified participants of the associated CDF collaborative room.
    """
    if user_id == owner_id:
        return

    if room_id:
        stmt = select(CDFRoomParticipant).where(
            and_(CDFRoomParticipant.room_id == room_id, CDFRoomParticipant.user_id == user_id)
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have authorization to view or download this mission dossier.",
    )


@router.post(
    "/generate",
    response_model=DossierJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Asynchronous Mission Dossier Generation Job",
)
async def generate_dossier(
    payload: DossierGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DossierJobResponse:
    """
    Initiates asynchronous generation of an auditable mission concept dossier.
    Validates mission existence and user authorization, schedules background worker,
    and returns initial job tracking metadata.
    """
    validate_uuid(payload.mission_id, "mission_id")
    if payload.room_id:
        validate_uuid(payload.room_id, "room_id")
    if payload.design_id:
        validate_uuid(payload.design_id, "design_id")
    if payload.trajectory_job_id:
        validate_uuid(payload.trajectory_job_id, "trajectory_job_id")

    # 0. Enforce Rate Limiting
    allowed, retry_after = check_dossier_rate_limit(current_user.id, action="generate")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Dossier generation rate limit exceeded. "
                f"Please wait {retry_after}s before submitting another job."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    # 1. Verify target mission exists
    stmt_m = select(Mission).where(Mission.id == payload.mission_id)
    res_m = await db.execute(stmt_m)
    mission = res_m.scalar_one_or_none()
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission with ID '{payload.mission_id}' not found.",
        )

    # 2. Authorization Verification
    if payload.room_id:
        # Strictly verify user is an active participant in the specified room
        await assert_room_membership(db, payload.room_id, current_user.id)
    else:
        # If CDF rooms exist for this mission, check if user is in any of them
        stmt_rooms = select(CDFRoom).where(CDFRoom.mission_id == payload.mission_id)
        res_rooms = await db.execute(stmt_rooms)
        rooms = res_rooms.scalars().all()
        if rooms:
            room_ids = [r.id for r in rooms]
            stmt_parts = select(CDFRoomParticipant).where(
                and_(
                    CDFRoomParticipant.room_id.in_(room_ids),
                    CDFRoomParticipant.user_id == current_user.id,
                )
            )
            res_parts = await db.execute(stmt_parts)
            if not res_parts.scalars().all():
                # User is not a participant in any CDF room for this mission
                # Check if user created any room
                creator_match = any(r.creator_id == current_user.id for r in rooms)
                if not creator_match:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            "You are not authorized to compile a dossier for this "
                            "collaborative mission."
                        ),
                    )

    # 3. Create Persisted DossierJob
    clean_title = sanitize_text(payload.title, 128) if payload.title else None
    job = DossierJob(
        mission_id=payload.mission_id,
        user_id=current_user.id,
        room_id=payload.room_id,
        design_id=payload.design_id,
        format=payload.format,
        status=DossierReportStatus.QUEUED,
        progress_percent=0.0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 4. Schedule Non-blocking Background Job
    asyncio.create_task(
        run_dossier_generation_job(
            job_id=job.id,
            mission_id=payload.mission_id,
            user_id=current_user.id,
            room_id=payload.room_id,
            design_id=payload.design_id,
            trajectory_job_id=payload.trajectory_job_id,
            custom_title=clean_title,
            format_pref=payload.format,
            include_cdf_history=payload.include_cdf_history,
            include_fdir_audit=payload.include_fdir_audit,
            include_capcom_summary=payload.include_capcom_summary,
        )
    )

    return DossierJobResponse(
        job_id=job.id,
        mission_id=job.mission_id,
        status=job.status,
        format=job.format,
        progress_percent=0.0,
        report_id=None,
        error_message=None,
        created_at=job.created_at,
        completed_at=None,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=DossierJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Dossier Generation Job Status",
)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DossierJobResponse:
    """Retrieves real-time status and progress of a dossier compilation task."""
    validate_uuid(job_id, "job_id")
    stmt = select(DossierJob).where(DossierJob.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dossier job '{job_id}' not found.",
        )

    # RBAC Ownership check
    await assert_dossier_access(db, current_user.id, job.user_id, job.room_id)

    # Dynamically reflect in-memory progress if active
    prog = _DOSSIER_PROGRESS.get(job.id, job.progress_percent)
    if job.status == DossierReportStatus.COMPLETED:
        prog = 100.0

    return DossierJobResponse(
        job_id=job.id,
        mission_id=job.mission_id,
        status=job.status,
        format=job.format,
        progress_percent=prog,
        report_id=job.report_id,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get(
    "/{report_id}",
    response_model=DossierReportMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Dossier Report Metadata and Checksums",
)
async def get_report_metadata(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DossierReportMetadataResponse:
    """Retrieves metadata, file sizes, and cryptographic SHA-256 hashes of a generated dossier."""
    validate_uuid(report_id, "report_id")
    stmt = select(DossierReport).where(DossierReport.id == report_id)
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dossier report '{report_id}' not found.",
        )

    await assert_dossier_access(db, current_user.id, report.user_id, report.room_id)

    dl_pdf = f"/api/v1/dossiers/{report.id}/download?format=pdf" if report.pdf_path else None
    dl_json = f"/api/v1/dossiers/{report.id}/download?format=json" if report.json_path else None

    return DossierReportMetadataResponse(
        id=report.id,
        job_id=report.job_id,
        mission_id=report.mission_id,
        room_id=report.room_id,
        design_id=report.design_id,
        title=report.title,
        format=report.format,
        pdf_size_bytes=report.pdf_size_bytes,
        pdf_sha256=report.pdf_sha256,
        json_size_bytes=report.json_size_bytes,
        json_sha256=report.json_sha256,
        schema_version=report.schema_version,
        page_count=report.page_count,
        created_at=report.created_at,
        download_url_pdf=dl_pdf,
        download_url_json=dl_json,
    )


@router.get(
    "/{report_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Securely Download Dossier Artifact (PDF or JSON)",
)
async def download_dossier_artifact(
    report_id: str,
    format: str = Query(default="pdf", pattern="^(?i)(pdf|json)$"),
    redirect: bool = Query(
        default=False, description="Redirect to Supabase signed URL if available"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Secure artifact download with strict path traversal prevention,
    RBAC ownership enforcement, and tamper-evident SHA-256 ETag headers.
    Supports optional 307 temporary redirect to Supabase expiring signed URLs.
    """
    validate_uuid(report_id, "report_id")

    # 0. Enforce Rate Limiting on Downloads
    allowed, retry_after = check_dossier_rate_limit(current_user.id, action="download")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Dossier download rate limit exceeded. "
                f"Please wait {retry_after}s before retrying."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    stmt = select(DossierReport).where(DossierReport.id == report_id)
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dossier report '{report_id}' not found.",
        )

    # 1. Enforce RBAC
    await assert_dossier_access(db, current_user.id, report.user_id, report.room_id)

    # 2. Enforce Data Retention Expiration Check
    if is_dossier_expired(report):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                f"Dossier report '{report_id}' has expired per the "
                f"{settings.DOSSIER_RETENTION_DAYS}-day data retention policy."
            ),
        )

    target_fmt = format.lower()
    clean_ext = ".pdf" if target_fmt == "pdf" else ".json"

    # If redirect requested and Supabase Storage configured, redirect to signed URL
    if redirect and is_supabase_configured():
        signed_url = await dossier_storage.create_signed_url(
            report_id=report.id,
            mission_id=report.mission_id,
            extension=clean_ext,
        )
        if signed_url:
            return RedirectResponse(url=signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    file_path_str = report.pdf_path if target_fmt == "pdf" else report.json_path
    etag_hash = report.pdf_sha256 if target_fmt == "pdf" else report.json_sha256
    media_type = "application/pdf" if target_fmt == "pdf" else "application/json"

    if not file_path_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact for format '{format}' was not generated for this report.",
        )

    artifact_path = Path(file_path_str).resolve()
    storage_dir = Path(settings.DOSSIER_STORAGE_DIR).resolve()

    # 3. Prevent Path Traversal
    if not artifact_path.is_relative_to(storage_dir):
        logger.critical(
            "Security Alert: Path traversal attempt blocked on report download '%s'",
            report_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Illegal storage path traversal attempt detected.",
        )

    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested dossier artifact file is missing on storage.",
        )

    # 4. Enforce Maximum Allowable Download Size
    file_size = artifact_path.stat().st_size
    if file_size > settings.MAX_DOSSIER_DOWNLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"Artifact size ({file_size} bytes) exceeds maximum allowable "
                f"download limit ({settings.MAX_DOSSIER_DOWNLOAD_BYTES} bytes)."
            ),
        )

    safe_title = sanitize_filename(report.title)
    download_filename = f"{safe_title}_{report.id[:8]}.{target_fmt}"

    headers = {
        "Content-Disposition": f'attachment; filename="{download_filename}"',
        "ETag": f'"{etag_hash or ""}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
        "Cache-Control": "private, no-transform, max-age=3600",
    }

    return FileResponse(
        path=str(artifact_path),
        media_type=media_type,
        filename=download_filename,
        headers=headers,
    )


@router.get(
    "/{report_id}/signed-url",
    status_code=status.HTTP_200_OK,
    summary="Generate Expiring Signed Download URL for Dossier Artifact",
)
async def get_dossier_signed_url(
    report_id: str,
    format: str = Query(default="pdf", pattern="^(?i)(pdf|json)$"),
    expires_in: Optional[int] = Query(default=None, ge=60, le=86400),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generates an expiring signed download URL for direct cloud object storage retrieval.
    If Supabase Storage is configured, issues a cryptographically signed URL from Supabase.
    If running locally, returns direct local download route.
    """
    validate_uuid(report_id, "report_id")
    stmt = select(DossierReport).where(DossierReport.id == report_id)
    res = await db.execute(stmt)
    report = res.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dossier report '{report_id}' not found.",
        )

    await assert_dossier_access(db, current_user.id, report.user_id, report.room_id)

    if is_dossier_expired(report):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                f"Dossier report '{report_id}' has expired per retention policy."
            ),
        )

    clean_ext = ".pdf" if format.lower() == "pdf" else ".json"
    ttl = expires_in or settings.SUPABASE_STORAGE_EXPIRING_URL_SECONDS

    signed_url = await dossier_storage.create_signed_url(
        report_id=report.id,
        mission_id=report.mission_id,
        extension=clean_ext,
        expires_in=ttl,
    )

    return {
        "report_id": report.id,
        "mission_id": report.mission_id,
        "format": format.upper(),
        "storage_provider": "supabase" if signed_url else "local",
        "download_url": (
            signed_url or f"/api/v1/dossiers/{report.id}/download?format={format.lower()}"
        ),
        "is_signed_cloud_url": bool(signed_url),
        "expires_in_seconds": ttl,
    }


@router.get(
    "/missions/{mission_id}",
    response_model=DossierReportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Generated Dossiers for a Mission",
)
async def list_mission_dossiers(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DossierReportListResponse:
    """Lists all compiled dossier reports for a mission authorized to the current user."""
    validate_uuid(mission_id, "mission_id")

    # 1. Verify target mission exists
    stmt_m = select(Mission).where(Mission.id == mission_id)
    res_m = await db.execute(stmt_m)
    mission = res_m.scalar_one_or_none()
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission with ID '{mission_id}' not found.",
        )

    # 2. Fetch reports for this mission
    stmt = (
        select(DossierReport)
        .where(DossierReport.mission_id == mission_id)
        .order_by(desc(DossierReport.created_at))
    )
    res = await db.execute(stmt)
    reports = res.scalars().all()

    authorized_reports: List[DossierReportMetadataResponse] = []
    for r in reports:
        # Check authorization
        if r.user_id == current_user.id:
            authorized_reports.append(
                DossierReportMetadataResponse(
                    id=r.id,
                    job_id=r.job_id,
                    mission_id=r.mission_id,
                    room_id=r.room_id,
                    design_id=r.design_id,
                    title=r.title,
                    format=r.format,
                    pdf_size_bytes=r.pdf_size_bytes,
                    pdf_sha256=r.pdf_sha256,
                    json_size_bytes=r.json_size_bytes,
                    json_sha256=r.json_sha256,
                    schema_version=r.schema_version,
                    page_count=r.page_count,
                    created_at=r.created_at,
                    download_url_pdf=(
                        f"/api/v1/dossiers/{r.id}/download?format=pdf" if r.pdf_path else None
                    ),
                    download_url_json=(
                        f"/api/v1/dossiers/{r.id}/download?format=json" if r.json_path else None
                    ),
                )
            )
        elif r.room_id:
            stmt_part = select(CDFRoomParticipant).where(
                and_(
                    CDFRoomParticipant.room_id == r.room_id,
                    CDFRoomParticipant.user_id == current_user.id,
                )
            )
            res_part = await db.execute(stmt_part)
            if res_part.scalar_one_or_none():
                authorized_reports.append(
                    DossierReportMetadataResponse(
                        id=r.id,
                        job_id=r.job_id,
                        mission_id=r.mission_id,
                        room_id=r.room_id,
                        design_id=r.design_id,
                        title=r.title,
                        format=r.format,
                        pdf_size_bytes=r.pdf_size_bytes,
                        pdf_sha256=r.pdf_sha256,
                        json_size_bytes=r.json_size_bytes,
                        json_sha256=r.json_sha256,
                        schema_version=r.schema_version,
                        page_count=r.page_count,
                        created_at=r.created_at,
                        download_url_pdf=(
                            f"/api/v1/dossiers/{r.id}/download?format=pdf" if r.pdf_path else None
                        ),
                        download_url_json=(
                            f"/api/v1/dossiers/{r.id}/download?format=json" if r.json_path else None
                        ),
                    )
                )

    return DossierReportListResponse(
        reports=authorized_reports,
        total=len(authorized_reports),
    )


@router.post(
    "/cleanup",
    status_code=status.HTTP_200_OK,
    summary="Prune Expired Mission Dossiers and Reclaim Storage",
)
async def prune_expired_dossiers(
    max_age_days: Optional[int] = Query(default=None, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Administrative retention cleanup endpoint: removes expired reports older than
    the retention window (default 30 days) and unlinks files to reclaim disk space.
    """
    return await cleanup_expired_dossiers(db, max_age_days=max_age_days)
