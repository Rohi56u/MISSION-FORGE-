"""
Unit and Integration Tests for JPL Horizons Adapter and API
Tests vector parsing, orbital elements, ambiguous targets, not found,
transient retries, caching, stale fallback, and FastAPI endpoints.
"""

import json
from pathlib import Path
import pytest
from httpx import AsyncClient, MockTransport, Response

from backend.app.core.cache import CacheStatus
from backend.app.integrations.horizons import (
    HorizonsAmbiguousTargetError,
    HorizonsClient,
    HorizonsEphemType,
    HorizonsQueryRequest,
    HorizonsTargetNotFoundError,
    HorizonsValidationError,
    parse_horizons_response,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def horizons_vector_fixture() -> dict:
    with open(FIXTURES_DIR / "horizons_vector_earth.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def horizons_elements_fixture() -> dict:
    with open(FIXTURES_DIR / "horizons_elements_earth.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def horizons_ambiguous_fixture() -> dict:
    with open(FIXTURES_DIR / "horizons_ambiguous_mars.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def horizons_not_found_fixture() -> dict:
    with open(FIXTURES_DIR / "horizons_not_found.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def horizons_missing_cmd_fixture() -> dict:
    with open(FIXTURES_DIR / "horizons_missing_command.json", encoding="utf-8") as f:
        return json.load(f)


# =========================================================================
# 1. PARSER DETERMINISTIC TESTS
# =========================================================================

def test_horizons_vector_parsing_earth(horizons_vector_fixture):
    """Parses real JPL Horizons Earth state vectors into normalized SI models."""
    req_params = {"target": "399", "center": "500@0", "ephem_type": "VECTORS"}
    resp = parse_horizons_response(
        horizons_vector_fixture,
        req_params,
        source_url="https://ssd.jpl.nasa.gov/api/horizons.api",
    )

    assert resp.target_id == "399"
    assert resp.target_name == "Earth (399)" or "Earth" in resp.target_name
    assert resp.ephem_type == HorizonsEphemType.VECTORS
    assert len(resp.vectors) == 2

    v0 = resp.vectors[0]
    assert v0.epoch_jd == 2461041.5
    assert "2026-Jan-01" in v0.calendar_date
    assert pytest.approx(v0.position_km.x, rel=1e-5) == -2.653100241556548e7
    assert pytest.approx(v0.position_km.y, rel=1e-5) == 1.439468995740296e8
    assert pytest.approx(v0.position_km.z, rel=1e-5) == 1.080681311843544e4
    assert pytest.approx(v0.velocity_kms.x, rel=1e-5) == -29.77650610770464
    assert pytest.approx(v0.velocity_kms.y, rel=1e-5) == -5.395962660572101
    assert pytest.approx(v0.velocity_kms.z, rel=1e-5) == 1.753836198843395e-4
    assert v0.light_time_s is not None
    assert v0.range_km is not None
    assert v0.range_rate_kms is not None


def test_horizons_elements_parsing_earth(horizons_elements_fixture):
    """Parses real JPL Horizons osculating Keplerian orbital elements."""
    req_params = {"target": "399", "center": "500@0", "ephem_type": "ELEMENTS"}
    resp = parse_horizons_response(
        horizons_elements_fixture,
        req_params,
        source_url="https://ssd.jpl.nasa.gov/api/horizons.api",
    )

    assert resp.ephem_type == HorizonsEphemType.ELEMENTS
    assert len(resp.elements) == 2

    e0 = resp.elements[0]
    assert e0.epoch_jd == 2461041.5
    assert pytest.approx(e0.eccentricity, rel=1e-5) == 0.009166999548581222
    assert pytest.approx(e0.periapsis_dist_km, rel=1e-5) == 1.462971607564066e8
    assert pytest.approx(e0.inclination_deg, rel=1e-5) == 0.004242269325986349
    assert pytest.approx(e0.longitude_asc_node_deg, rel=1e-5) == 14.76083602234425
    assert pytest.approx(e0.arg_perifocus_deg, rel=1e-5) == 66.43751678619198
    assert pytest.approx(e0.mean_anomaly_deg, rel=1e-5) == 18.90069218754828
    assert e0.semi_major_axis_km is not None
    assert e0.orbital_period_s is not None


def test_horizons_ambiguous_target_error(horizons_ambiguous_fixture):
    """Ambiguous target query parses candidate body IDs and raises HorizonsAmbiguousTargetError."""
    req_params = {"target": "Mars", "ephem_type": "VECTORS"}
    with pytest.raises(HorizonsAmbiguousTargetError) as exc_info:
        parse_horizons_response(
            horizons_ambiguous_fixture,
            req_params,
            source_url="https://ssd.jpl.nasa.gov/api/horizons.api",
        )
    err = exc_info.value
    assert len(err.candidates) >= 4
    candidate_ids = [c.target_id for c in err.candidates]
    assert "4" in candidate_ids
    assert "499" in candidate_ids
    assert "-3" in candidate_ids


def test_horizons_target_not_found(horizons_not_found_fixture):
    """Unmatched target body raises HorizonsTargetNotFoundError."""
    req_params = {"target": "INVALID_XYZ", "ephem_type": "VECTORS"}
    with pytest.raises(HorizonsTargetNotFoundError):
        parse_horizons_response(
            horizons_not_found_fixture,
            req_params,
            source_url="https://ssd.jpl.nasa.gov/api/horizons.api",
        )


def test_horizons_missing_command_validation_error(horizons_missing_cmd_fixture):
    """Upstream error response raises HorizonsValidationError."""
    with pytest.raises(HorizonsValidationError):
        parse_horizons_response(
            horizons_missing_cmd_fixture,
            {},
            source_url="https://ssd.jpl.nasa.gov/api/horizons.api",
        )


# =========================================================================
# 2. CLIENT CACHING, RETRIES, AND STALE FALLBACK
# =========================================================================

@pytest.mark.asyncio
async def test_horizons_client_caching_lifecycle(horizons_vector_fixture):
    """Client queries upstream once, then serves subsequent identical requests from cache."""
    call_count = 0

    def mock_handler(request):
        nonlocal call_count
        call_count += 1
        return Response(200, json=horizons_vector_fixture)

    transport = MockTransport(mock_handler)
    client = HorizonsClient(
        transport=transport,
        cache_ttl_seconds=300.0,
    )

    try:
        req = HorizonsQueryRequest(
            target="399",
            center="500@0",
            ephem_type=HorizonsEphemType.VECTORS,
            start_time="2026-01-01",
            stop_time="2026-01-02",
        )

        # 1. First call: cache miss -> LIVE
        res1 = await client.query(req)
        assert res1.cache_status == CacheStatus.LIVE
        assert call_count == 1
        assert len(res1.vectors) == 2

        # 2. Second call: cache hit -> CACHED
        res2 = await client.query(req)
        assert res2.cache_status == CacheStatus.CACHED
        assert call_count == 1  # transport was NOT invoked again!
        assert len(res2.vectors) == 2

    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_horizons_client_transient_retry_success(horizons_vector_fixture):
    """Client recovers from a transient 503 error on retry."""
    attempts = 0

    def mock_flaky_handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return Response(503, text="Service Temporarily Busy")
        return Response(200, json=horizons_vector_fixture)

    transport = MockTransport(mock_flaky_handler)
    client = HorizonsClient(
        transport=transport,
        max_retries=3,
    )

    try:
        req = HorizonsQueryRequest(target="399")
        res = await client.query(req)
        assert res.cache_status == CacheStatus.LIVE
        assert attempts == 2
        assert len(res.vectors) == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_horizons_client_stale_fallback_during_outage(horizons_vector_fixture):
    """When upstream is down, client serves previously cached data marked as STALE."""
    should_fail = False

    def mock_outage_handler(request):
        if should_fail:
            return Response(500, text="Internal Server Error")
        return Response(200, json=horizons_vector_fixture)

    transport = MockTransport(mock_outage_handler)
    client = HorizonsClient(
        transport=transport,
        cache_ttl_seconds=0.01,  # Expires rapidly
    )

    try:
        req = HorizonsQueryRequest(target="399")

        # 1. Seed cache
        res1 = await client.query(req)
        assert res1.cache_status == CacheStatus.LIVE

        # Invalidate TTL manually to simulate expired cache entry
        cache_key = client._generate_cache_key(req)
        entry = client.cache._store[cache_key]
        entry.expires_at = entry.created_at  # Now expired

        # 2. Trigger upstream outage
        should_fail = True

        # 3. Query should serve stale data with STALE label
        res2 = await client.query(req, allow_stale=True)
        assert res2.cache_status == CacheStatus.STALE
        assert len(res2.vectors) == 2

    finally:
        await client.aclose()


# =========================================================================
# 3. FASTAPI ROUTE INTEGRATION TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_api_horizons_post_query(
    async_client: AsyncClient,
    horizons_vector_fixture,
    monkeypatch,
):
    """POST /api/v1/horizons/query returns 200 with typed state vectors."""
    from backend.app.api.v1.horizons import horizons_client

    async def mock_query(req, allow_stale=True):
        return parse_horizons_response(
            horizons_vector_fixture,
            req.model_dump(),
            source_url="http://mock-horizons",
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(horizons_client, "query", mock_query)

    payload = {
        "target": "399",
        "center": "500@0",
        "ephem_type": "VECTORS",
        "start_time": "2026-01-01",
        "stop_time": "2026-01-02",
        "step_size": "1d",
    }
    response = await async_client.post("/api/v1/horizons/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["target_id"] == "399"
    assert len(data["vectors"]) == 2
    assert "position_km" in data["vectors"][0]
    assert "velocity_kms" in data["vectors"][0]
    assert data["cache_status"] == "LIVE"


@pytest.mark.asyncio
async def test_api_horizons_get_query(
    async_client: AsyncClient,
    horizons_vector_fixture,
    monkeypatch,
):
    """GET /api/v1/horizons/query returns 200 with query parameters."""
    from backend.app.api.v1.horizons import horizons_client

    async def mock_query(req, allow_stale=True):
        return parse_horizons_response(
            horizons_vector_fixture,
            req.model_dump(),
            source_url="http://mock-horizons",
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(horizons_client, "query", mock_query)

    response = await async_client.get(
        "/api/v1/horizons/query?target=399&ephem_type=VECTORS"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["vectors"]) == 2


@pytest.mark.asyncio
async def test_api_horizons_ambiguous_target_conflict(
    async_client: AsyncClient,
    horizons_ambiguous_fixture,
    monkeypatch,
):
    """Ambiguous target returns 409 Conflict with candidate suggestions."""
    from backend.app.api.v1.horizons import horizons_client

    async def mock_ambiguous_query(req, allow_stale=True):
        parse_horizons_response(
            horizons_ambiguous_fixture,
            req.model_dump(),
            source_url="http://mock-horizons",
        )

    monkeypatch.setattr(horizons_client, "query", mock_ambiguous_query)

    response = await async_client.post(
        "/api/v1/horizons/query",
        json={"target": "Mars"},
    )
    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert "candidates" in data["detail"]
    assert len(data["detail"]["candidates"]) > 0


@pytest.mark.asyncio
async def test_api_horizons_not_found(
    async_client: AsyncClient,
    horizons_not_found_fixture,
    monkeypatch,
):
    """Non-existent celestial target returns 404 Not Found."""
    from backend.app.api.v1.horizons import horizons_client

    async def mock_not_found_query(req, allow_stale=True):
        parse_horizons_response(
            horizons_not_found_fixture,
            req.model_dump(),
            source_url="http://mock-horizons",
        )

    monkeypatch.setattr(horizons_client, "query", mock_not_found_query)

    response = await async_client.post(
        "/api/v1/horizons/query",
        json={"target": "NON_EXISTENT_BODY_999"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_horizons_search_targets(
    async_client: AsyncClient,
    monkeypatch,
):
    """GET /api/v1/horizons/targets returns candidate matches."""
    from backend.app.api.v1.horizons import horizons_client
    from backend.app.integrations.horizons import HorizonsTargetCandidate

    async def mock_search(q):
        return [
            HorizonsTargetCandidate(target_id="4", name="Mars Barycenter"),
            HorizonsTargetCandidate(target_id="499", name="Mars"),
        ]

    monkeypatch.setattr(horizons_client, "search_targets", mock_search)

    response = await async_client.get("/api/v1/horizons/targets?query=Mars")
    assert response.status_code == 200
    candidates = response.json()
    assert len(candidates) == 2
    assert candidates[0]["target_id"] == "4"


def test_horizons_target_identifier_validation():
    """Target and center identifiers with quotes or injection characters are rejected."""
    # Semicolon injection
    with pytest.raises(ValueError):
        HorizonsQueryRequest(target="399; DROP TABLE components")

    # Single quotes
    with pytest.raises(ValueError):
        HorizonsQueryRequest(target="Mars'")

    # Control character
    with pytest.raises(ValueError):
        HorizonsQueryRequest(target="399\n500")

    # Center injection
    with pytest.raises(ValueError):
        HorizonsQueryRequest(target="399", center="500@0' OR 1=1")

    # Valid targets with spaces, hyphens, slashes, numbers, letters
    r1 = HorizonsQueryRequest(target="Mars Barycenter")
    assert r1.target == "Mars Barycenter"
    r2 = HorizonsQueryRequest(target="C/2013 A1")
    assert r2.target == "C/2013 A1"
    r3 = HorizonsQueryRequest(target="-53", center="500@0")
    assert r3.target == "-53"


def test_horizons_query_params_time_type():
    """Verifies that Horizons client includes TIME_TYPE in upstream query parameters."""
    client = HorizonsClient()

    # TDB default
    req_tdb = HorizonsQueryRequest(target="399")
    params_tdb = client._build_query_params(req_tdb)
    assert params_tdb["TIME_TYPE"] == "'TDB'"

    # UTC timescale
    from backend.app.integrations.horizons import HorizonsTimeScale
    req_utc = HorizonsQueryRequest(target="399", time_scale=HorizonsTimeScale.UTC)
    params_utc = client._build_query_params(req_utc)
    assert params_utc["TIME_TYPE"] == "'UT'"

    # Native UT timescale
    req_ut = HorizonsQueryRequest(target="399", time_scale=HorizonsTimeScale.UT)
    params_ut = client._build_query_params(req_ut)
    assert params_ut["TIME_TYPE"] == "'UT'"

    # CSV_FORMAT='NO' present for both VECTORS and ELEMENTS
    req_vectors = HorizonsQueryRequest(target="399", ephem_type=HorizonsEphemType.VECTORS)
    params_v = client._build_query_params(req_vectors)
    assert params_v["CSV_FORMAT"] == "'NO'"
    assert params_v["VEC_TABLE"] == "'3'"

    req_elements = HorizonsQueryRequest(target="399", ephem_type=HorizonsEphemType.ELEMENTS)
    params_e = client._build_query_params(req_elements)
    assert params_e["CSV_FORMAT"] == "'NO'"
    assert "VEC_TABLE" not in params_e


def test_horizons_elements_hyperbolic_orbit_parsing():
    """Parses hyperbolic orbital elements where apoapsis distance (AD) is not applicable."""
    sample_hyperbolic = {
        "signature": {"version": "1.2", "source": "NASA/JPL Horizons API"},
        "result": """*******************************************************************************
Target body name: 'Oumuamua (A/2017 U1)          {source: JPL#16}
Center body name: Sun (10)                        {source: DE441}
*******************************************************************************
$$SOE
2458000.500000000 = A.D. 2017-Sep-04 00:00:00.0000 TDB
 EC= 1.200000000000000E+00 QR= 3.810000000000000E+07 IN= 1.220000000000000E+02
 OM= 2.460000000000000E+01 W = 2.410000000000000E+02 Tp=  2458005.100000000000
 N = 1.000000000000000E-04 MA=-5.000000000000000E+01 TA=-6.000000000000000E+01
 A =-1.905000000000000E+08 PR= 1.000000000000000E+99
$$EOE
*******************************************************************************
""",
    }
    resp = parse_horizons_response(
        sample_hyperbolic,
        {"target": "A/2017 U1", "ephem_type": "ELEMENTS"},
        source_url="http://test",
    )
    assert len(resp.elements) == 1
    elem = resp.elements[0]
    assert elem.eccentricity == 1.2
    assert elem.semi_major_axis_km == -1.905e8
    assert elem.apoapsis_dist_km is None  # Resiliently parsed as None without failing


@pytest.mark.asyncio
async def test_api_horizons_vectors_endpoint(
    async_client: AsyncClient,
    horizons_vector_fixture,
    monkeypatch,
):
    """GET /api/v1/horizons/vectors returns 200 with state vectors."""
    from backend.app.api.v1.horizons import horizons_client

    async def mock_query(req, allow_stale=True):
        return parse_horizons_response(
            horizons_vector_fixture,
            req.model_dump(),
            source_url="http://mock-horizons",
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(horizons_client, "query", mock_query)

    response = await async_client.get("/api/v1/horizons/vectors?target=399")
    assert response.status_code == 200
    data = response.json()
    assert data["ephem_type"] == "VECTORS"
    assert len(data["vectors"]) == 2


@pytest.mark.asyncio
async def test_api_horizons_elements_endpoint(
    async_client: AsyncClient,
    horizons_elements_fixture,
    monkeypatch,
):
    """GET /api/v1/horizons/elements returns 200 with orbital elements."""
    from backend.app.api.v1.horizons import horizons_client

    async def mock_query(req, allow_stale=True):
        return parse_horizons_response(
            horizons_elements_fixture,
            req.model_dump(),
            source_url="http://mock-horizons",
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(horizons_client, "query", mock_query)

    response = await async_client.get("/api/v1/horizons/elements?target=399")
    assert response.status_code == 200
    data = response.json()
    assert data["ephem_type"] == "ELEMENTS"
    assert len(data["elements"]) == 2


def test_horizons_query_injection_sanitization():
    """Validates that time, step, and identifier parameters reject injection characters."""
    from pydantic import ValidationError

    # Unsafe start_time with quote injection
    with pytest.raises(ValidationError):
        HorizonsQueryRequest(target="399", start_time="2026-01-01' ; INJECT")

    # Unsafe step_size with semicolon injection
    with pytest.raises(ValidationError):
        HorizonsQueryRequest(target="399", step_size="1d; COMMAND='DROP'")

    # Unsafe target with injection
    with pytest.raises(ValidationError):
        HorizonsQueryRequest(target="399; 'DROP'")

    # Unsupported ephemeris type OBSERVER
    with pytest.raises(ValidationError):
        HorizonsQueryRequest(target="399", ephem_type="OBSERVER")


def test_horizons_timescale_units_parity(horizons_vector_fixture):
    """
    Verifies that querying with UT timescale returns resp.time_scale == 'UT'
    (not 'HorizonsTimeScale.UT') and dynamic units['time'] reflect UT.
    """
    from backend.app.integrations.horizons import HorizonsTimeScale

    req = HorizonsQueryRequest(target="399", time_scale=HorizonsTimeScale.UT)
    resp = parse_horizons_response(
        horizons_vector_fixture,
        req.model_dump(),
        source_url="http://test",
    )
    assert resp.time_scale == "UT"
    assert "UT" in resp.units["time"]
    assert "TDB" not in resp.units["time"]
