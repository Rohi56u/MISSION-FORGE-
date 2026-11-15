"""
Unit and Integration Tests for NASA Open API Gateway Integration
Tests APOD, NeoWS, DONKI CME, Rate Limit Telemetry, Caching, and FastAPI Endpoints.
"""

from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, MockTransport, Response

from backend.app.core.cache import CacheStatus
from backend.app.integrations.nasa import (
    ApodItem,
    DonkiCmeResponse,
    NasaApiClient,
    NasaApiNotFoundError,
    NasaApiRateLimitError,
    NasaKeyVerificationResult,
    NeoFeedResponse,
)


# =========================================================================
# 1. CLIENT TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_nasa_client_verify_key_success():
    """Live key verification probe extracts rate limits and returns valid=True."""
    def handler(request):
        headers = {
            "Content-Type": "application/json",
            "X-RateLimit-Limit": "2000",
            "X-RateLimit-Remaining": "1995",
        }
        return Response(
            200,
            json={"title": "Test Cosmos", "date": "2024-01-01"},
            headers=headers,
        )

    client = NasaApiClient(api_key="test_key_12345", transport=MockTransport(handler))
    try:
        res = await client.verify_key()
        assert isinstance(res, NasaKeyVerificationResult)
        assert res.valid is True
        assert res.rate_limit == 2000
        assert res.rate_limit_remaining == 1995
        assert res.status_code == 200
        assert "authenticated" in res.message.lower()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_nasa_client_verify_key_invalid():
    """Invalid API key returns valid=False with HTTP 403."""
    def handler(request):
        return Response(403, json={"error": {"code": "API_KEY_INVALID"}})

    client = NasaApiClient(api_key="invalid_key", transport=MockTransport(handler))
    try:
        res = await client.verify_key()
        assert res.valid is False
        assert res.status_code == 403
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_nasa_client_get_apod():
    """Retrieves and parses APOD item with caching."""
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return Response(
            200,
            json={
                "date": "2024-01-01",
                "title": "Cosmic Nebulae",
                "explanation": "A breathtaking cloud of interstellar dust.",
                "url": "https://apod.nasa.gov/apod/image/2401/nebula.jpg",
                "hdurl": "https://apod.nasa.gov/apod/image/2401/nebula_hd.jpg",
                "media_type": "image",
            },
        )

    client = NasaApiClient(
        api_key="test_key",
        transport=MockTransport(handler),
        cache_ttl_seconds=300.0,
    )
    try:
        apod1 = await client.get_apod("2024-01-01")
        assert isinstance(apod1, ApodItem)
        assert apod1.title == "Cosmic Nebulae"
        assert apod1.cache_status == CacheStatus.LIVE
        assert calls == 1

        # Second request served from cache
        apod2 = await client.get_apod("2024-01-01")
        assert apod2.cache_status == CacheStatus.CACHED
        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_nasa_client_apod_not_found():
    """Missing APOD resource raises NasaApiNotFoundError."""
    def handler(request):
        return Response(404, json={"error": "Date not available"})

    client = NasaApiClient(transport=MockTransport(handler))
    try:
        with pytest.raises(NasaApiNotFoundError):
            await client.get_apod("1900-01-01")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_nasa_client_neo_feed():
    """Retrieves and aggregates Near-Earth Asteroid feed."""
    def handler(request):
        return Response(
            200,
            json={
                "element_count": 1,
                "near_earth_objects": {
                    "2024-01-01": [
                        {
                            "id": "3542519",
                            "name": "(2010 PK9)",
                            "absolute_magnitude_h": 21.8,
                            "estimated_diameter": {
                                "kilometers": {
                                    "estimated_diameter_min": 0.11,
                                    "estimated_diameter_max": 0.25,
                                }
                            },
                            "is_potentially_hazardous_asteroid": True,
                            "close_approach_data": [
                                {
                                    "close_approach_date": "2024-01-01",
                                    "miss_distance": {"kilometers": "4500000"},
                                    "relative_velocity": {"kilometers_per_second": "18.5"},
                                }
                            ],
                        }
                    ]
                },
            },
        )

    client = NasaApiClient(transport=MockTransport(handler))
    try:
        feed = await client.get_neo_feed("2024-01-01", "2024-01-01")
        assert isinstance(feed, NeoFeedResponse)
        assert feed.element_count == 1
        assert len(feed.near_earth_objects) == 1
        obj = feed.near_earth_objects[0]
        assert obj.name == "(2010 PK9)"
        assert obj.is_potentially_hazardous is True
        assert obj.miss_distance_km == 4500000.0
        assert obj.relative_velocity_km_s == 18.5
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_nasa_client_donki_cme():
    """Retrieves Coronal Mass Ejection event data from DONKI."""
    def handler(request):
        return Response(
            200,
            json=[
                {
                    "activityID": "2024-01-02T12:00:00-CME-001",
                    "catalog": "M2M_CATALOG",
                    "startTime": "2024-01-02T12:00Z",
                    "sourceLocation": "N15W25",
                    "note": "Halo CME detected by SOHO/LASCO",
                    "instruments": [{"displayName": "SOHO: LASCO/C2"}],
                }
            ],
        )

    client = NasaApiClient(transport=MockTransport(handler))
    try:
        cme = await client.get_donki_cme("2024-01-01", "2024-01-05")
        assert isinstance(cme, DonkiCmeResponse)
        assert cme.count == 1
        assert len(cme.events) == 1
        assert cme.events[0].activity_id == "2024-01-02T12:00:00-CME-001"
        assert cme.events[0].instruments == ["SOHO: LASCO/C2"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_nasa_client_rate_limit_error():
    """HTTP 429 raises NasaApiRateLimitError."""
    def handler(request):
        return Response(429, json={"error": "OVER_RATE_LIMIT"})

    client = NasaApiClient(transport=MockTransport(handler))
    try:
        with pytest.raises(NasaApiRateLimitError):
            await client.get_apod("2024-01-01")
    finally:
        await client.aclose()


# =========================================================================
# 2. FASTAPI ROUTE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_api_nasa_status(async_client: AsyncClient, monkeypatch):
    """GET /api/v1/nasa/status returns 200 with verification diagnostics."""
    from backend.app.api.v1.nasa import nasa_api_client

    async def mock_verify():
        return NasaKeyVerificationResult(
            valid=True,
            api_key_masked="qTzR...czNk6",
            rate_limit=2000,
            rate_limit_remaining=1998,
            status_code=200,
            message="Verified OK",
            endpoints_verified=["/planetary/apod"],
        )

    monkeypatch.setattr(nasa_api_client, "verify_key", mock_verify)

    response = await async_client.get("/api/v1/nasa/status")
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["rate_limit"] == 2000
    assert data["rate_limit_remaining"] == 1998


@pytest.mark.asyncio
async def test_api_nasa_apod(async_client: AsyncClient, monkeypatch):
    """GET /api/v1/nasa/apod returns 200 with astronomy picture item."""
    from backend.app.api.v1.nasa import nasa_api_client

    async def mock_apod(date=None, allow_stale=True):
        return ApodItem(
            date="2024-01-01",
            title="Hubble Deep Field",
            explanation="Distant galaxies across cosmic time.",
            url="https://example.com/hubble.jpg",
            media_type="image",
        )

    monkeypatch.setattr(nasa_api_client, "get_apod", mock_apod)

    response = await async_client.get("/api/v1/nasa/apod?date=2024-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Hubble Deep Field"
    assert data["date"] == "2024-01-01"


@pytest.mark.asyncio
async def test_api_nasa_neo_feed(async_client: AsyncClient, monkeypatch):
    """GET /api/v1/nasa/neo/feed returns 200 with near-Earth objects."""
    from backend.app.api.v1.nasa import nasa_api_client
    from backend.app.integrations.nasa.models import NearEarthObject

    async def mock_feed(start_date, end_date=None, allow_stale=True):
        return NeoFeedResponse(
            element_count=1,
            near_earth_objects=[
                NearEarthObject(
                    id="99999",
                    name="Apophis",
                    is_potentially_hazardous=True,
                )
            ],
            retrieved_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(nasa_api_client, "get_neo_feed", mock_feed)

    response = await async_client.get("/api/v1/nasa/neo/feed?start_date=2029-04-13")
    assert response.status_code == 200
    data = response.json()
    assert data["element_count"] == 1
    assert data["near_earth_objects"][0]["name"] == "Apophis"


@pytest.mark.asyncio
async def test_api_nasa_donki_cme(async_client: AsyncClient, monkeypatch):
    """GET /api/v1/nasa/donki/cme returns 200 with solar eruption events."""
    from backend.app.api.v1.nasa import nasa_api_client
    from backend.app.integrations.nasa.models import CoronalMassEjection

    async def mock_cme(start_date=None, end_date=None, allow_stale=True):
        return DonkiCmeResponse(
            count=1,
            events=[
                CoronalMassEjection(
                    activity_id="CME-001",
                    start_time="2024-01-01T00:00Z",
                    catalog="M2M",
                )
            ],
            retrieved_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(nasa_api_client, "get_donki_cme", mock_cme)

    response = await async_client.get("/api/v1/nasa/donki/cme")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["events"][0]["activity_id"] == "CME-001"
