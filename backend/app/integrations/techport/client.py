"""
Asynchronous NASA TechPort Client with Caching, Retries, and Stale Fallback
Authoritative adapter for official NASA Space Technology Mission Directorate TechPort API.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import httpx

from backend.app.core.cache import AsyncCacheManager, CacheStatus
from backend.app.core.config import settings
from backend.app.integrations.techport.exceptions import (
    TechPortNotFoundError,
    TechPortUpstreamError,
)
from backend.app.integrations.techport.models import (
    TechPortListResponse,
    TechPortProjectDetail,
    TechPortProjectSummary,
)

logger = logging.getLogger(__name__)


class TechPortClient:
    """
    Asynchronous client for the official NASA TechPort REST API (techport.nasa.gov/api).
    Enforces caching, bounded retries, and strict data-model boundary separation.
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
        self.base_url = (base_url or settings.TECHPORT_API_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.NASA_API_KEY
        self.timeout = timeout_seconds or settings.EXTERNAL_API_TIMEOUT_SECONDS
        self.max_retries = max_retries or settings.EXTERNAL_API_MAX_RETRIES
        self.backoff_factor = settings.EXTERNAL_API_BACKOFF_FACTOR
        self.rate_limit: Optional[int] = None
        self.rate_limit_remaining: Optional[int] = None

        self.cache = AsyncCacheManager(
            default_ttl_seconds=cache_ttl_seconds or float(settings.TECHPORT_CACHE_TTL_SECONDS)
        )

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

    def _update_rate_limits(self, response: httpx.Response) -> None:
        """Parses NASA API Gateway rate limit headers if present."""
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

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """Sanitizes sensitive api_key query parameters from stored or logged URLs."""
        import re
        return re.sub(r"([?&]api_key=)[^&]+", r"\1REDACTED", url)

    async def aclose(self) -> None:
        """Closes the underlying HTTP client and releases resources."""
        await self._client.aclose()

    async def list_projects(
        self,
        updated_since: Optional[str] = None,
        allow_stale: bool = True,
    ) -> TechPortListResponse:
        """
        Lists NASA TechPort technology projects.
        Supports filtering by lastUpdated timestamp.
        """
        cache_key = f"techport:projects:list:{updated_since or 'all'}"

        cached_data, cache_status, _ = await self.cache.get(cache_key, allow_stale=False)
        if cached_data is not None:
            resp = TechPortListResponse.model_validate(cached_data)
            resp.cache_status = CacheStatus.CACHED
            return resp

        params: Dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if updated_since:
            params["updatedSince"] = updated_since

        raw_url = str(self._client.build_request("GET", "/projects", params=params).url)
        source_url = self._sanitize_url(raw_url)

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get("/projects", params=params)
                self._update_rate_limits(response)

                if response.status_code >= 500:
                    raise TechPortUpstreamError(
                        f"NASA TechPort returned HTTP {response.status_code}"
                    )
                if response.status_code >= 400:
                    raise TechPortUpstreamError(
                        f"NASA TechPort request failed with HTTP {response.status_code}"
                    )

                data = response.json()
                raw_projects = data.get("projects", [])
                total_count = data.get("totalCount", len(raw_projects))

                items: List[TechPortProjectSummary] = []
                for p in raw_projects:
                    pid = p.get("projectId") or p.get("id")
                    title = p.get("title") or f"Project {pid}"
                    last_up = p.get("lastUpdated")
                    if pid is not None:
                        items.append(
                            TechPortProjectSummary(
                                id=int(pid),
                                title=str(title),
                                last_updated=str(last_up) if last_up else None,
                            )
                        )

                result = TechPortListResponse(
                    total_count=int(total_count),
                    projects=items,
                    retrieved_at=datetime.now(timezone.utc),
                    cache_status=CacheStatus.LIVE,
                    source_url=source_url,
                    rate_limit=self.rate_limit,
                    rate_limit_remaining=self.rate_limit_remaining,
                )

                await self.cache.set(cache_key, result.model_dump())
                return result

            except (httpx.RequestError, TechPortUpstreamError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        if allow_stale:
            stale_data, _, _ = await self.cache.get(cache_key, allow_stale=True)
            if stale_data is not None:
                resp = TechPortListResponse.model_validate(stale_data)
                resp.cache_status = CacheStatus.STALE
                return resp

        raise TechPortUpstreamError(
            f"Failed to list NASA TechPort projects after {self.max_retries} attempts: "
            f"{last_exception}"
        ) from last_exception

    async def search_projects(
        self,
        query: str,
        allow_stale: bool = True,
    ) -> TechPortListResponse:
        """
        Searches NASA TechPort projects by title or technology keywords.
        """
        cleaned_query = query.strip()
        cache_key = f"techport:projects:search:{cleaned_query.lower()}"

        cached_data, _, _ = await self.cache.get(cache_key, allow_stale=False)
        if cached_data is not None:
            resp = TechPortListResponse.model_validate(cached_data)
            resp.cache_status = CacheStatus.CACHED
            return resp

        params = {"searchQuery": cleaned_query}
        if self.api_key:
            params["api_key"] = self.api_key

        raw_url = str(
            self._client.build_request("GET", "/projects/search", params=params).url
        )
        source_url = self._sanitize_url(raw_url)

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get("/projects/search", params=params)
                self._update_rate_limits(response)

                if response.status_code >= 500:
                    raise TechPortUpstreamError(
                        f"NASA TechPort search returned HTTP {response.status_code}"
                    )
                if response.status_code >= 400:
                    raise TechPortUpstreamError(
                        f"NASA TechPort search failed with HTTP {response.status_code}"
                    )

                data = response.json()
                raw_projects = (
                    data.get("projects") or data.get("results") or []
                )
                total_count = data.get("totalCount") or data.get("total") or len(raw_projects)

                items: List[TechPortProjectSummary] = []
                for p in raw_projects:
                    pid = p.get("projectId") or p.get("id")
                    title = p.get("title") or f"Project {pid}"
                    last_up = p.get("lastUpdated")
                    if pid is not None:
                        items.append(
                            TechPortProjectSummary(
                                id=int(pid),
                                title=str(title),
                                last_updated=str(last_up) if last_up else None,
                            )
                        )

                result = TechPortListResponse(
                    total_count=int(total_count),
                    projects=items,
                    retrieved_at=datetime.now(timezone.utc),
                    cache_status=CacheStatus.LIVE,
                    source_url=source_url,
                    rate_limit=self.rate_limit,
                    rate_limit_remaining=self.rate_limit_remaining,
                )

                await self.cache.set(cache_key, result.model_dump())
                return result

            except (httpx.RequestError, TechPortUpstreamError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        if allow_stale:
            stale_data, _, _ = await self.cache.get(cache_key, allow_stale=True)
            if stale_data is not None:
                resp = TechPortListResponse.model_validate(stale_data)
                resp.cache_status = CacheStatus.STALE
                return resp

        raise TechPortUpstreamError(
            f"Failed to search NASA TechPort projects after {self.max_retries} attempts: "
            f"{last_exception}"
        ) from last_exception

    async def get_project(
        self,
        project_id: int,
        allow_stale: bool = True,
    ) -> TechPortProjectDetail:
        """
        Retrieves complete metadata and TRL progression for a single NASA TechPort project.
        """
        cache_key = f"techport:project:{project_id}"

        cached_data, _, _ = await self.cache.get(cache_key, allow_stale=False)
        if cached_data is not None:
            resp = TechPortProjectDetail.model_validate(cached_data)
            resp.cache_status = CacheStatus.CACHED
            return resp

        endpoint = f"/projects/{project_id}"
        canonical_url = f"https://techport.nasa.gov/view/{project_id}"
        params: Dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                response = await self._client.get(endpoint, params=params)
                self._update_rate_limits(response)

                if response.status_code == 404:
                    raise TechPortNotFoundError(
                        f"NASA TechPort project ID '{project_id}' not found."
                    )
                if response.status_code >= 500:
                    raise TechPortUpstreamError(
                        f"NASA TechPort returned HTTP {response.status_code}"
                    )
                if response.status_code >= 400:
                    raise TechPortUpstreamError(
                        f"NASA TechPort request failed with HTTP {response.status_code}"
                    )

                data = response.json()
                p = data.get("project", data)

                # Extract lead organization string
                lead_org = p.get("leadOrganization")
                lead_org_name: Optional[str] = None
                if isinstance(lead_org, dict):
                    lead_org_name = lead_org.get("organizationName") or lead_org.get("name")
                elif isinstance(lead_org, str):
                    lead_org_name = lead_org

                # Extract program string
                prog = p.get("program")
                prog_name: Optional[str] = None
                if isinstance(prog, dict):
                    prog_name = prog.get("title") or prog.get("name")
                elif isinstance(prog, str):
                    prog_name = prog

                # Extract taxonomy
                prim_tx = p.get("primaryTx") or p.get("primaryTaxonomyNodes")
                prim_tx_str: Optional[str] = None
                if isinstance(prim_tx, dict):
                    prim_tx_str = prim_tx.get("title") or prim_tx.get("name")
                elif isinstance(prim_tx, str):
                    prim_tx_str = prim_tx

                def _int_or_none(v: Any) -> Optional[int]:
                    try:
                        return int(v) if v is not None else None
                    except (ValueError, TypeError):
                        return None

                detail = TechPortProjectDetail(
                    id=project_id,
                    title=str(p.get("title", f"TechPort Project {project_id}")),
                    status=p.get("status") or p.get("statusDescription"),
                    description=p.get("description"),
                    benefits=p.get("benefits"),
                    lead_organization=lead_org_name,
                    program=prog_name,
                    trl_begin=_int_or_none(p.get("trlBegin")),
                    trl_current=_int_or_none(p.get("trlCurrent")),
                    trl_end=_int_or_none(p.get("trlEnd")),
                    last_updated=p.get("lastUpdated"),
                    canonical_url=canonical_url,
                    primary_taxonomy=prim_tx_str,
                    raw_payload=data,
                    retrieved_at=datetime.now(timezone.utc),
                    cache_status=CacheStatus.LIVE,
                    rate_limit=self.rate_limit,
                    rate_limit_remaining=self.rate_limit_remaining,
                )

                await self.cache.set(cache_key, detail.model_dump())
                return detail

            except TechPortNotFoundError:
                raise

            except (httpx.RequestError, TechPortUpstreamError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        if allow_stale:
            stale_data, _, _ = await self.cache.get(cache_key, allow_stale=True)
            if stale_data is not None:
                resp = TechPortProjectDetail.model_validate(stale_data)
                resp.cache_status = CacheStatus.STALE
                return resp

        raise TechPortUpstreamError(
            f"Failed to fetch NASA TechPort project {project_id} after "
            f"{self.max_retries} attempts: {last_exception}"
        ) from last_exception


# Global singleton instance for application use
techport_client = TechPortClient()
