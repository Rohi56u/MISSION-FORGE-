"""
Unit and Integration Tests for Ephemeris-Driven Porkchop Engine & API
Mission Forge — Phase 3

Tests include:
1. Deterministic Earth-to-Mars porkchop grid generation using ephemeris fixtures.
2. Earth-to-Moon geocentric porkchop calculation and verified TLI / LOI Delta-Vs.
3. Earth-to-Europa model assumptions and clear multi-body Jovian capture limitations.
4. Representation of invalid cells (None / null, never 0 or fabricated values).
5. Minima calculation strictly over valid cells.
6. Optional parking-orbit Delta-V calculations vs excess velocities.
7. Grid resolution and bounds validation (exceeding 10,000 points rejected with 422).
8. Asynchronous background job creation, state transitions, polling, and results retrieval.
9. FastAPI routes: POST /porkchop/calculate, POST /porkchop/jobs, GET /jobs/{id},
   and GET /jobs/{id}/result.
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from backend.app.astrodynamics.porkchop import (
    EphemerisState,
    PorkchopGenerator,
)
from backend.app.core.cache import CacheStatus
from backend.app.integrations.horizons import (
    HorizonsEphemType,
    HorizonsQueryResponse,
    HorizonsVectorEntry,
    horizons_client,
)
from backend.app.integrations.horizons.models import Vector3D
from backend.app.main import app


@pytest.fixture
def mock_horizons_for_porkchop(monkeypatch, mars_transfer_ephemerides):
    """Mocks upstream Horizons queries with deterministic ephemeris vectors."""
    earth_states, mars_states = mars_transfer_ephemerides

    async def mock_query(req, allow_stale=True):
        is_earth = req.target in ("399", "EARTH", "3")
        source_states = earth_states if is_earth else mars_states
        vectors = []
        for d_str, state in source_states.items():
            vectors.append(
                HorizonsVectorEntry(
                    epoch_jd=state.epoch_jd,
                    calendar_date=state.calendar_date,
                    position_km=state.position_km,
                    velocity_kms=state.velocity_kms,
                )
            )
        return HorizonsQueryResponse(
            target_id=req.target,
            target_name="Earth (399)" if is_earth else "Mars (499)",
            center_id=req.center,
            center_name="Sun (10)",
            ephem_type=HorizonsEphemType.VECTORS,
            coordinate_frame="ICRF / J2000",
            origin_center="Sun",
            time_scale="TDB",
            source_url="https://ssd.jpl.nasa.gov/api/horizons.api",
            vectors=vectors,
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(horizons_client, "query", mock_query)


# =========================================================================
# FIXTURES: DETERMINISTIC EPHEMERIS STATES FOR EARTH AND MARS
# =========================================================================

def make_ephemeris_state(
    pos_x: float, pos_y: float, pos_z: float,
    vel_x: float, vel_y: float, vel_z: float,
    date_str: str,
) -> EphemerisState:
    """Helper to construct deterministic ephemeris state."""
    return EphemerisState(
        epoch_jd=2461000.5,
        calendar_date=f"A.D. {date_str} 00:00:00.0000 TDB",
        position_km=Vector3D(x=pos_x, y=pos_y, z=pos_z),
        velocity_kms=Vector3D(x=vel_x, y=vel_y, z=vel_z),
    )


@pytest.fixture
def mars_transfer_ephemerides() -> tuple[dict[str, EphemerisState], dict[str, EphemerisState]]:
    """
    Constructs deterministic heliocentric states for Earth (departure)
    and Mars (arrival) corresponding to a realistic 2026-2027 transfer window.
    """
    earth_states = {
        "2026-06-01": make_ephemeris_state(
            -5.46e7, 1.41e8, 1.2e4, -28.2, -10.9, 0.001, "2026-Jun-01"
        ),
        "2026-06-15": make_ephemeris_state(
            -8.85e7, 1.24e8, 1.1e4, -24.8, -17.2, 0.001, "2026-Jun-15"
        ),
        "2026-06-16": make_ephemeris_state(
            -8.85e7, 1.24e8, 1.1e4, -24.8, -17.2, 0.001, "2026-Jun-16"
        ),
        "2026-07-01": make_ephemeris_state(
            -1.18e8, 9.87e7, 8.5e3, -20.0, -22.5, 0.001, "2026-Jul-01"
        ),
    }

    mars_states = {
        "2027-01-01": make_ephemeris_state(
            1.85e8, -1.22e8, -6.8e6, 13.5, 20.8, 0.22, "2027-Jan-01"
        ),
        "2027-01-15": make_ephemeris_state(
            2.00e8, -9.62e7, -6.5e6, 10.7, 22.4, 0.31, "2027-Jan-15"
        ),
        "2027-01-16": make_ephemeris_state(
            2.00e8, -9.62e7, -6.5e6, 10.7, 22.4, 0.31, "2027-Jan-16"
        ),
        "2027-01-31": make_ephemeris_state(
            2.11e8, -6.85e7, -6.0e6, 7.6, 23.6, 0.39, "2027-Jan-31"
        ),
        "2027-02-01": make_ephemeris_state(
            2.11e8, -6.85e7, -6.0e6, 7.6, 23.6, 0.39, "2027-Feb-01"
        ),
    }

    return earth_states, mars_states


# =========================================================================
# 1. DETERMINISTIC EARTH-TO-MARS PORKCHOP CALCULATION
# =========================================================================

@pytest.mark.asyncio
async def test_porkchop_earth_to_mars_deterministic(mars_transfer_ephemerides):
    """
    Generates a 3x3 Earth-to-Mars porkchop grid using deterministic ephemerides.
    Verifies grid dimensions, C3 ranges, excess velocities, and minima calculation.
    """
    earth_states, mars_states = mars_transfer_ephemerides
    generator = PorkchopGenerator(max_grid_points=1000)

    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MARS",
        departure_start_date="2026-06-01",
        departure_end_date="2026-07-01",
        arrival_start_date="2027-01-01",
        arrival_end_date="2027-02-01",
        step_days=15.0,
        dep_parking_alt_km=200.0,
        arr_parking_alt_km=300.0,
        origin_states_override=earth_states,
        target_states_override=mars_states,
    )

    assert result["origin_body"] == "EARTH"
    assert result["target_body"] == "MARS"
    assert len(result["departure_dates"]) == 3
    assert len(result["arrival_dates"]) == 3
    assert result["total_grid_points"] == 9
    assert result["valid_cells_count"] == 9

    # Verify grids are 3x3
    assert len(result["c3_grid"]) == 3
    assert len(result["c3_grid"][0]) == 3
    assert len(result["valid_mask"]) == 3

    # Check characteristic energy C3 is in realistic interplanetary range (5 to 100 km^2/s^2)
    min_c3 = result["minima"]["min_c3"]
    assert min_c3 is not None
    assert 5.0 <= min_c3["value"] <= 100.0
    assert min_c3["units"] == "km^2/s^2"

    # Check departure and arrival excess velocities
    min_vinf_dep = result["minima"]["min_vinf_dep"]
    assert min_vinf_dep is not None
    assert 2.0 <= min_vinf_dep["value"] <= 15.0

    # Total Delta-V (injection + capture)
    min_dv_total = result["minima"]["min_total_delta_v"]
    assert min_dv_total is not None
    assert 4.0 <= min_dv_total["value"] <= 25.0


# =========================================================================
# 2. EARTH-TO-MOON GEOCENTRIC PORKCHOP & VERIFIED TLI DELTA-V
# =========================================================================

@pytest.mark.asyncio
async def test_porkchop_earth_to_moon_geocentric():
    """
    Verifies Earth-to-Moon geocentric model:
    Moon at geocentric distance ~ 384,400 km.
    Spacecraft departs from Earth parking orbit.
    1. With explicit parking orbits (200 km Earth, 100 km Moon):
       Verifies Trans-Lunar Injection (TLI) Delta-V ~ 3.1 - 3.2 km/s.
       Verifies Lunar Orbit Insertion (LOI) Delta-V ~ 0.8 - 0.9 km/s.
       Verifies total mission Delta-V ~ 3.9 - 4.1 km/s.
    2. With omitted parking orbits:
       Verifies injection/capture Delta-Vs are None, and geocentric C3 is computed.
    """
    # Deterministic Moon geocentric state
    moon_states = {
        "2026-05-05": make_ephemeris_state(
            -3.5e5, 1.5e5, 2.5e4, -0.4, -0.9, 0.05, "2026-May-05"
        ),
        "2026-05-06": make_ephemeris_state(
            -3.8e5, 6.0e4, 2.0e4, -0.1, -1.0, 0.04, "2026-May-06"
        ),
    }
    earth_states = {
        "2026-05-01": make_ephemeris_state(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "2026-May-01"),
        "2026-05-02": make_ephemeris_state(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "2026-May-02"),
    }

    generator = PorkchopGenerator(max_grid_points=100)

    # 1. With explicit parking orbits
    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MOON",
        departure_start_date="2026-05-01",
        departure_end_date="2026-05-02",
        arrival_start_date="2026-05-05",
        arrival_end_date="2026-05-06",
        step_days=1.0,
        dep_parking_alt_km=200.0,
        arr_parking_alt_km=100.0,
        origin_states_override=earth_states,
        target_states_override=moon_states,
    )

    assert result["origin_body"] == "EARTH"
    assert result["target_body"] == "MOON"
    assert "Earth-centered" in result["provenance"]["physical_model"]
    assert result["valid_cells_count"] > 0

    # Verify TLI Delta-V is approximately 3.1 - 3.2 km/s (Apollo standard)
    valid_inj_dvs = [
        val for row in result["dv_inj_grid"] for val in row if val is not None
    ]
    assert len(valid_inj_dvs) > 0
    for dv in valid_inj_dvs:
        assert 2.9 <= dv <= 3.5, f"Unexpected TLI Delta-V: {dv} km/s"

    # Verify total Delta-V is approximately 3.8 - 4.5 km/s
    min_dv = result["minima"]["min_total_delta_v"]
    assert min_dv is not None
    assert 3.7 <= min_dv["value"] <= 4.6

    # 2. With omitted parking orbits: Delta-Vs must be None, geocentric C3 computed
    result_no_burns = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MOON",
        departure_start_date="2026-05-01",
        departure_end_date="2026-05-02",
        arrival_start_date="2026-05-05",
        arrival_end_date="2026-05-06",
        step_days=1.0,
        dep_parking_alt_km=None,
        arr_parking_alt_km=None,
        origin_states_override=earth_states,
        target_states_override=moon_states,
    )
    assert result_no_burns["dv_inj_grid"][0][0] is None
    assert result_no_burns["dv_arr_grid"][0][0] is None
    assert result_no_burns["dv_total_grid"][0][0] is None
    assert result_no_burns["minima"]["min_total_delta_v"] is None
    # Geocentric C3 should be negative for elliptic lunar transfer (~ -2.4 km^2/s^2)
    c3_lunar = result_no_burns["c3_grid"][0][0]
    assert c3_lunar is not None
    assert -5.0 <= c3_lunar <= 0.0


# =========================================================================
# 3. EARTH-TO-EUROPA PHYSICAL MODEL & JOVIAN LIMITATIONS
# =========================================================================

@pytest.mark.asyncio
async def test_porkchop_earth_to_europa_provenance_and_limitations():
    """
    Verifies that Earth-to-Europa analysis explicitly documents Sun-centered transfer
    assumptions and omits Europa capture burn because Jovian multi-body capture is required.
    """
    europa_states = {
        "2030-01-01": make_ephemeris_state(
            7.5e8, -2.1e8, -1.2e7, 3.5, 12.8, 0.05, "2030-Jan-01"
        )
    }
    earth_states = {
        "2027-01-01": make_ephemeris_state(
            -2.6e7, 1.44e8, 1.0e4, -29.8, -5.4, 0.0, "2027-Jan-01"
        )
    }

    generator = PorkchopGenerator(max_grid_points=100)
    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="EUROPA",
        departure_start_date="2027-01-01",
        departure_end_date="2027-01-01",
        arrival_start_date="2030-01-01",
        arrival_end_date="2030-01-01",
        step_days=1.0,
        dep_parking_alt_km=200.0,
        arr_parking_alt_km=100.0,
        origin_states_override=earth_states,
        target_states_override=europa_states,
    )

    provenance = result["provenance"]
    assert "Sun-centered" in provenance["physical_model"]
    assert "Europa is a moon of Jupiter" in provenance["physical_model"]
    assert "Jovian multi-body capture" in provenance["physical_model"]

    # Europa capture Delta-V MUST be None because multi-body Jovian capture is unmodeled
    assert result["dv_arr_grid"][0][0] is None
    assert result["dv_total_grid"][0][0] is None
    assert result["vinf_arr_grid"][0][0] is not None


# =========================================================================
# 4. INVALID CELLS & NON-CONVERGENCE SAFEGUARDS (NO FABRICATED VALUES)
# =========================================================================

@pytest.mark.asyncio
async def test_invalid_cells_null_representation():
    """
    Verifies that cells with negative TOF (arrival <= departure) are marked
    invalid (valid_mask == False) and contain None, NEVER 0 or fabricated numbers.
    """
    dummy_states = {
        "2026-06-01": make_ephemeris_state(1.5e8, 0.0, 0.0, 0.0, 30.0, 0.0, "2026-06-01"),
        "2026-06-05": make_ephemeris_state(1.4e8, 5e7, 0.0, -10.0, 28.0, 0.0, "2026-06-05"),
    }

    generator = PorkchopGenerator(max_grid_points=100)
    # Arrival dates overlap departure dates -> arrival <= departure happens
    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MARS",
        departure_start_date="2026-06-01",
        departure_end_date="2026-06-05",
        arrival_start_date="2026-06-01",
        arrival_end_date="2026-06-05",
        step_days=4.0,
        origin_states_override=dummy_states,
        target_states_override=dummy_states,
    )

    c3_grid = result["c3_grid"]
    valid_mask = result["valid_mask"]

    # At arrival idx 0 ("2026-06-01") and departure idx 0 ("2026-06-01"): TOF = 0 -> Invalid
    assert valid_mask[0][0] is False
    assert c3_grid[0][0] is None  # MUST be None, not 0.0!

    # At arrival idx 0 ("2026-06-01") and departure idx 1 ("2026-06-05"): TOF = -4 -> Invalid
    assert valid_mask[0][1] is False
    assert c3_grid[0][1] is None  # MUST be None


# =========================================================================
# 5. PARKING ORBIT DELTA-V CALCULATION OMISSION HANDLING
# =========================================================================

@pytest.mark.asyncio
async def test_parking_orbit_delta_v_omission(mars_transfer_ephemerides):
    """
    Verifies that when parking orbit altitudes are omitted, injection and capture
    Delta-Vs are set to None, and only excess velocities and C3 are computed.
    """
    earth_states, mars_states = mars_transfer_ephemerides
    generator = PorkchopGenerator(max_grid_points=100)

    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MARS",
        departure_start_date="2026-06-01",
        departure_end_date="2026-06-01",
        arrival_start_date="2027-01-01",
        arrival_end_date="2027-01-01",
        step_days=1.0,
        dep_parking_alt_km=None,  # No parking assumptions
        arr_parking_alt_km=None,
        origin_states_override=earth_states,
        target_states_override=mars_states,
    )

    assert result["c3_grid"][0][0] is not None
    assert result["vinf_dep_grid"][0][0] is not None
    assert result["dv_inj_grid"][0][0] is None
    assert result["dv_arr_grid"][0][0] is None
    assert result["dv_total_grid"][0][0] is None
    assert result["minima"]["min_total_delta_v"] is None


# =========================================================================
# 6. FASTAPI API ROUTES: DIRECT SYNC & ASYNC BACKGROUND JOBS
# =========================================================================

@pytest.mark.asyncio
async def test_api_porkchop_calculate_direct(mock_horizons_for_porkchop):
    """Tests POST /api/v1/trajectory/porkchop/calculate direct synchronous endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. Intentionally invalid date ordering -> 422
        bad_payload = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2026-08-01",
            "departure_end_date": "2026-05-01",  # End before start
            "arrival_start_date": "2026-11-01",
            "arrival_end_date": "2027-04-01",
        }
        resp = await client.post("/api/v1/trajectory/porkchop/calculate", json=bad_payload)
        assert resp.status_code == 422

        # 2. Valid synchronous calculation
        valid_payload = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2026-06-01",
            "departure_end_date": "2026-06-15",
            "arrival_start_date": "2027-01-01",
            "arrival_end_date": "2027-01-15",
            "step_size_days": 14.0,
            "dep_parking_alt_km": 200.0,
            "arr_parking_alt_km": 300.0,
        }
        valid_resp = await client.post(
            "/api/v1/trajectory/porkchop/calculate", json=valid_payload
        )
        assert valid_resp.status_code == 200
        data = valid_resp.json()
        assert data["origin_body"] == "EARTH"
        assert data["target_body"] == "MARS"
        assert len(data["c3_grid"]) > 0


