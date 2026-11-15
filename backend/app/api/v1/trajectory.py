"""
Astrodynamics & Trajectory Optimization API Endpoints
Mission Forge — Phase 3

Provides versioned REST endpoints for:
1. Direct Lambert boundary-value solver (POST /trajectory/lambert)
2. Direct synchronous porkchop calculation with caching (POST /trajectory/porkchop/calculate)
3. Asynchronous porkchop job submission with duplicate protection (POST /trajectory/porkchop/jobs)
4. Job status and granular progress polling (GET /trajectory/porkchop/jobs/{job_id})
5. Job result retrieval (GET /trajectory/porkchop/jobs/{job_id}/result)
6. Job cancellation (POST /trajectory/porkchop/jobs/{job_id}/cancel)
7. Job cleanup maintenance (DELETE /trajectory/porkchop/jobs/cleanup)
"""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Set
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.astrodynamics.lambert import (
    LambertCollinearError,
    LambertConvergenceError,
    LambertDomainError,
    solve_lambert,
)
from backend.app.astrodynamics.porkchop import PorkchopGenerator, normalize_body_name
from backend.app.core.cache import AsyncCacheManager, CacheStatus
from backend.app.core.database import AsyncSessionLocal, get_db
from backend.app.models.trajectory import PorkchopJob, PorkchopJobStatus
from backend.app.schemas.trajectory import (
    LambertSolveRequest,
    LambertSolveResponse,
    PorkchopJobCreateResponse,
    PorkchopJobStatusResponse,
    PorkchopRequest,
    PorkchopResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trajectory", tags=["Astrodynamics & Trajectory Optimization"])

# Concurrency semaphore for bounded background execution
_JOB_SEMAPHORE = asyncio.Semaphore(4)

# Dynamic in-memory progress tracking for active background jobs
_JOB_PROGRESS: Dict[str, float] = {}

# In-memory tracking of cancelled job IDs to ensure zero-race cancellation
_CANCELLED_JOBS: Set[str] = set()

# In-memory result cache for equivalent scientific porkchop queries
_porkchop_result_cache = AsyncCacheManager(default_ttl_seconds=3600.0, max_entries=200)


@router.post(
    "/lambert",
    response_model=LambertSolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Solve Two-Body Lambert Boundary-Value Problem",
)
async def solve_lambert_endpoint(
    request: LambertSolveRequest,
) -> LambertSolveResponse:
    """
    Computes deterministic two-body Keplerian transfer velocity vectors
    v1 (departure) and v2 (arrival) given position vectors r1, r2, time of flight,
    and central gravitational parameter mu.
    """
    try:
        sol = solve_lambert(
            r1=request.r1_km,
            r2=request.r2_km,
            time_of_flight_s=request.time_of_flight_s,
            mu_km3_s2=request.mu_km3_s2,
            prograde=request.prograde,
            transfer_angle_type=request.transfer_angle_type,
            max_iterations=request.max_iterations,
            tolerance=request.tolerance,
            raise_on_failure=True,
        )
        return LambertSolveResponse(
            v1_kms=sol.v1,
            v2_kms=sol.v2,
            converged=sol.converged,
            iterations=sol.iterations,
            residual=sol.residual,
            semi_major_axis_km=sol.semi_major_axis_km,
            eccentricity=sol.eccentricity,
            transfer_angle_deg=sol.transfer_angle_deg,
            time_of_flight_s=sol.time_of_flight_s,
            solution_branch=sol.solution_branch,
            stumpff_z=sol.stumpff_z,
            units=sol.units,
        )
    except (LambertDomainError, LambertCollinearError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except LambertConvergenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Numerical solver failed to converge: {exc}",
        ) from exc


@router.post(
    "/porkchop/calculate",
    response_model=PorkchopResponse,
    status_code=status.HTTP_200_OK,
    summary="Direct Synchronous Ephemeris Porkchop Analysis",
)
async def calculate_porkchop_direct(
    request: PorkchopRequest,
) -> PorkchopResponse:
    """
    Direct synchronous porkchop plot computation for bounded grid sizes.
    Retrieves real ephemeris states from JPL Horizons, computes 2D mesh of
    Lambert transfer arcs, and returns C3, excess velocities, and Delta-V arrays.
    Equivalent scientific requests are served from the high-speed in-memory cache.
    """
    norm_origin = normalize_body_name(request.origin_body)
    norm_target = normalize_body_name(request.target_body)
    cache_key = (
        f"porkchop:{norm_origin}:{norm_target}:"
        f"{request.departure_start_date}:{request.departure_end_date}:"
        f"{request.arrival_start_date}:{request.arrival_end_date}:"
        f"{request.step_size_days}:{request.dep_parking_alt_km}:{request.arr_parking_alt_km}:"
        f"{request.prograde}"
    )

    cached_data, c_status, _ = await _porkchop_result_cache.get(cache_key)
    if cached_data is not None:
        data_copy = dict(cached_data)
        data_copy["provenance"] = dict(data_copy.get("provenance", {}))
        data_copy["provenance"]["cache_status"] = CacheStatus.CACHED.value
        return PorkchopResponse(**data_copy)

    generator = PorkchopGenerator(max_grid_points=10000)
    try:
        data = await generator.generate_porkchop(
            origin_body=request.origin_body,
            target_body=request.target_body,
            departure_start_date=request.departure_start_date,
            departure_end_date=request.departure_end_date,
            arrival_start_date=request.arrival_start_date,
            arrival_end_date=request.arrival_end_date,
            step_days=request.step_size_days,
            dep_parking_alt_km=request.dep_parking_alt_km,
            arr_parking_alt_km=request.arr_parking_alt_km,
            prograde=request.prograde,
        )
        await _porkchop_result_cache.set(cache_key, data)
        return PorkchopResponse(**data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error in direct porkchop calculation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Porkchop computation failed: {exc}",
        ) from exc


async def _run_porkchop_job_worker(
    job_id: str,
    request_data: Dict[str, Any],
) -> None:
    """
    Asynchronous background worker executing porkchop analysis under bounded concurrency.
    Offloads heavy numerical iterations to a worker thread and streams progress to DB.
    """
    async with _JOB_SEMAPHORE:
        try:
            if job_id in _CANCELLED_JOBS:
                logger.info("Porkchop job %s was cancelled before worker pickup", job_id)
                return

            # 1. Verify job has not been cancelled before starting, mark RUNNING atomically
            async with AsyncSessionLocal() as session:
                stmt_start = (
                    update(PorkchopJob)
                    .where(
                        PorkchopJob.id == job_id,
                        PorkchopJob.status.notin_([
                            PorkchopJobStatus.CANCELLED,
                            PorkchopJobStatus.FAILED,
                            PorkchopJobStatus.COMPLETED,
                        ]),
                    )
                    .values(
                        status=PorkchopJobStatus.RUNNING,
                        progress_percent=5.0,
                    )
                )
                res_start = await session.execute(stmt_start)
                if getattr(res_start, "rowcount", 0) == 0:
                    logger.info(
                        "Porkchop job %s was already cancelled or terminal before start", job_id
                    )
                    await session.rollback()
                    return
                await session.commit()
                _JOB_PROGRESS[job_id] = 5.0

            if job_id in _CANCELLED_JOBS:
                logger.info("Porkchop job %s was cancelled right after start", job_id)
                return

            # Progress callback tracking row-by-row convergence
            def on_computation_progress(pct: float) -> None:
                if job_id not in _CANCELLED_JOBS:
                    _JOB_PROGRESS[job_id] = round(pct, 1)

            # 2. Execute calculation with thread offloading (NO DB connection held!)
            generator = PorkchopGenerator(max_grid_points=10000)
            result_data = await generator.generate_porkchop(
                origin_body=request_data["origin_body"],
                target_body=request_data["target_body"],
                departure_start_date=request_data["departure_start_date"],
                departure_end_date=request_data["departure_end_date"],
                arrival_start_date=request_data["arrival_start_date"],
                arrival_end_date=request_data["arrival_end_date"],
                step_days=request_data.get("step_size_days", 2.0),
                dep_parking_alt_km=request_data.get("dep_parking_alt_km"),
                arr_parking_alt_km=request_data.get("arr_parking_alt_km"),
                prograde=request_data.get("prograde", True),
                on_progress=on_computation_progress,
            )
            result_data["job_id"] = job_id

            if job_id in _CANCELLED_JOBS:
                logger.info("Porkchop job %s was cancelled during computation", job_id)
                return

            # 3. Update status to COMPLETED ONLY IF NOT CANCELLED (Atomic SQL Update)
            async with AsyncSessionLocal() as session:
                stmt_complete = (
                    update(PorkchopJob)
                    .where(
                        PorkchopJob.id == job_id,
                        PorkchopJob.status != PorkchopJobStatus.CANCELLED,
                    )
                    .values(
                        status=PorkchopJobStatus.COMPLETED,
                        progress_percent=100.0,
                        results=result_data,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                res_complete = await session.execute(stmt_complete)
                if getattr(res_complete, "rowcount", 0) == 0:
                    logger.info("Porkchop job %s was cancelled before completion commit", job_id)
                    await session.rollback()
                    return
                await session.commit()
                logger.info("Porkchop job %s completed successfully", job_id)

        except Exception as exc:
            logger.exception("Porkchop job %s failed: %s", job_id, exc)
            if job_id not in _CANCELLED_JOBS:
                try:
                    async with AsyncSessionLocal() as session:
                        stmt_err = (
                            update(PorkchopJob)
                            .where(
                                PorkchopJob.id == job_id,
                                PorkchopJob.status != PorkchopJobStatus.CANCELLED,
                            )
                            .values(
                                status=PorkchopJobStatus.FAILED,
                                error_message=str(exc)[:500],
                                completed_at=datetime.now(timezone.utc),
                            )
                        )
                        await session.execute(stmt_err)
                        await session.commit()
                except Exception as db_exc:
                    logger.error("Failed to persist failure status for job %s: %s", job_id, db_exc)
        finally:
            _JOB_PROGRESS.pop(job_id, None)


@router.post(
    "/porkchop/jobs",
    response_model=PorkchopJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Asynchronous Porkchop Grid Computation Job",
)
@router.post(
    "/porkchop",
    response_model=PorkchopJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Asynchronous Porkchop Grid Computation Job (Alias)",
)
async def submit_porkchop_job(
    request: PorkchopRequest,
    db: AsyncSession = Depends(get_db),
) -> PorkchopJobCreateResponse:
    """
    Submits an asynchronous porkchop grid analysis job.
    Enforces duplicate job protection / idempotency: if an identical active job
    (QUEUED or RUNNING) already exists, returns the existing job ID.
    Persists job in database and schedules computation under a bounded background pool.
    """
    # 1. Estimate total points to reject unbounded requests upfront
    try:
        d_dep_s = datetime.strptime(request.departure_start_date[:10], "%Y-%m-%d").date()
        d_dep_e = datetime.strptime(request.departure_end_date[:10], "%Y-%m-%d").date()
        d_arr_s = datetime.strptime(request.arrival_start_date[:10], "%Y-%m-%d").date()
        d_arr_e = datetime.strptime(request.arrival_end_date[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid date format: {exc}",
        ) from exc

    n_dep = max(1, int((d_dep_e - d_dep_s).days / request.step_size_days) + 1)
    n_arr = max(1, int((d_arr_e - d_arr_s).days / request.step_size_days) + 1)
    total_est = n_dep * n_arr
    if total_est > 10000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Requested grid resolution produces ~{total_est} cells, exceeding "
                "the maximum limit of 10,000. Increase step_size_days or narrow date windows."
            ),
        )

    # 2. Check for identical in-flight job (duplicate job protection)
    norm_origin = normalize_body_name(request.origin_body)
    norm_target = normalize_body_name(request.target_body)
    stmt_dup = select(PorkchopJob).where(
        PorkchopJob.origin_body == norm_origin,
        PorkchopJob.target_body == norm_target,
        PorkchopJob.departure_start == request.departure_start_date,
        PorkchopJob.departure_end == request.departure_end_date,
        PorkchopJob.arrival_start == request.arrival_start_date,
        PorkchopJob.arrival_end == request.arrival_end_date,
        PorkchopJob.step_size_days == request.step_size_days,
        PorkchopJob.status.in_([
            PorkchopJobStatus.QUEUED,
            PorkchopJobStatus.RUNNING,
        ]),
    ).order_by(PorkchopJob.created_at.desc())
    res_dup = await db.execute(stmt_dup)
    existing_jobs = res_dup.scalars().all()
    for existing_job in existing_jobs:
        params = existing_job.parameters or {}
        if (
            params.get("prograde", True) == request.prograde
            and params.get("dep_parking_alt_km") == request.dep_parking_alt_km
            and params.get("arr_parking_alt_km") == request.arr_parking_alt_km
        ):
            logger.info(
                "Returning existing active job %s (status: %s) for duplicate request",
                existing_job.id,
                existing_job.status.value,
            )
            return PorkchopJobCreateResponse(
                job_id=existing_job.id,
                status=existing_job.status,
                created_at=existing_job.created_at,
            )

    # 3. Create new job record
    job = PorkchopJob(
        origin_body=norm_origin,
        target_body=norm_target,
        departure_start=request.departure_start_date,
        departure_end=request.departure_end_date,
        arrival_start=request.arrival_start_date,
        arrival_end=request.arrival_end_date,
        step_size_days=request.step_size_days,
        parameters=request.model_dump(),
        status=PorkchopJobStatus.QUEUED,
        progress_percent=0.0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch asynchronous worker task
    asyncio.create_task(_run_porkchop_job_worker(job.id, request.model_dump()))

    return PorkchopJobCreateResponse(
        job_id=job.id,
        status=job.status,
        created_at=job.created_at,
    )


@router.get(
    "/porkchop/jobs/{job_id}",
    response_model=PorkchopJobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Porkchop Job Status & Progress",
)
@router.get(
    "/porkchop/{job_id}",
    response_model=PorkchopJobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Porkchop Job Status & Progress (Alias)",
)
async def get_porkchop_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> PorkchopJobStatusResponse:
    """Retrieves current execution status, progress percentage, and metadata for a job."""
    stmt = select(PorkchopJob).where(PorkchopJob.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Porkchop job '{job_id}' not found.",
        )

    current_progress = _JOB_PROGRESS.get(job.id, job.progress_percent)
    return PorkchopJobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress_percent=current_progress,
        origin_body=job.origin_body,
        target_body=job.target_body,
        departure_window={
            "start": job.departure_start,
            "end": job.departure_end,
        },
        arrival_window={
            "start": job.arrival_start,
            "end": job.arrival_end,
        },
        step_size_days=job.step_size_days,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


@router.post(
    "/porkchop/jobs/{job_id}/cancel",
    response_model=PorkchopJobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Porkchop Job",
)
async def cancel_porkchop_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> PorkchopJobStatusResponse:
    """Cancels a queued or running porkchop background computation."""
    stmt = select(PorkchopJob).where(PorkchopJob.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Porkchop job '{job_id}' not found.",
        )

    if job.status == PorkchopJobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job '{job_id}' because it has already COMPLETED.",
        )

    if job.status == PorkchopJobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job '{job_id}' because it has already FAILED.",
        )

    if job.status != PorkchopJobStatus.CANCELLED:
        job.status = PorkchopJobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = "Job cancelled by client request."
        _CANCELLED_JOBS.add(job_id)
        _JOB_PROGRESS.pop(job_id, None)
        await db.commit()
        await db.refresh(job)

    current_progress = _JOB_PROGRESS.get(job.id, job.progress_percent)
    return PorkchopJobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress_percent=current_progress,
        origin_body=job.origin_body,
        target_body=job.target_body,
        departure_window={"start": job.departure_start, "end": job.departure_end},
        arrival_window={"start": job.arrival_start, "end": job.arrival_end},
        step_size_days=job.step_size_days,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


@router.get(
    "/porkchop/jobs/{job_id}/result",
    response_model=PorkchopResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Completed Porkchop Grid Dataset",
)
async def get_porkchop_job_result(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> PorkchopResponse:
    """Retrieves complete 2D contour grid results for a completed job."""
    stmt = select(PorkchopJob).where(PorkchopJob.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Porkchop job '{job_id}' not found.",
        )

    if job.status == PorkchopJobStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Porkchop job '{job_id}' was CANCELLED.",
        )

    if job.status == PorkchopJobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Porkchop job failed: {job.error_message}",
        )

    if job.status in (PorkchopJobStatus.QUEUED, PorkchopJobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Job '{job_id}' is still in progress ({job.status.value}, "
                f"progress: {job.progress_percent:.1f}%)."
            ),
        )

    if not job.results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No results found for job '{job_id}'.",
        )

    return PorkchopResponse(**job.results)


