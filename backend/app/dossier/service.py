"""
Asynchronous Mission Dossier Compilation and Generation Service
Mission Forge — Phase 6
"""

import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.dossier.builder import compile_dossier_snapshot
from backend.app.dossier.pdf_generator import render_dossier_pdf
from backend.app.dossier.storage import dossier_storage
from backend.app.models.auth import User
from backend.app.models.dossier import DossierFormat, DossierJob, DossierReport, DossierReportStatus

logger = logging.getLogger(__name__)

# Bounded Concurrency Semaphore for asynchronous report rendering
_DOSSIER_SEMAPHORE = asyncio.Semaphore(settings.DOSSIER_MAX_CONCURRENT_JOBS)

# In-memory progress tracking for real-time polling
_DOSSIER_PROGRESS: Dict[str, float] = {}

# In-memory sliding window rate limiter store: (user_id:action) -> list of timestamps
_DOSSIER_RATE_LIMITS: Dict[str, List[float]] = {}

_SESSION_FACTORY: Any = None


def check_dossier_rate_limit(user_id: str, action: str = "generate") -> Tuple[bool, int]:
    """
    Sliding-window in-memory rate limiter for dossier operations.
    Returns (allowed: bool, retry_after_seconds: int).
    """
    now = time.time()
    window_seconds = 60.0
    if action == "generate":
        max_requests = settings.DOSSIER_RATE_LIMIT_GENERATE_PER_MINUTE
    else:
        max_requests = settings.DOSSIER_RATE_LIMIT_DOWNLOAD_PER_MINUTE

    key = f"{user_id}:{action}"
    history = _DOSSIER_RATE_LIMITS.setdefault(key, [])

    # Filter out timestamps older than the sliding window
    cutoff = now - window_seconds
    _DOSSIER_RATE_LIMITS[key] = [t for t in history if t > cutoff]
    history = _DOSSIER_RATE_LIMITS[key]

    if len(history) >= max_requests:
        oldest = history[0]
        retry_after = max(1, int(oldest + window_seconds - now))
        return False, retry_after

    history.append(now)
    return True, 0


def reset_dossier_rate_limits() -> None:
    """Resets rate limiting state (useful for test isolation)."""
    _DOSSIER_RATE_LIMITS.clear()


def is_dossier_expired(report: DossierReport) -> bool:
    """Checks whether a dossier report has exceeded the retention window."""
    if not report.created_at:
        return False
    created_at = report.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    return (now_utc - created_at) > timedelta(days=settings.DOSSIER_RETENTION_DAYS)


