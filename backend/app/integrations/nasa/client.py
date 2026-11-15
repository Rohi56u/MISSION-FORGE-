"""
Asynchronous NASA Open API Client with Caching, Bounded Retries, and Rate Limit Telemetry.
Provides unified access to official NASA Open APIs (APOD, NeoWS, DONKI, TechPort).
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
import httpx

from backend.app.core.cache import AsyncCacheManager, CacheStatus
from backend.app.core.config import settings
from backend.app.integrations.nasa.exceptions import (
    NasaApiAuthError,
    NasaApiError,
    NasaApiNotFoundError,
    NasaApiRateLimitError,
    NasaApiUpstreamError,
)
from backend.app.integrations.nasa.models import (
    ApodItem,
    CoronalMassEjection,
    DonkiCmeResponse,
    NasaKeyVerificationResult,
    NasaRateLimitInfo,
    NearEarthObject,
    NeoFeedResponse,
)

logger = logging.getLogger(__name__)


class NasaApiClient:
    """
    Asynchronous client for NASA Open APIs (https://api.nasa.gov).
    Authenticates requests using the configured NASA_API_KEY, parses rate limit
    headers, and provides resilient in-memory caching and exponential backoff.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        cache_ttl_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = (base_url or settings.NASA_API_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.NASA_API_KEY
        self.timeout = timeout_seconds or settings.EXTERNAL_API_TIMEOUT_SECONDS
        self.max_retries = max_retries or settings.EXTERNAL_API_MAX_RETRIES
        self.backoff_factor = settings.EXTERNAL_API_BACKOFF_FACTOR

        self.cache = AsyncCacheManager(
            default_ttl_seconds=cache_ttl_seconds or 3600.0
        )

        self.rate_limit: Optional[int] = None
        self.rate_limit_remaining: Optional[int] = None
        self.last_rate_limit_update: Optional[datetime] = None

        headers = {
            "User-Agent": settings.HTTP_USER_AGENT,
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        """Closes the underlying HTTP client session."""
        await self._client.aclose()

    def _mask_key(self, key: Optional[str] = None) -> str:
        """Returns securely masked representation of the API key for safe logging."""
        k = key or self.api_key or ""
        if len(k) <= 8:
            return "***"
        return f"{k[:4]}...{k[-4:]}"

    def _update_rate_limits(self, response: httpx.Response) -> None:
        """Extracts X-RateLimit-Limit and X-RateLimit-Remaining headers."""
        limit_h = response.headers.get("X-RateLimit-Limit")
        remaining_h = response.headers.get("X-RateLimit-Remaining")
        if limit_h is not None:
            try:
                self.rate_limit = int(limit_h)
            except (ValueError, TypeError):
                pass
        if remaining_h is not None:
            try:
                self.rate_limit_remaining = int(remaining_h)
            except (ValueError, TypeError):
                pass
        self.last_rate_limit_update = datetime.now(timezone.utc)

    def get_rate_limit_info(self) -> NasaRateLimitInfo:
        """Returns the current known rate limit status for the API key."""
        return NasaRateLimitInfo(
            limit=self.rate_limit,
            remaining=self.rate_limit_remaining,
            last_checked=self.last_rate_limit_update or datetime.now(timezone.utc),
        )

    async def verify_key(self) -> NasaKeyVerificationResult:
        """
        Executes a live probe against api.nasa.gov to verify API key validity,
        extract confirmed rate limit quotas, and return structured diagnostics.
        """
        masked = self._mask_key()
        params: Dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        # Use APOD with explicit date to get a lightweight deterministic response
        params["date"] = "2024-01-01"

        try:
            response = await self._client.get("/planetary/apod", params=params)
            self._update_rate_limits(response)

            if response.status_code == 200:
                payload = response.json()
                return NasaKeyVerificationResult(
                    valid=True,
                    api_key_masked=masked,
                    rate_limit=self.rate_limit,
                    rate_limit_remaining=self.rate_limit_remaining,
                    status_code=200,
                    message="Official NASA API key authenticated successfully.",
                    endpoints_verified=["/planetary/apod"],
                    raw_sample={"title": payload.get("title"), "date": payload.get("date")},
                )
            elif response.status_code in (401, 403):
                return NasaKeyVerificationResult(
                    valid=False,
                    api_key_masked=masked,
                    rate_limit=self.rate_limit,
                    rate_limit_remaining=self.rate_limit_remaining,
                    status_code=response.status_code,
                    message=f"NASA API key authentication failed with HTTP {response.status_code}.",
                    endpoints_verified=[],
                )
            elif response.status_code == 429:
                return NasaKeyVerificationResult(
                    valid=True,
                    api_key_masked=masked,
                    rate_limit=self.rate_limit,
                    rate_limit_remaining=0,
                    status_code=429,
                    message="NASA API key is valid but the hourly request rate limit is exhausted.",
                    endpoints_verified=[],
                )
            else:
                return NasaKeyVerificationResult(
                    valid=False,
                    api_key_masked=masked,
                    rate_limit=self.rate_limit,
                    rate_limit_remaining=self.rate_limit_remaining,
                    status_code=response.status_code,
                    message=(
                        f"NASA API returned unexpected HTTP status {response.status_code}."
                    ),
                    endpoints_verified=[],
                )
        except httpx.RequestError as exc:
            return NasaKeyVerificationResult(
                valid=False,
                api_key_masked=masked,
                rate_limit=self.rate_limit,
                rate_limit_remaining=self.rate_limit_remaining,
                status_code=0,
                message=f"Network connectivity error contacting NASA API Gateway: {exc}",
                endpoints_verified=[],
            )

    async def get_apod(
        self,
        date: Optional[str] = None,
        allow_stale: bool = True,
    ) -> ApodItem:
        """
        Retrieves Astronomy Picture of the Day (APOD) metadata.
        Supports caching and stale fallback.
        """
        cache_key = f"nasa:apod:{date or 'today'}"
        cached_data, _, _ = await self.cache.get(cache_key, allow_stale=False)
        if cached_data is not None:
            item = ApodItem.model_validate(cached_data)
            item.cache_status = CacheStatus.CACHED
            return item

        params: Dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if date:
            params["date"] = date

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get("/planetary/apod", params=params)
                self._update_rate_limits(response)

                if response.status_code in (401, 403):
                    raise NasaApiAuthError(
                        f"NASA API authentication failed (HTTP {response.status_code}): "
                        f"{response.text}"
                    )
                if response.status_code == 404:
                    raise NasaApiNotFoundError(f"APOD resource not found for date: {date}")
                if response.status_code == 429:
                    raise NasaApiRateLimitError("NASA API rate limit exceeded (HTTP 429).")
                if response.status_code >= 500:
                    raise NasaApiUpstreamError(
                        f"NASA API server error (HTTP {response.status_code})."
                    )
                if response.status_code >= 400:
                    raise NasaApiError(
                        f"NASA API request failed with HTTP {response.status_code}."
                    )

                payload = response.json()
                item = ApodItem(
                    date=str(payload.get("date", date or "")),
                    title=str(payload.get("title", "")),
                    explanation=str(payload.get("explanation", "")),
                    url=str(payload.get("url", "")),
                    hdurl=payload.get("hdurl"),
                    media_type=str(payload.get("media_type", "image")),
                    service_version=payload.get("service_version"),
                    copyright=payload.get("copyright"),
                    retrieved_at=datetime.now(timezone.utc),
                    cache_status=CacheStatus.LIVE,
                )

                await self.cache.set(cache_key, item.model_dump())
                return item

            except (NasaApiAuthError, NasaApiNotFoundError, NasaApiRateLimitError):
                raise

            except (httpx.RequestError, NasaApiUpstreamError, NasaApiError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        if allow_stale:
            stale_data, _, _ = await self.cache.get(cache_key, allow_stale=True)
            if stale_data is not None:
                item = ApodItem.model_validate(stale_data)
                item.cache_status = CacheStatus.STALE
                return item

        raise NasaApiUpstreamError(
            f"Failed to fetch NASA APOD after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    async def get_neo_feed(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        allow_stale: bool = True,
    ) -> NeoFeedResponse:
        """
        Retrieves Near Earth Object asteroid tracking data for a date range.
        """
        end_dt = end_date or start_date
        cache_key = f"nasa:neows:{start_date}:{end_dt}"

        cached_data, _, _ = await self.cache.get(cache_key, allow_stale=False)
        if cached_data is not None:
            resp = NeoFeedResponse.model_validate(cached_data)
            resp.cache_status = CacheStatus.CACHED
            return resp

        params: Dict[str, str] = {
            "start_date": start_date,
            "end_date": end_dt,
        }
        if self.api_key:
            params["api_key"] = self.api_key

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get("/neo/rest/v1/feed", params=params)
                self._update_rate_limits(response)

                if response.status_code in (401, 403):
                    raise NasaApiAuthError(
                        f"NASA NeoWS API authentication failed (HTTP {response.status_code})"
                    )
                if response.status_code == 429:
                    raise NasaApiRateLimitError("NASA NeoWS API rate limit exceeded (HTTP 429)")
                if response.status_code >= 500:
                    raise NasaApiUpstreamError(f"NASA NeoWS returned HTTP {response.status_code}")
                if response.status_code >= 400:
                    raise NasaApiError(
                        f"NASA NeoWS request failed with HTTP {response.status_code}"
                    )

                data = response.json()
                element_count = int(data.get("element_count", 0))
                neo_dict = data.get("near_earth_objects", {})

                objects: List[NearEarthObject] = []
                for _, obj_list in neo_dict.items():
                    for o in obj_list:
                        close_approaches = o.get("close_approach_data", [])
                        ca_date = None
                        miss_km = None
                        rel_vel = None
                        if close_approaches:
                            ca0 = close_approaches[0]
                            ca_date = ca0.get("close_approach_date")
                            try:
                                miss_km = float(ca0.get("miss_distance", {}).get("kilometers", 0))
                            except (ValueError, TypeError):
                                pass
                            try:
                                rel_vel = float(
                                    ca0.get("relative_velocity", {}).get(
                                        "kilometers_per_second", 0
                                    )
                                )
                            except (ValueError, TypeError):
                                pass

                        diam = o.get("estimated_diameter", {}).get("kilometers", {})
                        objects.append(
                            NearEarthObject(
                                id=str(o.get("id")),
                                name=str(o.get("name")),
                                absolute_magnitude_h=o.get("absolute_magnitude_h"),
                                estimated_diameter_min_km=diam.get("estimated_diameter_min"),
                                estimated_diameter_max_km=diam.get("estimated_diameter_max"),
                                is_potentially_hazardous=bool(
                                    o.get("is_potentially_hazardous_asteroid", False)
                                ),
                                close_approach_date=ca_date,
                                miss_distance_km=miss_km,
                                relative_velocity_km_s=rel_vel,
                            )
                        )

                feed = NeoFeedResponse(
                    element_count=element_count,
                    near_earth_objects=objects,
                    retrieved_at=datetime.now(timezone.utc),
                    cache_status=CacheStatus.LIVE,
                )

                await self.cache.set(cache_key, feed.model_dump())
                return feed

            except (NasaApiAuthError, NasaApiRateLimitError):
                raise

            except (httpx.RequestError, NasaApiUpstreamError, NasaApiError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        if allow_stale:
            stale_data, _, _ = await self.cache.get(cache_key, allow_stale=True)
            if stale_data is not None:
                resp = NeoFeedResponse.model_validate(stale_data)
                resp.cache_status = CacheStatus.STALE
                return resp

        raise NasaApiUpstreamError(
            f"Failed to fetch NASA NeoWS feed after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    async def get_donki_cme(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        allow_stale: bool = True,
    ) -> DonkiCmeResponse:
        """
        Retrieves Space Weather Coronal Mass Ejection (CME) data from NASA DONKI.
        """
        cache_key = f"nasa:donki:cme:{start_date or 'default'}:{end_date or 'default'}"
        cached_data, _, _ = await self.cache.get(cache_key, allow_stale=False)
        if cached_data is not None:
            resp = DonkiCmeResponse.model_validate(cached_data)
            resp.cache_status = CacheStatus.CACHED
            return resp

        params: Dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get("/DONKI/CME", params=params)
                self._update_rate_limits(response)

                if response.status_code in (401, 403):
                    raise NasaApiAuthError(
                        f"NASA DONKI API authentication failed (HTTP {response.status_code})"
                    )
                if response.status_code == 429:
                    raise NasaApiRateLimitError("NASA DONKI API rate limit exceeded (HTTP 429)")
                if response.status_code >= 500:
                    raise NasaApiUpstreamError(f"NASA DONKI returned HTTP {response.status_code}")
                if response.status_code >= 400:
                    raise NasaApiError(
                        f"NASA DONKI request failed with HTTP {response.status_code}"
                    )

                raw_list = response.json()
                if not isinstance(raw_list, list):
                    raw_list = []

                events: List[CoronalMassEjection] = []
                for item in raw_list:
                    inst_list: List[str] = []
                    for inst in item.get("instruments", []):
                        if isinstance(inst, dict) and "displayName" in inst:
                            inst_list.append(inst["displayName"])

                    events.append(
                        CoronalMassEjection(
                            activity_id=str(item.get("activityID", "")),
                            catalog=item.get("catalog"),
                            start_time=str(item.get("startTime", "")),
                            source_location=item.get("sourceLocation"),
                            note=item.get("note"),
                            instruments=inst_list,
                        )
                    )

                cme_resp = DonkiCmeResponse(
                    count=len(events),
                    events=events,
                    retrieved_at=datetime.now(timezone.utc),
                    cache_status=CacheStatus.LIVE,
                )

                await self.cache.set(cache_key, cme_resp.model_dump())
                return cme_resp

            except (NasaApiAuthError, NasaApiRateLimitError):
                raise

            except (httpx.RequestError, NasaApiUpstreamError, NasaApiError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        if allow_stale:
            stale_data, _, _ = await self.cache.get(cache_key, allow_stale=True)
            if stale_data is not None:
                resp = DonkiCmeResponse.model_validate(stale_data)
                resp.cache_status = CacheStatus.STALE
                return resp

        raise NasaApiUpstreamError(
            f"Failed to fetch NASA DONKI CME data after {self.max_retries} attempts: "
            f"{last_exception}"
        ) from last_exception


# Global singleton instance for application use
nasa_api_client = NasaApiClient()