async def recover_orphaned_porkchop_jobs(session: AsyncSession) -> int:
    """
    Recovers orphaned in-flight porkchop jobs after application restart.
    Any job persisted as QUEUED or RUNNING whose background task was lost on shutdown
    is transitioned to FAILED with a clear explanation, preventing infinite hangs
    and unblocking duplicate-submission protection.
    """
    stmt = select(PorkchopJob).where(
        PorkchopJob.status.in_([
            PorkchopJobStatus.QUEUED,
            PorkchopJobStatus.RUNNING,
        ])
    )
    res = await session.execute(stmt)
    orphaned_jobs = res.scalars().all()
    count = len(orphaned_jobs)
    now = datetime.now(timezone.utc)
    for job in orphaned_jobs:
        job.status = PorkchopJobStatus.FAILED
        job.error_message = (
            "Server restarted while job was in progress. Please resubmit the calculation."
        )
        job.completed_at = now
    if count > 0:
        await session.commit()
        logger.warning(
            "Recovered %d orphaned porkchop background jobs on application startup", count
        )
    return count


async def cleanup_old_porkchop_jobs(
    db: AsyncSession,
    retention_days: int = 7,
) -> int:
    """Removes finished (completed, failed, cancelled) jobs older than retention threshold."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    stmt = select(PorkchopJob).where(
        PorkchopJob.status.in_([
            PorkchopJobStatus.COMPLETED,
            PorkchopJobStatus.FAILED,
            PorkchopJobStatus.CANCELLED,
        ]),
        PorkchopJob.created_at < cutoff,
    )
    res = await db.execute(stmt)
    old_jobs = res.scalars().all()
    count = len(old_jobs)
    for j in old_jobs:
        await db.delete(j)
    if count > 0:
        await db.commit()
    return count


@router.delete(
    "/porkchop/jobs/cleanup",
    status_code=status.HTTP_200_OK,
    summary="Cleanup Old Finished Porkchop Jobs",
)
async def cleanup_porkchop_jobs_endpoint(
    retention_days: int = Query(default=7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Deletes finished porkchop jobs older than the retention threshold."""
    deleted_count = await cleanup_old_porkchop_jobs(db, retention_days=retention_days)
    return {"deleted_jobs_count": deleted_count, "retention_days": retention_days}
