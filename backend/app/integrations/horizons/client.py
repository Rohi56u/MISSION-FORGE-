"""
Asynchronous NASA/JPL Horizons Client with Caching, Retries, and Stale Fallback
Authoritative adapter for official JPL Solar System Dynamics ephemeris service.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
import httpx

from backend.app.core.cache import AsyncCacheManager, CacheStatus
from backend.app.core.config import settings
from backend.app.integrations.horizons.exceptions import (
    HorizonsAmbiguousTargetError,
    HorizonsTargetNotFoundError,
    HorizonsUpstreamError,
    HorizonsValidationError,
)
from backend.app.integrations.horizons.models import (
    HorizonsEphemType,
    HorizonsQueryRequest,
    HorizonsQueryResponse,
    HorizonsTargetCandidate,
)
from backend.app.integrations.horizons.parser import (
    parse_ambiguous_targets,
    parse_horizons_response,
)

logger = logging.getLogger(__name__)


class HorizonsClient:
    """
    Asynchronous client for the NASA/JPL Horizons Ephemeris API.
    Enforces bounded retries, parameter validation, SI normalization, and caching.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        cache_ttl_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = base_url or settings.HORIZONS_API_BASE_URL
        self.timeout = timeout_seconds or settings.EXTERNAL_API_TIMEOUT_SECONDS
        self.max_retries = max_retries or settings.EXTERNAL_API_MAX_RETRIES
        self.backoff_factor = settings.EXTERNAL_API_BACKOFF_FACTOR

        self.cache = AsyncCacheManager(
            default_ttl_seconds=cache_ttl_seconds or float(settings.HORIZONS_CACHE_TTL_SECONDS)
        )

        headers = {
            "User-Agent": settings.HTTP_USER_AGENT,
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        """Closes the underlying HTTP client and releases resources."""
        await self._client.aclose()

    def _generate_cache_key(self, req: HorizonsQueryRequest) -> str:
        """Constructs a deterministic cache key for an ephemeris query."""
        return (
            f"horizons:{req.target.strip().upper()}:"
            f"{req.center.strip().upper()}:"
            f"{req.ephem_type.value}:"
            f"{req.start_time.strip()}:"
            f"{req.stop_time.strip()}:"
            f"{req.step_size.strip()}:"
            f"{req.ref_plane.value}:"
            f"{req.ref_system.value}:"
            f"{req.time_scale.value}"
        )

    def _build_query_params(self, req: HorizonsQueryRequest) -> Dict[str, str]:
        """Translates validated domain model into Horizons URL query parameters."""
        time_type = "UT" if req.time_scale.value in ("UTC", "UT") else "TDB"
        params: Dict[str, str] = {
            "format": "json",
            "COMMAND": f"'{req.target}'",
            "CENTER": f"'{req.center}'",
            "EPHEM_TYPE": f"'{req.ephem_type.value}'",
            "START_TIME": f"'{req.start_time}'",
            "STOP_TIME": f"'{req.stop_time}'",
            "STEP_SIZE": f"'{req.step_size}'",
            "REF_PLANE": f"'{req.ref_plane.value}'",
            "REF_SYSTEM": f"'{req.ref_system.value}'",
            "TIME_TYPE": f"'{time_type}'",
            "TIME_DIGITS": "'FRACSEC'",
            "OUT_UNITS": "'KM-S'",
            "CSV_FORMAT": "'NO'",
        }
        if req.ephem_type == HorizonsEphemType.VECTORS:
            params["VEC_TABLE"] = "'3'"
        return params

    async def query(
        self,
        request: HorizonsQueryRequest,
        allow_stale: bool = True,
    ) -> HorizonsQueryResponse:
        """
        Executes a validated ephemeris or orbital elements query against JPL Horizons.
        Returns normalized response with coordinate frame, units, and cache status.
        """
        cache_key = self._generate_cache_key(request)

        # 1. Check cache for fresh entry
        cached_data, cache_status, retrieved_at = await self.cache.get(
            cache_key, allow_stale=False
        )
        if cached_data is not None:
            logger.info("JPL Horizons cache hit (fresh): key=%s", cache_key)
            resp = HorizonsQueryResponse.model_validate(cached_data)
            resp.cache_status = CacheStatus.CACHED
            return resp

        # 2. Build upstream request parameters
        params = self._build_query_params(request)
        source_url = str(self._client.build_request("GET", "", params=params).url)

        # 3. Execute HTTP request with bounded exponential backoff retries
        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get("", params=params)

                # Check for 5xx server errors (retryable)
                if response.status_code >= 500:
                    raise HorizonsUpstreamError(
                        f"JPL Horizons returned HTTP {response.status_code}: {response.text[:200]}"
                    )

                # Check for 4xx client errors (non-retryable)
                if response.status_code >= 400:
                    raise HorizonsValidationError(
                        f"JPL Horizons rejected query with HTTP {response.status_code}: "
                        f"{response.text[:200]}"
                    )

                try:
                    raw_json = response.json()
                except Exception as json_err:
                    raise HorizonsUpstreamError(
                        f"JPL Horizons returned non-JSON response: {json_err}"
                    ) from json_err

                # Parse and validate response
                query_meta = request.model_dump()
                parsed = parse_horizons_response(
                    raw_json=raw_json,
                    query_params=query_meta,
                    source_url=source_url,
                    cache_status=CacheStatus.LIVE,
                    retrieved_at=datetime.now(timezone.utc),
                )

                # Store successful parsed model in cache
                await self.cache.set(cache_key, parsed.model_dump())
                logger.info(
                    "JPL Horizons query successful (live): target=%s records=%d",
                    request.target,
                    len(parsed.vectors) or len(parsed.elements),
                )
                return parsed

            except (
                HorizonsValidationError,
                HorizonsTargetNotFoundError,
                HorizonsAmbiguousTargetError,
            ):
                # Non-retryable errors: do not retry
                raise

            except (httpx.RequestError, HorizonsUpstreamError) as exc:
                last_exception = exc
                logger.warning(
                    "JPL Horizons attempt %d/%d failed: %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    backoff = self.backoff_factor * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)

        # 4. If all retries failed and allow_stale is enabled, fallback to stale cache
        if allow_stale:
            stale_data, stale_status, retrieved_at = await self.cache.get(
                cache_key, allow_stale=True
            )
            if stale_data is not None:
                logger.warning(
                    "JPL Horizons upstream unreachable; serving stale cached data for %s",
                    cache_key,
                )
                resp = HorizonsQueryResponse.model_validate(stale_data)
                resp.cache_status = CacheStatus.STALE
                return resp

        raise HorizonsUpstreamError(
            f"Failed to query JPL Horizons after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    async def search_targets(self, query: str) -> List[HorizonsTargetCandidate]:
        """
        Searches target names or small bodies in the JPL Horizons database.
        Returns candidates if ambiguous or matched.
        """
        params = {
            "format": "json",
            "COMMAND": f"'{query.strip()}'",
        }
        try:
            response = await self._client.get("", params=params)
            if response.status_code >= 400:
                return []
            raw_json = response.json()
            result_text = raw_json.get("result", "")
            return parse_ambiguous_targets(result_text)
        except Exception as exc:
            logger.warning("Error searching Horizons targets: %s", exc)
            return []


# Global singleton instance for application use
horizons_client = HorizonsClient()
