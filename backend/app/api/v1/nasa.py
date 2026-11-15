"""
NASA Open API Endpoints
Provides direct access to NASA Open API Gateway services:
APOD, NeoWS, DONKI CME, and Rate Limit Telemetry.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.integrations.nasa import (
    ApodItem,
    DonkiCmeResponse,
    NasaApiAuthError,
    NasaApiNotFoundError,
    NasaApiRateLimitError,
    NasaApiUpstreamError,
    NasaKeyVerificationResult,
    NasaRateLimitInfo,
    NeoFeedResponse,
    nasa_api_client,
)

router = APIRouter(prefix="/nasa", tags=["NASA Open APIs"])


@router.get(
    "/status",
    response_model=NasaKeyVerificationResult,
    status_code=status.HTTP_200_OK,
    summary="Verify NASA API Key & Rate Limits",
)
async def get_nasa_status() -> NasaKeyVerificationResult:
    """
    Performs a live probe against the official NASA API Gateway using configured credentials.
    Returns validation status, confirmed rate limits, and remaining request quotas.
    """
    return await nasa_api_client.verify_key()


@router.get(
    "/rate-limit",
    response_model=NasaRateLimitInfo,
    status_code=status.HTTP_200_OK,
    summary="Get Cached NASA Rate Limit Quota",
)
async def get_rate_limit() -> NasaRateLimitInfo:
    """
    Returns latest known rate limit information recorded from NASA API Gateway responses.
    """
    return nasa_api_client.get_rate_limit_info()


@router.get(
    "/apod",
    response_model=ApodItem,
    status_code=status.HTTP_200_OK,
    summary="Get NASA Astronomy Picture of the Day",
)
async def get_apod(
    date: Optional[str] = Query(
        default=None,
        description="Date in YYYY-MM-DD format (defaults to latest available)",
    ),
    allow_stale: bool = Query(default=True),
) -> ApodItem:
    """
    Retrieves NASA Astronomy Picture of the Day (APOD) metadata and imagery.
    """
    try:
        return await nasa_api_client.get_apod(date=date, allow_stale=allow_stale)
    except NasaApiAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except NasaApiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except NasaApiRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except NasaApiUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NASA API Gateway unavailable: {exc}",
        ) from exc


@router.get(
    "/neo/feed",
    response_model=NeoFeedResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Near Earth Objects Asteroid Feed",
)
async def get_neo_feed(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    allow_stale: bool = Query(default=True),
) -> NeoFeedResponse:
    """
    Retrieves asteroid tracking, miss distances, and relative velocities from NASA NeoWS.
    """
    try:
        return await nasa_api_client.get_neo_feed(
            start_date=start_date, end_date=end_date, allow_stale=allow_stale
        )
    except NasaApiAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except NasaApiRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except NasaApiUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NASA NeoWS API unavailable: {exc}",
        ) from exc


@router.get(
    "/donki/cme",
    response_model=DonkiCmeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Space Weather Coronal Mass Ejections (CME)",
)
async def get_donki_cme(
    start_date: Optional[str] = Query(default=None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    allow_stale: bool = Query(default=True),
) -> DonkiCmeResponse:
    """
    Retrieves space weather Coronal Mass Ejections (CMEs) from NASA DONKI.
    """
    try:
        return await nasa_api_client.get_donki_cme(
            start_date=start_date, end_date=end_date, allow_stale=allow_stale
        )
    except NasaApiAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except NasaApiRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except NasaApiUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NASA DONKI API unavailable: {exc}",
        ) from exc
