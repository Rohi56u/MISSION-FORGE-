"""
Asynchronous NASA DSN Now Client with Caching and Stale Fallback
Polls official Deep Space Network live tracking status XML feed.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional
import httpx

from backend.app.core.cache import AsyncCacheManager, CacheStatus
from backend.app.core.config import settings
from backend.app.integrations.dsn.exceptions import (
    DSNParseError,
    DSNUpstreamError,
)
from backend.app.integrations.dsn.models import (
    DSNFeedResponse,
    DSNSpacecraftContact,
    DSNSpacecraftTrackingResponse,
)
from backend.app.integrations.dsn.parser import parse_dsn_xml

logger = logging.getLogger(__name__)


class DSNNowClient:
    """
    Asynchronous client for NASA DSN Now live feed (eyes.nasa.gov/dsn/data/dsn.xml).
    Enforces safe XML parsing, SI unit tracking, caching, and graceful failure.
    """

    def __init__(
        self,
        feed_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        cache_ttl_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.feed_url = feed_url or settings.DSN_FEED_URL
        self.timeout = timeout_seconds or settings.EXTERNAL_API_TIMEOUT_SECONDS
        self.max_retries = max_retries or settings.EXTERNAL_API_MAX_RETRIES
        self.backoff_factor = settings.EXTERNAL_API_BACKOFF_FACTOR

        self.cache = AsyncCacheManager(
            default_ttl_seconds=cache_ttl_seconds or float(settings.DSN_CACHE_TTL_SECONDS)
        )

        headers = {
            "User-Agent": settings.HTTP_USER_AGENT,
            "Accept": "application/xml, text/xml, */*",
        }
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        """Closes the underlying HTTP client and releases resources."""
        await self._client.aclose()

    async def get_feed(self, allow_stale: bool = True) -> DSNFeedResponse:
        """
        Retrieves the current NASA DSN Now live tracking feed.
        Returns normalized complex, dish, signal, and target data.
        """
        cache_key = "dsn:now:feed"

        # 1. Check cache for fresh entry
        cached_data, cache_status, retrieved_at = await self.cache.get(
            cache_key, allow_stale=False
        )
        if cached_data is not None:
            logger.debug("NASA DSN Now cache hit (fresh)")
            resp = DSNFeedResponse.model_validate(cached_data)
            resp.cache_status = CacheStatus.CACHED
            return resp

        # 2. Execute upstream request with bounded retries
        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get(self.feed_url)

                if response.status_code >= 500:
                    raise DSNUpstreamError(
                        f"NASA DSN Now returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                if response.status_code >= 400:
                    raise DSNUpstreamError(
                        f"NASA DSN Now request failed with HTTP {response.status_code}"
                    )

                xml_text = response.text
                parsed = parse_dsn_xml(
                    xml_content=xml_text,
                    source_url=self.feed_url,
                    cache_status=CacheStatus.LIVE,
                    retrieved_at=datetime.now(timezone.utc),
                )

                # Store in cache
                await self.cache.set(
                    cache_key,
                    parsed.model_dump(),
                    source_timestamp=parsed.source_timestamp,
                )
                logger.info(
                    "NASA DSN Now feed retrieved (live): stations=%d tracked_spacecraft=%d",
                    len(parsed.stations),
                    len(parsed.tracked_spacecraft),
                )
                return parsed

            except DSNParseError:
                # Do not retry parse errors
                raise

            except (httpx.RequestError, DSNUpstreamError) as exc:
                last_exception = exc
                logger.warning(
                    "NASA DSN Now attempt %d/%d failed: %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    backoff = self.backoff_factor * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)

        # 3. Fallback to stale cached feed if available
        if allow_stale:
            stale_data, stale_status, retrieved_at = await self.cache.get(
                cache_key, allow_stale=True
            )
            if stale_data is not None:
                logger.warning(
                    "NASA DSN Now upstream unreachable; serving stale cached tracking data."
                )
                resp = DSNFeedResponse.model_validate(stale_data)
                resp.cache_status = CacheStatus.STALE
                return resp

        raise DSNUpstreamError(
            f"Failed to fetch NASA DSN Now feed after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    async def get_spacecraft(
        self,
        target: str,
        allow_stale: bool = True,
    ) -> DSNSpacecraftTrackingResponse:
        """
        Retrieves active tracking contacts and telemetry signals for a specific spacecraft target.
        Searches all complexes and antennas in the live feed.
        """
        feed = await self.get_feed(allow_stale=allow_stale)
        clean_target = target.strip().upper()
        matching_contacts = []

        for station in feed.stations:
            for dish in station.dishes:
                # Check if dish targets match
                matched_target = None
                for tgt in dish.targets:
                    if tgt.name and tgt.name.upper() == clean_target:
                        matched_target = tgt
                        break

                # Check if up or down signals match spacecraft code
                matching_up = [
                    s for s in dish.up_signals
                    if s.spacecraft and s.spacecraft.upper() == clean_target
                ]
                matching_down = [
                    s for s in dish.down_signals
                    if s.spacecraft and s.spacecraft.upper() == clean_target
                ]

                # Assign signals strictly belonging to this spacecraft.
                # Fall back to unassigned signals only if this dish has exactly one target
                # and that single target matches the requested spacecraft.
                final_up = list(matching_up)
                final_down = list(matching_down)

                if not final_up and len(dish.targets) == 1 and matched_target:
                    final_up = [
                        s for s in dish.up_signals
                        if not s.spacecraft or s.spacecraft.upper() in ("NONE", "UNKNOWN", "")
                    ]
                if not final_down and len(dish.targets) == 1 and matched_target:
                    final_down = [
                        s for s in dish.down_signals
                        if not s.spacecraft or s.spacecraft.upper() in ("NONE", "UNKNOWN", "")
                    ]

                if matched_target or final_up or final_down:
                    matching_contacts.append(
                        DSNSpacecraftContact(
                            station_name=station.name,
                            station_friendly_name=station.friendly_name,
                            dish_name=dish.name,
                            activity=dish.activity,
                            azimuth_deg=dish.azimuth_deg,
                            elevation_deg=dish.elevation_deg,
                            wind_speed_kmh=dish.wind_speed_kmh,
                            is_mspa=dish.is_mspa,
                            is_array=dish.is_array,
                            is_ddor=dish.is_ddor,
                            target=matched_target,
                            up_signals=final_up,
                            down_signals=final_down,
                        )
                    )

        return DSNSpacecraftTrackingResponse(
            spacecraft=clean_target,
            is_actively_tracked=len(matching_contacts) > 0,
            contacts=matching_contacts,
            retrieved_at=feed.retrieved_at,
            source_timestamp=feed.source_timestamp,
            cache_status=feed.cache_status,
            source_url=feed.source_url,
        )


# Global singleton instance for application use
dsn_client = DSNNowClient()