async def cleanup_expired_dossiers(
    session: AsyncSession,
    max_age_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Prunes expired dossier report artifacts and records according to retention policy.
    Removes files from disk and purges historical records past the retention horizon.
    """
    retention_days = max_age_days if max_age_days is not None else settings.DOSSIER_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    stmt_reports = select(DossierReport).where(DossierReport.created_at < cutoff)
    res_reports = await session.execute(stmt_reports)
    expired_reports = res_reports.scalars().all()

    cleaned_count = 0
    reclaimed_bytes = 0

    storage_dir = get_storage_dir()
    for report in expired_reports:
        for path_attr, ext in ((report.pdf_path, ".pdf"), (report.json_path, ".json")):
            if path_attr:
                try:
                    p = Path(path_attr).resolve()
                    if p.is_relative_to(storage_dir) and p.exists() and p.is_file():
                        reclaimed_bytes += p.stat().st_size
                except OSError as e:
                    logger.warning("Failed to inspect expired dossier file '%s': %s", path_attr, e)
                await dossier_storage.delete_artifact(
                    report_id=report.id,
                    mission_id=report.mission_id,
                    extension=ext,
                    local_path_str=path_attr,
                )
        await session.delete(report)
        cleaned_count += 1

    await session.commit()
    logger.info(
        "Dossier retention cleanup: purged %d expired reports, reclaimed %d bytes.",
        cleaned_count,
        reclaimed_bytes,
    )
    return {
        "cleaned_reports_count": cleaned_count,
        "reclaimed_bytes": reclaimed_bytes,
        "cutoff_utc": cutoff.isoformat(),
        "retention_days": retention_days,
    }


def get_session_factory() -> Any:
    """Returns the active async sessionmaker factory."""
    if _SESSION_FACTORY is not None:
        return _SESSION_FACTORY
    from backend.app.core.database import AsyncSessionLocal
    return AsyncSessionLocal


def set_session_factory(factory: Any) -> None:
    """Configures a custom sessionmaker for testing isolation."""
    global _SESSION_FACTORY
    _SESSION_FACTORY = factory


def get_storage_dir() -> Path:
    """Resolves and ensures the persistent directory for generated dossier artifacts."""
    storage_path = Path(settings.DOSSIER_STORAGE_DIR).resolve()
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def get_dossier_file_path(report_id: str, extension: str) -> Path:
    """
    Safely resolves an artifact file path, strictly guaranteeing no path traversal.
    """
    clean_ext = ".pdf" if extension.lower() in (".pdf", "pdf") else ".json"
    clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", report_id)
    if not clean_id:
        clean_id = str(uuid.uuid4())

    storage_dir = get_storage_dir()
    target_path = (storage_dir / f"{clean_id}{clean_ext}").resolve()

    if not target_path.is_relative_to(storage_dir):
        raise ValueError("Illegal path traversal detected in dossier filename.")

    return target_path


async def recover_orphaned_dossier_jobs(session: AsyncSession) -> int:
    """
    Startup recovery procedure: Transitions any orphaned background jobs
    left in QUEUED or GENERATING state from a previous server restart to FAILED.
    """
    stmt = (
        update(DossierJob)
        .where(DossierJob.status.in_([DossierReportStatus.QUEUED, DossierReportStatus.GENERATING]))
        .values(
            status=DossierReportStatus.FAILED,
            error_message=(
                "Process restarted before dossier generation completed; "
                "marked as failed during startup recovery."
            ),
            completed_at=datetime.now(timezone.utc),
        )
    )
    res = await session.execute(stmt)
    await session.commit()
    recovered_count = int(getattr(res, "rowcount", 0))
    if recovered_count > 0:
        logger.warning(
            "Startup recovery: marked %d orphaned dossier jobs as FAILED.",
            recovered_count,
        )
    return recovered_count


async def run_dossier_generation_job(
    job_id: str,
    mission_id: str,
    user_id: str,
    room_id: Optional[str] = None,
    design_id: Optional[str] = None,
    trajectory_job_id: Optional[str] = None,
    custom_title: Optional[str] = None,
    format_pref: DossierFormat = DossierFormat.BOTH,
    include_cdf_history: bool = True,
    include_fdir_audit: bool = True,
    include_capcom_summary: bool = True,
) -> None:
    """
    Asynchronously compiles frozen mission snapshot and renders PDF and/or JSON artifacts.
    Executes within bounded concurrency semaphore and offloads CPU-heavy rendering to threads.
    """
    tmp_files_to_clean: list[Path] = []
    _DOSSIER_PROGRESS[job_id] = 5.0

    session_maker = get_session_factory()
    async with _DOSSIER_SEMAPHORE:
        async with session_maker() as session:
            try:
                # 1. Update Job Status to GENERATING
                _DOSSIER_PROGRESS[job_id] = 15.0
                await session.execute(
                    update(DossierJob)
                    .where(DossierJob.id == job_id)
                    .values(
                        status=DossierReportStatus.GENERATING,
                        progress_percent=15.0,
                    )
                )
                await session.commit()

                # 2. Retrieve User Entity
                stmt_u = select(User).where(User.id == user_id)
                res_u = await session.execute(stmt_u)
                user = res_u.scalar_one_or_none()
                if not user:
                    raise ValueError(f"User '{user_id}' no longer exists.")

                # 3. Compile Frozen Mission Snapshot
                _DOSSIER_PROGRESS[job_id] = 35.0
                await session.execute(
                    update(DossierJob)
                    .where(DossierJob.id == job_id)
                    .values(progress_percent=35.0)
                )
                await session.commit()

                snapshot_data = await compile_dossier_snapshot(
                    db=session,
                    mission_id=mission_id,
                    user=user,
                    room_id=room_id,
                    design_id=design_id,
                    trajectory_job_id=trajectory_job_id,
                    custom_title=custom_title,
                    include_cdf_history=include_cdf_history,
                    include_fdir_audit=include_fdir_audit,
                    include_capcom_summary=include_capcom_summary,
                )

                report_id = str(uuid.uuid4())
                pdf_path_str: Optional[str] = None
                pdf_size: Optional[int] = None
                pdf_sha: Optional[str] = None
                json_path_str: Optional[str] = None
                json_size: Optional[int] = None
                json_sha: Optional[str] = None

                # 4. Generate JSON Artifact (Atomic Write & Storage Integration)
                if format_pref in (DossierFormat.JSON, DossierFormat.BOTH):
                    _DOSSIER_PROGRESS[job_id] = 55.0
                    canonical_json = json.dumps(snapshot_data, indent=2, sort_keys=True)
                    json_bytes = canonical_json.encode("utf-8")
                    json_sha = hashlib.sha256(json_bytes).hexdigest()
                    json_size = len(json_bytes)

                    stored_json = await dossier_storage.store_artifact(
                        report_id=report_id,
                        mission_id=mission_id,
                        extension=".json",
                        data=json_bytes,
                        content_type="application/json",
                    )
                    json_path_str = stored_json["local_path"]

                # 5. Render 5-Page PDF Artifact in Worker Thread & Storage Integration
                if format_pref in (DossierFormat.PDF, DossierFormat.BOTH):
                    _DOSSIER_PROGRESS[job_id] = 75.0
                    await session.execute(
                        update(DossierJob)
                        .where(DossierJob.id == job_id)
                        .values(progress_percent=75.0)
                    )
                    await session.commit()

                    pdf_bytes = await asyncio.to_thread(render_dossier_pdf, snapshot_data)
                    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
                    pdf_size = len(pdf_bytes)

                    stored_pdf = await dossier_storage.store_artifact(
                        report_id=report_id,
                        mission_id=mission_id,
                        extension=".pdf",
                        data=pdf_bytes,
                        content_type="application/pdf",
                    )
                    pdf_path_str = stored_pdf["local_path"]

                # 6. Persist Immutable Dossier Report Record
                _DOSSIER_PROGRESS[job_id] = 95.0
                report = DossierReport(
                    id=report_id,
                    job_id=job_id,
                    mission_id=mission_id,
                    user_id=user_id,
                    room_id=room_id,
                    design_id=design_id,
                    title=snapshot_data.get("title", f"Mission Concept Dossier: {mission_id}"),
                    format=format_pref.value,
                    pdf_path=pdf_path_str,
                    pdf_size_bytes=pdf_size,
                    pdf_sha256=pdf_sha,
                    json_path=json_path_str,
                    json_size_bytes=json_size,
                    json_sha256=json_sha,
                    schema_version="1.0.0",
                    snapshot_data=snapshot_data,
                    page_count=5,
                )
                session.add(report)

                # 7. Complete Job
                now_utc = datetime.now(timezone.utc)
                await session.execute(
                    update(DossierJob)
                    .where(DossierJob.id == job_id)
                    .values(
                        status=DossierReportStatus.COMPLETED,
                        progress_percent=100.0,
                        report_id=report_id,
                        completed_at=now_utc,
                    )
                )
                await session.commit()
                _DOSSIER_PROGRESS[job_id] = 100.0
                logger.info(
                    "Dossier job '%s' completed successfully. Report '%s' generated.",
                    job_id,
                    report_id,
                )

            except Exception as exc:
                # Cleanup any orphaned partial files
                for tmp_p in tmp_files_to_clean:
                    try:
                        if tmp_p.exists():
                            tmp_p.unlink()
                    except OSError:
                        pass

                error_msg = f"Dossier compilation failed: {str(exc)}"
                logger.error(
                    "Dossier job '%s' encountered an error: %s",
                    job_id,
                    error_msg,
                    exc_info=True,
                )
                _DOSSIER_PROGRESS[job_id] = 0.0

                try:
                    await session.execute(
                        update(DossierJob)
                        .where(DossierJob.id == job_id)
                        .values(
                            status=DossierReportStatus.FAILED,
                            error_message=error_msg,
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                except Exception as db_exc:
                    logger.error(
                        "Failed to mark dossier job '%s' as FAILED in database: %s",
                        job_id,
                        db_exc,
                    )
