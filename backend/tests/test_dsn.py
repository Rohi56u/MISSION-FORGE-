"""
Unit and Integration Tests for NASA DSN Now Adapter and API
Tests XML feed parsing, all 3 tracking complexes, antennas, radio links,
caching, retries, stale fallback, and FastAPI endpoint.
"""

from pathlib import Path
import pytest
from httpx import AsyncClient, MockTransport, Response

from backend.app.core.cache import CacheStatus
from backend.app.integrations.dsn import (
    DSNFeedResponse,
    DSNNowClient,
    DSNParseError,
    DSNUpstreamError,
    parse_dsn_xml,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def dsn_xml_fixture() -> str:
    with open(FIXTURES_DIR / "dsn_now.xml", encoding="utf-8") as f:
        return f.read()


# =========================================================================
# 1. XML PARSER DETERMINISTIC TESTS
# =========================================================================

def test_dsn_xml_parsing_all_stations(dsn_xml_fixture):
    """Parses real DSN Now XML feed and verifies all 3 complexes."""
    resp = parse_dsn_xml(
        dsn_xml_fixture,
        source_url="https://eyes.nasa.gov/dsn/data/dsn.xml",
    )

    assert isinstance(resp, DSNFeedResponse)
    assert len(resp.stations) == 3

    station_names = {s.friendly_name for s in resp.stations}
    assert station_names == {"Goldstone", "Madrid", "Canberra"}

    # Verify Goldstone dishes
    gdscc = next(s for s in resp.stations if s.name == "gdscc")
    assert len(gdscc.dishes) == 5
    dish_names = [d.name for d in gdscc.dishes]
    assert "DSS14" in dish_names
    assert "DSS25" in dish_names


def test_dsn_xml_antenna_metrics_and_signals(dsn_xml_fixture):
    """Verifies antenna pointing, up/down signals, and sentinel value normalization."""
    resp = parse_dsn_xml(dsn_xml_fixture, source_url="http://test")

    # Inspect all dishes to verify pointing angles and signal structures
    all_dishes = [d for s in resp.stations for d in s.dishes]
    assert len(all_dishes) == 15

    for dish in all_dishes:
        if dish.azimuth_deg is not None:
            assert 0.0 <= dish.azimuth_deg <= 360.0
        if dish.elevation_deg is not None:
            assert 0.0 <= dish.elevation_deg <= 90.0

    # Ensure tracked missions were detected
    assert len(resp.tracked_spacecraft) > 0
    assert resp.active_tracking_count > 0
    assert resp.source_timestamp is not None


def test_dsn_xml_sentinel_normalization():
    """Sentinel values (-1 for range/rtlt, empty string for wind) map to None."""
    sample_xml = """<dsn>
        <station name="gdscc" friendlyName="Goldstone" timeUTC="1794646741000"
                 timeZoneOffset="-28800000.0"/>
        <dish name="DSS14" azimuthAngle="0" elevationAngle="90" windSpeed=""
              isMSPA="false" isArray="false" isDDOR="false" activity="Test">
            <target name="TEST_SAT" id="99" uplegRange="-1" downlegRange="-1" rtlt="-1"/>
            <upSignal active="false" signalType="none" dataRate="0" frequency="0"
                      band="X" power="0"/>
        </dish>
        <timestamp>1794646741000</timestamp>
    </dsn>"""

    resp = parse_dsn_xml(sample_xml, source_url="http://test")
    assert len(resp.stations) == 1
    dish = resp.stations[0].dishes[0]

    assert dish.wind_speed_kmh is None
    assert len(dish.targets) == 1
    tgt = dish.targets[0]
    assert tgt.upleg_range_km is None
    assert tgt.downleg_range_km is None
    assert tgt.rtlt_seconds is None


def test_dsn_xml_empty_input_raises_parse_error():
    """Empty or whitespace-only feed raises DSNParseError."""
    with pytest.raises(DSNParseError):
        parse_dsn_xml("", source_url="http://test")

    with pytest.raises(DSNParseError):
        parse_dsn_xml("   \n  ", source_url="http://test")


def test_dsn_xml_malformed_xml_raises_parse_error():
    """Corrupted XML syntax raises DSNParseError."""
    with pytest.raises(DSNParseError):
        parse_dsn_xml("<dsn><station unclosed", source_url="http://test")


def test_dsn_xml_invalid_root_raises_parse_error():
    """XML with unexpected root element raises DSNParseError."""
    with pytest.raises(DSNParseError):
        parse_dsn_xml("<not_dsn><station/></not_dsn>", source_url="http://test")


# =========================================================================
# 2. CLIENT CACHING, RETRIES, AND STALE FALLBACK
# =========================================================================

@pytest.mark.asyncio
async def test_dsn_client_caching(dsn_xml_fixture):
    """Client serves fresh cached feed on subsequent calls within TTL."""
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return Response(200, text=dsn_xml_fixture)

    client = DSNNowClient(
        transport=MockTransport(handler),
        cache_ttl_seconds=15.0,
    )

    try:
        # First call -> LIVE
        r1 = await client.get_feed()
        assert r1.cache_status == CacheStatus.LIVE
        assert calls == 1

        # Second call -> CACHED
        r2 = await client.get_feed()
        assert r2.cache_status == CacheStatus.CACHED
        assert calls == 1  # No additional network request
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_dsn_client_stale_fallback(dsn_xml_fixture):
    """Client falls back to stale cache during upstream network outages."""
    fail = False

    def handler(request):
        if fail:
            return Response(503, text="DSN Gateway Busy")
        return Response(200, text=dsn_xml_fixture)

    client = DSNNowClient(
        transport=MockTransport(handler),
        cache_ttl_seconds=0.01,
    )

    try:
        # 1. Seed cache
        r1 = await client.get_feed()
        assert r1.cache_status == CacheStatus.LIVE

        # Invalidate TTL
        entry = client.cache._store["dsn:now:feed"]
        entry.expires_at = entry.created_at

        # 2. Simulate upstream failure
        fail = True

        # 3. Retrieve with allow_stale -> STALE
        r2 = await client.get_feed(allow_stale=True)
        assert r2.cache_status == CacheStatus.STALE
        assert len(r2.stations) == 3
    finally:
        await client.aclose()


# =========================================================================
# 3. FASTAPI ROUTE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_api_dsn_now_endpoint(
    async_client: AsyncClient,
    dsn_xml_fixture,
    monkeypatch,
):
    """GET /api/v1/dsn/now returns 200 with all 3 complexes."""
    from backend.app.api.v1.dsn import dsn_client

    async def mock_feed(allow_stale=True):
        return parse_dsn_xml(
            dsn_xml_fixture,
            source_url="http://mock-dsn",
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(dsn_client, "get_feed", mock_feed)

    response = await async_client.get("/api/v1/dsn/now")
    assert response.status_code == 200
    data = response.json()
    assert "stations" in data
    assert len(data["stations"]) == 3
    assert data["cache_status"] == "LIVE"
    assert "active_tracking_count" in data
    assert "tracked_spacecraft" in data


@pytest.mark.asyncio
async def test_api_dsn_now_upstream_error(
    async_client: AsyncClient,
    monkeypatch,
):
    """Upstream failure without cache returns 503 Service Unavailable."""
    from backend.app.api.v1.dsn import dsn_client

    async def mock_failing_feed(allow_stale=True):
        raise DSNUpstreamError("Connection to DSN gateway timed out")

    monkeypatch.setattr(dsn_client, "get_feed", mock_failing_feed)

    response = await async_client.get("/api/v1/dsn/now")
    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_dsn_client_get_spacecraft(dsn_xml_fixture):
    """DSN client extracts active dish tracking and signals for a specific spacecraft."""
    client = DSNNowClient(
        transport=MockTransport(lambda req: Response(200, text=dsn_xml_fixture))
    )
    try:
        # MRO is actively tracked in fixture on DSS26
        mro_status = await client.get_spacecraft("MRO")
        assert mro_status.spacecraft == "MRO"
        assert mro_status.is_actively_tracked is True
        assert len(mro_status.contacts) >= 1
        contact = mro_status.contacts[0]
        assert contact.dish_name == "DSS26"
        assert contact.station_friendly_name == "Goldstone"
        assert contact.target is not None
        assert contact.target.name == "MRO"
        assert contact.target.rtlt_seconds == 1320.0

        # Untracked spacecraft
        untracked = await client.get_spacecraft("VOYAGER_UNKNOWN")
        assert untracked.spacecraft == "VOYAGER_UNKNOWN"
        assert untracked.is_actively_tracked is False
        assert len(untracked.contacts) == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_api_dsn_status_alias(
    async_client: AsyncClient,
    dsn_xml_fixture,
    monkeypatch,
):
    """GET /api/v1/dsn/status is a valid alias returning 200 with feed status."""
    from backend.app.api.v1.dsn import dsn_client

    async def mock_feed(allow_stale=True):
        return parse_dsn_xml(dsn_xml_fixture, source_url="http://mock-dsn")

    monkeypatch.setattr(dsn_client, "get_feed", mock_feed)

    response = await async_client.get("/api/v1/dsn/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data["stations"]) == 3


@pytest.mark.asyncio
async def test_api_dsn_spacecraft_endpoint(
    async_client: AsyncClient,
    dsn_xml_fixture,
    monkeypatch,
):
    """GET /api/v1/dsn/spacecraft/{target} returns contacts for tracked spacecraft."""
    from backend.app.api.v1.dsn import dsn_client

    async def mock_get_sc(target, allow_stale=True):
        from backend.app.integrations.dsn.models import DSNSpacecraftTrackingResponse
        return DSNSpacecraftTrackingResponse(
            spacecraft=target.upper(),
            is_actively_tracked=True,
            contacts=[],
            source_url="http://mock-dsn",
        )

    monkeypatch.setattr(dsn_client, "get_spacecraft", mock_get_sc)

    response = await async_client.get("/api/v1/dsn/spacecraft/MRO")
    assert response.status_code == 200
    data = response.json()
    assert data["spacecraft"] == "MRO"
    assert data["is_actively_tracked"] is True


@pytest.mark.asyncio
async def test_dsn_client_spacecraft_signal_isolation(dsn_xml_fixture):
    """
    On a dish tracking multiple spacecraft (e.g. DSS26 tracking MRO and MEX),
    verifies that MEX (which has only a downSignal and no upSignal in the feed)
    is NOT falsely attributed MRO's upSignal.
    """
    client = DSNNowClient(
        transport=MockTransport(lambda req: Response(200, text=dsn_xml_fixture))
    )
    try:
        # Query MEX
        mex_status = await client.get_spacecraft("MEX")
        assert mex_status.spacecraft == "MEX"
        assert mex_status.is_actively_tracked is True
        assert len(mex_status.contacts) >= 1
        mex_contact = mex_status.contacts[0]
        assert mex_contact.dish_name == "DSS26"
        # MEX has NO uplink signal in feed
        assert len(mex_contact.up_signals) == 0, "MEX must not receive MRO's uplink signal!"
        # MEX has downlink signal with spacecraft="MEX"
        assert len(mex_contact.down_signals) == 1
        assert mex_contact.down_signals[0].spacecraft == "MEX"

        # Query MRO on the same dish
        mro_status = await client.get_spacecraft("MRO")
        assert mro_status.spacecraft == "MRO"
        mro_contact = mro_status.contacts[0]
        assert mro_contact.dish_name == "DSS26"
        # MRO has its own upSignal
        assert len(mro_contact.up_signals) == 1
        assert mro_contact.up_signals[0].spacecraft == "MRO"
        # MRO has its own downSignal (not MEX's)
        assert len(mro_contact.down_signals) == 1
        assert mro_contact.down_signals[0].spacecraft == "MRO"
    finally:
        await client.aclose()