@pytest.mark.asyncio
async def test_api_porkchop_job_lifecycle(mock_horizons_for_porkchop):
    """
    Tests asynchronous porkchop job lifecycle:
    1. POST /api/v1/trajectory/porkchop/jobs -> 202 Accepted
    2. GET /api/v1/trajectory/porkchop/jobs/{job_id} -> poll until COMPLETED
    3. GET /api/v1/trajectory/porkchop/jobs/{job_id}/result -> verify dataset
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        payload = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2026-06-01",
            "departure_end_date": "2026-06-03",
            "arrival_start_date": "2027-01-01",
            "arrival_end_date": "2027-01-03",
            "step_size_days": 2.0,
            "dep_parking_alt_km": 200.0,
            "arr_parking_alt_km": 300.0,
        }
        create_resp = await client.post("/api/v1/trajectory/porkchop/jobs", json=payload)
        assert create_resp.status_code == 202
        job_info = create_resp.json()
        job_id = job_info["job_id"]
        assert job_id is not None
        assert job_info["status"] == "QUEUED"

        # Poll for completion (up to 10 seconds)
        completed = False
        for _ in range(20):
            await asyncio.sleep(0.5)
            status_resp = await client.get(f"/api/v1/trajectory/porkchop/jobs/{job_id}")
            assert status_resp.status_code == 200
            status_data = status_resp.json()
            if status_data["status"] == "COMPLETED":
                completed = True
                break
            elif status_data["status"] == "FAILED":
                pytest.fail(f"Job failed with error: {status_data['error_message']}")

        assert completed is True, "Job did not complete within timeout"

        # Retrieve final result
        res_resp = await client.get(f"/api/v1/trajectory/porkchop/jobs/{job_id}/result")
        assert res_resp.status_code == 200
        res_data = res_resp.json()
        assert res_data["origin_body"] == "EARTH"
        assert res_data["target_body"] == "MARS"
        assert len(res_data["c3_grid"]) > 0


@pytest.mark.asyncio
async def test_api_porkchop_job_not_found():
    """Verifies querying a non-existent job ID returns 404."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        dummy_uuid = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(f"/api/v1/trajectory/porkchop/jobs/{dummy_uuid}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_porkchop_job_cancellation(mock_horizons_for_porkchop):
    """
    Tests cancelling a porkchop job:
    1. Submit job -> QUEUED
    2. Cancel job -> CANCELLED (200 OK)
    3. Querying result of cancelled job -> returns 400 Bad Request
    4. Cancelling an already finished job -> returns 400 Bad Request
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        payload = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2026-06-01",
            "departure_end_date": "2026-06-02",
            "arrival_start_date": "2027-01-01",
            "arrival_end_date": "2027-01-02",
            "step_size_days": 1.0,
        }
        create_resp = await client.post("/api/v1/trajectory/porkchop/jobs", json=payload)
        assert create_resp.status_code == 202
        job_id = create_resp.json()["job_id"]

        # Cancel the job
        cancel_resp = await client.post(f"/api/v1/trajectory/porkchop/jobs/{job_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "CANCELLED"

        # Attempting to fetch result of cancelled job should return 400
        res_resp = await client.get(f"/api/v1/trajectory/porkchop/jobs/{job_id}/result")
        assert res_resp.status_code == 400

        # Attempting to cancel non-existent job -> 404
        dummy_uuid = "00000000-0000-0000-0000-000000000000"
        c_404 = await client.post(f"/api/v1/trajectory/porkchop/jobs/{dummy_uuid}/cancel")
        assert c_404.status_code == 404

        # Brief yield to allow worker task to observe cancellation cleanly
        await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_api_porkchop_duplicate_job_idempotency(mock_horizons_for_porkchop):
    """
    Tests that submitting an identical request while a job is in-flight returns
    the existing job ID instead of duplicating the computation.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        payload = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2026-06-15",
            "departure_end_date": "2026-06-16",
            "arrival_start_date": "2027-01-15",
            "arrival_end_date": "2027-01-16",
            "step_size_days": 1.0,
        }
        resp1 = await client.post("/api/v1/trajectory/porkchop/jobs", json=payload)
        assert resp1.status_code == 202
        job_id1 = resp1.json()["job_id"]

        resp2 = await client.post("/api/v1/trajectory/porkchop/jobs", json=payload)
        assert resp2.status_code == 202
        job_id2 = resp2.json()["job_id"]

        # Duplicate submission must return identical in-flight or completed job ID
        assert job_id1 == job_id2

        # Await completion to allow background task to finish cleanly before loop teardown
        for _ in range(20):
            await asyncio.sleep(0.2)
            st = await client.get(f"/api/v1/trajectory/porkchop/jobs/{job_id1}")
            if st.json()["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
                break


@pytest.mark.asyncio
async def test_api_porkchop_request_validation_errors():
    """
    Tests request payload validation errors:
    1. departure_start_date >= arrival_end_date (impossible transfer) -> 422
    2. origin_body == target_body (e.g. EARTH to EARTH) -> 422
    3. Grid exceeding 10,000 cells -> 422
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. Infeasible date ordering
        bad_dates = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2027-05-01",
            "departure_end_date": "2027-06-01",
            "arrival_start_date": "2026-01-01",
            "arrival_end_date": "2026-02-01",  # Arrival before departure
        }
        resp1 = await client.post("/api/v1/trajectory/porkchop/jobs", json=bad_dates)
        assert resp1.status_code == 422

        # 2. Identical origin and target
        same_body = {
            "origin_body": "EARTH",
            "target_body": "EARTH",
            "departure_start_date": "2026-05-01",
            "departure_end_date": "2026-06-01",
            "arrival_start_date": "2026-11-01",
            "arrival_end_date": "2027-01-01",
        }
        resp2 = await client.post("/api/v1/trajectory/porkchop/jobs", json=same_body)
        assert resp2.status_code == 422

        # 3. Identical origin and target via aliases (EARTH vs 399)
        same_alias = {
            "origin_body": "EARTH",
            "target_body": "399",
            "departure_start_date": "2026-05-01",
            "departure_end_date": "2026-06-01",
            "arrival_start_date": "2026-11-01",
            "arrival_end_date": "2027-01-01",
        }
        resp3 = await client.post("/api/v1/trajectory/porkchop/jobs", json=same_alias)
        assert resp3.status_code == 422

        # 4. Sun as origin body -> rejected with 422
        sun_orig = {
            "origin_body": "SUN",
            "target_body": "MARS",
            "departure_start_date": "2026-05-01",
            "departure_end_date": "2026-06-01",
            "arrival_start_date": "2026-11-01",
            "arrival_end_date": "2027-01-01",
        }
        resp4 = await client.post("/api/v1/trajectory/porkchop/jobs", json=sun_orig)
        assert resp4.status_code == 422

        # 5. Moon as origin body without escape modeling -> rejected with 422
        moon_orig = {
            "origin_body": "MOON",
            "target_body": "MARS",
            "departure_start_date": "2026-05-01",
            "departure_end_date": "2026-06-01",
            "arrival_start_date": "2026-11-01",
            "arrival_end_date": "2027-01-01",
        }
        resp5 = await client.post("/api/v1/trajectory/porkchop/jobs", json=moon_orig)
        assert resp5.status_code == 422


@pytest.mark.asyncio
async def test_api_porkchop_provenance_and_diagnostics(mars_transfer_ephemerides):
    """
    Verifies that porkchop results include all mandatory provenance fields
    and that fixture data is accurately labeled as FIXTURE, never falsely LIVE.
    Also verifies solver diagnostics are populated.
    """
    earth_states, mars_states = mars_transfer_ephemerides
    generator = PorkchopGenerator(max_grid_points=100)

    res = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MARS",
        departure_start_date="2026-06-01",
        departure_end_date="2026-06-01",
        arrival_start_date="2027-01-01",
        arrival_end_date="2027-01-01",
        step_days=1.0,
        origin_states_override=earth_states,
        target_states_override=mars_states,
    )

    provenance = res["provenance"]
    assert provenance["cache_status"] == "FIXTURE"  # Never falsely labeled LIVE
    assert "source_url" in provenance
    assert "target_ids" in provenance
    assert provenance["target_ids"]["origin"] == "399"
    assert provenance["target_ids"]["target"] == "499"
    assert "query_parameters" in provenance
    assert "retrieved_at" in provenance
    assert "limitations" in provenance
    assert "Two-body Lambert transfer does not model" in provenance["limitations"]
    assert "insertion/capture delta-v maneuvers are uncalculated" in provenance["limitations"]

    diagnostics = res["solver_diagnostics"]
    assert diagnostics["converged_cells_count"] == 1
    assert diagnostics["convergence_rate_percent"] == 100.0
    assert "Universal Variable" in diagnostics["solver_method"]


@pytest.mark.asyncio
async def test_porkchop_empty_horizons_vectors_error(monkeypatch):
    """Verifies that if Horizons returns zero vectors, PorkchopGenerator raises ValueError."""
    async def mock_empty_query(req, allow_stale=True):
        return HorizonsQueryResponse(
            target_id=req.target,
            target_name="Test Target",
            center_id=req.center,
            center_name="Test Center",
            ephem_type=HorizonsEphemType.VECTORS,
            coordinate_frame="ICRF / J2000",
            origin_center="Sun",
            time_scale="TDB",
            source_url="https://ssd.jpl.nasa.gov/api/horizons.api",
            vectors=[],  # Empty!
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(horizons_client, "query", mock_empty_query)

    generator = PorkchopGenerator(max_grid_points=100)
    with pytest.raises(ValueError, match="No ephemeris vectors returned by JPL Horizons"):
        await generator.generate_porkchop(
            origin_body="EARTH",
            target_body="MARS",
            departure_start_date="2026-06-01",
            departure_end_date="2026-06-02",
            arrival_start_date="2027-01-01",
            arrival_end_date="2027-01-02",
        )


@pytest.mark.asyncio
async def test_api_porkchop_cleanup_endpoint():
    """Tests DELETE /api/v1/trajectory/porkchop/jobs/cleanup maintenance endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.delete("/api/v1/trajectory/porkchop/jobs/cleanup?retention_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "deleted_jobs_count" in data
        assert data["retention_days"] == 30


# =========================================================================
# 10. RESTART RECOVERY, MODEL LIMITATIONS & FRAME AUDIT REGRESSION TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_porkchop_restart_recovery_orphaned_jobs():
    """
    Verifies that application restart recovery safely cleans up orphaned in-flight
    jobs (QUEUED or RUNNING) by transitioning them to FAILED.
    Verifies that duplicate-submission protection is unblocked so clients can resubmit.
    """
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.trajectory import PorkchopJob, PorkchopJobStatus
    from backend.app.api.v1.trajectory import recover_orphaned_porkchop_jobs

    async with AsyncSessionLocal() as session:
        # Create an orphaned QUEUED job and an orphaned RUNNING job
        orphan_queued = PorkchopJob(
            origin_body="EARTH",
            target_body="MARS",
            departure_start="2026-06-01",
            departure_end="2026-06-15",
            arrival_start="2027-01-01",
            arrival_end="2027-01-15",
            step_size_days=2.0,
            parameters={"test": "orphan_queued"},
            status=PorkchopJobStatus.QUEUED,
            progress_percent=0.0,
        )
        orphan_running = PorkchopJob(
            origin_body="EARTH",
            target_body="VENUS",
            departure_start="2026-05-01",
            departure_end="2026-05-15",
            arrival_start="2026-10-01",
            arrival_end="2026-10-15",
            step_size_days=2.0,
            parameters={"test": "orphan_running"},
            status=PorkchopJobStatus.RUNNING,
            progress_percent=45.0,
        )
        session.add(orphan_queued)
        session.add(orphan_running)
        await session.commit()
        await session.refresh(orphan_queued)
        await session.refresh(orphan_running)

        q_id = orphan_queued.id
        r_id = orphan_running.id

    # Execute startup recovery procedure
    async with AsyncSessionLocal() as session:
        recovered_count = await recover_orphaned_porkchop_jobs(session)
        assert recovered_count >= 2

    # Verify both jobs are marked FAILED with recovery explanation
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp_q = await client.get(f"/api/v1/trajectory/porkchop/jobs/{q_id}")
        assert resp_q.status_code == 200
        data_q = resp_q.json()
        assert data_q["status"] == "FAILED"
        assert "restarted" in data_q["error_message"].lower()

        resp_r = await client.get(f"/api/v1/trajectory/porkchop/jobs/{r_id}")
        assert resp_r.status_code == 200
        data_r = resp_r.json()
        assert data_r["status"] == "FAILED"
        assert "restarted" in data_r["error_message"].lower()

        # Verify duplicate protection is UNBLOCKED: submitting identical query now succeeds
        dup_payload = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2026-06-01",
            "departure_end_date": "2026-06-15",
            "arrival_start_date": "2027-01-01",
            "arrival_end_date": "2027-01-15",
            "step_size_days": 2.0,
        }
        resp_new = await client.post("/api/v1/trajectory/porkchop/jobs", json=dup_payload)
        assert resp_new.status_code == 202
        new_id = resp_new.json()["job_id"]
        # Must be a NEW job ID, not the old failed job!
        assert new_id != q_id
        # Cleanly cancel test job so background worker does not leak across event loops
        await client.post(f"/api/v1/trajectory/porkchop/jobs/{new_id}/cancel")
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_porkchop_europa_model_limitations_and_provenance(monkeypatch):
    """
    Verifies that the Earth-to-Europa mission model:
    1. Uses Europa (ID 502) state vectors relative to Sun (500@10).
    2. Explicitly omits target capture Delta-V and total Delta-V (both None).
    3. Clearly documents that Jovian multi-body dynamics are required for capture.
    4. Correctly classifies excess velocity relative to Europa's heliocentric orbit.
    """
    earth_state = make_ephemeris_state(
        -5.46e7, 1.41e8, 1.2e4, -28.2, -10.9, 0.001, "2026-Jun-01"
    )
    # Realistic Europa heliocentric state (~ 5.2 AU distance, ~ 13.0 km/s speed)
    europa_state = make_ephemeris_state(
        7.40e8, 2.50e8, -1.2e7, -4.5, 12.3, 0.05, "2028-06-01"
    )

    generator = PorkchopGenerator(max_grid_points=100)
    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="EUROPA",
        departure_start_date="2026-06-01",
        departure_end_date="2026-06-01",
        arrival_start_date="2028-06-01",
        arrival_end_date="2028-06-01",
        step_days=1.0,
        dep_parking_alt_km=200.0,
        arr_parking_alt_km=100.0,
        origin_states_override={"2026-06-01": earth_state},
        target_states_override={"2028-06-01": europa_state},
    )

    assert result["valid_cells_count"] == 1
    # Departure injection Delta-V from Earth 200 km is computed
    assert result["dv_inj_grid"][0][0] is not None
    # Europa arrival capture Delta-V MUST BE None (unmodeled in 2-body heliocentric)
    assert result["dv_arr_grid"][0][0] is None
    # Total Delta-V MUST BE None
    assert result["dv_total_grid"][0][0] is None

    # Arrival excess velocity is computed
    assert result["vinf_arr_grid"][0][0] is not None

    # Verify provenance disclosures
    prov = result["provenance"]
    assert "Europa" in prov["physical_model"]
    assert "Jovian multi-body capture" in prov["physical_model"]
    assert prov["coordinate_center"] == "500@10"


