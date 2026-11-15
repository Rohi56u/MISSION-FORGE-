"""
NASA/JPL Horizons API Endpoints
Provides typed, validated access to JPL ephemeris vectors and orbital elements.
"""

from typing import List
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.integrations.horizons import (
    HorizonsAmbiguousTargetError,
    HorizonsEphemType,
    HorizonsParseError,
    HorizonsQueryRequest,
    HorizonsQueryResponse,
    HorizonsRefPlane,
    HorizonsRefSystem,
    HorizonsTargetCandidate,
    HorizonsTargetNotFoundError,
    HorizonsTimeScale,
    HorizonsUpstreamError,
    HorizonsValidationError,
    horizons_client,
)

router = APIRouter(prefix="/horizons", tags=["JPL Horizons Ephemeris"])


@router.post(
    "/query",
    response_model=HorizonsQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query JPL Horizons Ephemeris or Orbital Elements",
)
async def query_horizons_post(
    request: HorizonsQueryRequest,
    allow_stale: bool = Query(
        default=True,
        description="Whether to return cached stale data during upstream Horizons outages",
    ),
) -> HorizonsQueryResponse:
    """
    Queries official NASA/JPL Horizons API for Cartesian state vectors
    or Keplerian orbital elements.
    """
    try:
        return await horizons_client.query(request, allow_stale=allow_stale)
    except HorizonsValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except HorizonsTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HorizonsAmbiguousTargetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "candidates": [c.model_dump() for c in exc.candidates],
            },
        ) from exc
    except HorizonsParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to parse JPL Horizons response: {exc}",
        ) from exc
    except HorizonsUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"JPL Horizons service unavailable: {exc}",
        ) from exc


@router.get(
    "/query",
    response_model=HorizonsQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query JPL Horizons via GET Parameters",
)
async def query_horizons_get(
    target: str = Query(..., description="Target body name or ID (e.g. '399', '499', 'MARS')"),
    center: str = Query(default="500@0", description="Coordinate center (default: 500@0 SSB)"),
    ephem_type: HorizonsEphemType = Query(
        default=HorizonsEphemType.VECTORS, description="VECTORS or ELEMENTS"
    ),
    start_time: str = Query(default="2026-01-01", description="Start time"),
    stop_time: str = Query(default="2026-01-02", description="Stop time"),
    step_size: str = Query(default="1d", description="Time step (e.g. '1d', '6h')"),
    ref_plane: HorizonsRefPlane = Query(default=HorizonsRefPlane.FRAME),
    ref_system: HorizonsRefSystem = Query(default=HorizonsRefSystem.J2000),
    time_scale: HorizonsTimeScale = Query(default=HorizonsTimeScale.TDB),
    allow_stale: bool = Query(default=True),
) -> HorizonsQueryResponse:
    """Convenience GET endpoint for Horizons queries."""
    req = HorizonsQueryRequest(
        target=target,
        center=center,
        ephem_type=ephem_type,
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        ref_plane=ref_plane,
        ref_system=ref_system,
        time_scale=time_scale,
    )
    return await query_horizons_post(req, allow_stale=allow_stale)


@router.get(
    "/vectors",
    response_model=HorizonsQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query JPL Horizons Cartesian State Vectors",
)
async def get_horizons_vectors(
    target: str = Query(..., description="Target body name or ID (e.g. '399', '499', 'MARS')"),
    center: str = Query(default="500@0", description="Coordinate center (default: 500@0 SSB)"),
    start_time: str = Query(default="2026-01-01", description="Start time"),
    stop_time: str = Query(default="2026-01-02", description="Stop time"),
    step_size: str = Query(default="1d", description="Time step (e.g. '1d', '6h')"),
    ref_plane: HorizonsRefPlane = Query(default=HorizonsRefPlane.FRAME),
    ref_system: HorizonsRefSystem = Query(default=HorizonsRefSystem.J2000),
    time_scale: HorizonsTimeScale = Query(default=HorizonsTimeScale.TDB),
    allow_stale: bool = Query(default=True),
) -> HorizonsQueryResponse:
    """Dedicated convenience GET endpoint for Cartesian state vectors (position and velocity)."""
    return await query_horizons_get(
        target=target,
        center=center,
        ephem_type=HorizonsEphemType.VECTORS,
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        ref_plane=ref_plane,
        ref_system=ref_system,
        time_scale=time_scale,
        allow_stale=allow_stale,
    )


@router.get(
    "/elements",
    response_model=HorizonsQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query JPL Horizons Osculating Keplerian Elements",
)
async def get_horizons_elements(
    target: str = Query(..., description="Target body name or ID (e.g. '399', '499', 'MARS')"),
    center: str = Query(default="500@0", description="Coordinate center (default: 500@0 SSB)"),
    start_time: str = Query(default="2026-01-01", description="Start time"),
    stop_time: str = Query(default="2026-01-02", description="Stop time"),
    step_size: str = Query(default="1d", description="Time step (e.g. '1d', '6h')"),
    ref_plane: HorizonsRefPlane = Query(default=HorizonsRefPlane.ECLIPTIC),
    ref_system: HorizonsRefSystem = Query(default=HorizonsRefSystem.J2000),
    time_scale: HorizonsTimeScale = Query(default=HorizonsTimeScale.TDB),
    allow_stale: bool = Query(default=True),
) -> HorizonsQueryResponse:
    """Dedicated convenience GET endpoint for osculating Keplerian orbital elements."""
    return await query_horizons_get(
        target=target,
        center=center,
        ephem_type=HorizonsEphemType.ELEMENTS,
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        ref_plane=ref_plane,
        ref_system=ref_system,
        time_scale=time_scale,
        allow_stale=allow_stale,
    )


@router.get(
    "/targets",
    response_model=List[HorizonsTargetCandidate],
    status_code=status.HTTP_200_OK,
    summary="Search Horizons Celestial Body Identifiers",
)
async def search_horizons_targets(
    query: str = Query(..., min_length=1, description="Body search query (e.g. 'Mars', 'Europa')"),
) -> List[HorizonsTargetCandidate]:
    """Searches body designations and IDs in the Horizons database."""
    return await horizons_client.search_targets(query)
