"""
NASA DSN Now API Endpoints
Provides live and cached tracking status from the official NASA Deep Space Network feed.
"""

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.integrations.dsn import (
    DSNFeedResponse,
    DSNParseError,
    DSNSpacecraftTrackingResponse,
    DSNUpstreamError,
    dsn_client,
)

router = APIRouter(prefix="/dsn", tags=["NASA Deep Space Network Now"])


@router.get(
    "/now",
    response_model=DSNFeedResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current NASA DSN Now Live Tracking Status",
)
@router.get(
    "/status",
    response_model=DSNFeedResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current NASA DSN Now Live Tracking Status (Status Alias)",
)
async def get_dsn_now_feed(
    allow_stale: bool = Query(
        default=True,
        description="Serve cached data if live NASA DSN feed is temporarily unreachable",
    ),
) -> DSNFeedResponse:
    """
    Returns live tracking status across the three DSN complexes:
    Goldstone (California), Madrid (Spain), and Canberra (Australia).
    Includes antenna pointing, up/down carrier signals, data rates, and round-trip light time.
    """
    try:
        return await dsn_client.get_feed(allow_stale=allow_stale)
    except DSNParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to parse upstream NASA DSN Now XML feed: {exc}",
        ) from exc
    except DSNUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NASA DSN Now feed temporarily unavailable: {exc}",
        ) from exc


@router.get(
    "/spacecraft/{target}",
    response_model=DSNSpacecraftTrackingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get DSN Tracking Status for a Specific Spacecraft",
)
async def get_dsn_spacecraft_tracking(
    target: str,
    allow_stale: bool = Query(
        default=True,
        description="Serve cached tracking data if upstream feed is temporarily unavailable",
    ),
) -> DSNSpacecraftTrackingResponse:
    """
    Filters the DSN feed for contacts and active radio frequency links
    associated with a specific spacecraft callsign/mission code (e.g. M01O, MRO, JWST, VGR1).
    """
    try:
        return await dsn_client.get_spacecraft(target=target, allow_stale=allow_stale)
    except DSNParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to parse upstream NASA DSN Now XML feed: {exc}",
        ) from exc
    except DSNUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NASA DSN Now feed temporarily unavailable: {exc}",
        ) from exc