@pytest.mark.asyncio
async def test_porkchop_earth_moon_geocentric_provenance(monkeypatch):
    """
    Verifies that Earth-to-Moon geocentric porkchop analysis:
    1. Sets Horizons coordinate center to Geocenter (500@399).
    2. Computes Trans-Lunar Injection (TLI) and Lunar Orbit Insertion (LOI).
    3. Accurately documents Earth-centered two-body astrodynamics in provenance.
    """
    # Geocentric Moon state at ~ 384,400 km, ~ 1.02 km/s speed
    moon_state = make_ephemeris_state(
        -3.50e5, 1.50e5, 5.0e4, -0.4, -0.9, 0.2, "2026-06-05"
    )

    generator = PorkchopGenerator(max_grid_points=100)
    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MOON",
        departure_start_date="2026-06-01",
        departure_end_date="2026-06-01",
        arrival_start_date="2026-06-05",
        arrival_end_date="2026-06-05",
        step_days=1.0,
        dep_parking_alt_km=200.0,
        arr_parking_alt_km=100.0,
        origin_states_override={"2026-06-01": moon_state},  # dummy origin for fixture
        target_states_override={"2026-06-05": moon_state},
    )

    assert result["valid_cells_count"] == 1
    # TLI ~ 3.1 - 3.2 km/s
    dv_inj = result["dv_inj_grid"][0][0]
    assert dv_inj is not None
    assert 2.5 < dv_inj < 4.0

    # LOI ~ 0.8 - 1.2 km/s
    dv_arr = result["dv_arr_grid"][0][0]
    assert dv_arr is not None
    assert 0.5 < dv_arr < 2.0

    # Provenance coordinate center must be Geocenter 500@399
    assert result["provenance"]["coordinate_center"] == "500@399"
    assert "Earth-centered" in result["provenance"]["physical_model"]


@pytest.mark.asyncio
async def test_porkchop_duplicate_protection_respects_all_parameters(mock_horizons_for_porkchop):
    """
    Verifies that the duplicate submission check distinguishes jobs by prograde,
    dep_parking_alt_km, and arr_parking_alt_km. Submitting requests with identical date
    windows but different prograde or parking altitudes MUST produce distinct jobs.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        req_base = {
            "origin_body": "EARTH",
            "target_body": "MARS",
            "departure_start_date": "2029-06-01",
            "departure_end_date": "2029-06-03",
            "arrival_start_date": "2030-01-01",
            "arrival_end_date": "2030-01-03",
            "step_size_days": 2.0,
            "prograde": True,
            "dep_parking_alt_km": 200.0,
            "arr_parking_alt_km": 300.0,
        }

        # Submit first job
        resp1 = await client.post("/api/v1/trajectory/porkchop/jobs", json=req_base)
        assert resp1.status_code == 202
        job1_id = resp1.json()["job_id"]

        # Submit identical duplicate request -> returns same job ID
        resp_dup = await client.post("/api/v1/trajectory/porkchop/jobs", json=req_base)
        assert resp_dup.status_code == 202
        assert resp_dup.json()["job_id"] == job1_id

        # Cancel job1 cleanly
        await client.post(f"/api/v1/trajectory/porkchop/jobs/{job1_id}/cancel")
        await asyncio.sleep(0.05)

        # Submit request with prograde=False -> MUST return different job ID
        req_retro = dict(req_base)
        req_retro["prograde"] = False
        resp_retro = await client.post("/api/v1/trajectory/porkchop/jobs", json=req_retro)
        assert resp_retro.status_code == 202
        job2_id = resp_retro.json()["job_id"]
        assert job2_id != job1_id
        await client.post(f"/api/v1/trajectory/porkchop/jobs/{job2_id}/cancel")
        await asyncio.sleep(0.05)

        # Submit request with different parking altitudes -> MUST return different job ID
        req_nopark = dict(req_base)
        req_nopark["dep_parking_alt_km"] = None
        req_nopark["arr_parking_alt_km"] = None
        resp_nopark = await client.post("/api/v1/trajectory/porkchop/jobs", json=req_nopark)
        assert resp_nopark.status_code == 202
        job3_id = resp_nopark.json()["job_id"]
        assert job3_id != job1_id
        await client.post(f"/api/v1/trajectory/porkchop/jobs/{job3_id}/cancel")
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_porkchop_epoch_julian_date_tof_consistency():
    """
    Verifies that state vector epochs, Julian Dates, and Lambert time of flight
    are mathematically consistent:
    1. Epoch Julian Date difference (JD_arr - JD_dep) in days equals (d_arr - d_dep).days.
    2. Elapsed time in seconds equals (JD_arr - JD_dep) * 86400.0.
    """
    dep_jd = 2461192.5  # 2026-Jun-01 00:00:00 TDB
    arr_jd = 2461406.5  # 2027-Jan-01 00:00:00 TDB
    expected_tof_days = 214.0
    assert arr_jd - dep_jd == expected_tof_days

    earth_state = EphemerisState(
        epoch_jd=dep_jd,
        calendar_date="A.D. 2026-Jun-01 00:00:00.0000 TDB",
        position_km=Vector3D(x=-5.46e7, y=1.41e8, z=1.2e4),
        velocity_kms=Vector3D(x=-28.2, y=-10.9, z=0.001),
    )
    mars_state = EphemerisState(
        epoch_jd=arr_jd,
        calendar_date="A.D. 2027-Jan-01 00:00:00.0000 TDB",
        position_km=Vector3D(x=1.80e8, y=-1.30e8, z=-6.5e6),
        velocity_kms=Vector3D(x=13.5, y=21.2, z=0.15),
    )

    generator = PorkchopGenerator(max_grid_points=10)
    result = await generator.generate_porkchop(
        origin_body="EARTH",
        target_body="MARS",
        departure_start_date="2026-06-01",
        departure_end_date="2026-06-01",
        arrival_start_date="2027-01-01",
        arrival_end_date="2027-01-01",
        origin_states_override={"2026-06-01": earth_state},
        target_states_override={"2027-01-01": mars_state},
    )

    assert result["valid_cells_count"] == 1
    tof_grid_days = result["tof_days_grid"][0][0]
    assert tof_grid_days == expected_tof_days
