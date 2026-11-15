"""
Comprehensive API and Database Test Suite
Covers all registered Phase 1 routes:
  - System Health & Diagnostics (/health, /ready)
  - Deterministic Aerospace Physics (/api/v1/physics/*)
  - Mission & Spacecraft Design Lifecycle (/api/v1/missions/*)
  - Component Catalog (/api/v1/components/*)
"""

import pytest
from httpx import AsyncClient
from backend.app.main import app
from backend.app.core.database import get_db


def test_discover_registered_routes():
    """Discovers and logs every registered API route in the application."""
    routes = [
        f"{list(route.methods)[0] if route.methods else 'WS'} {route.path}"
        for route in app.routes
        if hasattr(route, "path")
    ]
    assert len(routes) >= 14
    # Ensure critical endpoints are registered
    assert any("/health" in r for r in routes)
    assert any("/ready" in r for r in routes)
    assert any("/physics/propulsion-tradeoff" in r for r in routes)
    assert any("/physics/swapc" in r for r in routes)
    assert any("/missions" in r for r in routes)
    assert any("/components" in r for r in routes)


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """GET /health returns 200 OK with service details."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "service" in data


@pytest.mark.asyncio
async def test_readiness_check_healthy(async_client: AsyncClient):
    """GET /ready returns 200 OK when database is operational."""
    response = await async_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["physics_engine"] == "operational"


@pytest.mark.asyncio
async def test_readiness_check_database_disconnected():
    """GET /ready returns 503 Service Unavailable when DB is disconnected."""
    from httpx import ASGITransport

    class DisconnectedSession:
        async def execute(self, *args, **kwargs):
            raise ConnectionError("Simulated Database Connection Failure")

    async def disconnected_get_db():
        yield DisconnectedSession()

    app.dependency_overrides[get_db] = disconnected_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
    app.dependency_overrides.clear()


# ===========================================================================
# PHYSICS API ROUTE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_physics_tsiolkovsky_success(async_client: AsyncClient):
    payload = {"isp_seconds": 320.0, "wet_mass_kg": 1200.0, "dry_mass_kg": 400.0}
    response = await async_client.post("/api/v1/physics/tsiolkovsky", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "delta_v_mps" in data
    assert data["delta_v_mps"] > 3000.0


@pytest.mark.asyncio
async def test_physics_tsiolkovsky_validation_error(async_client: AsyncClient):
    # Wet mass less than dry mass
    payload = {"isp_seconds": 320.0, "wet_mass_kg": 300.0, "dry_mass_kg": 400.0}
    response = await async_client.post("/api/v1/physics/tsiolkovsky", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_physics_propellant_mass_success(async_client: AsyncClient):
    payload = {"isp_seconds": 315.0, "dry_mass_kg": 500.0, "delta_v_mps": 2000.0}
    response = await async_client.post("/api/v1/physics/propellant-mass", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["propellant_mass_kg"] > 0
    assert data["wet_mass_kg"] == pytest.approx(
        data["dry_mass_kg"] + data["propellant_mass_kg"], abs=0.01
    )


@pytest.mark.asyncio
async def test_physics_propulsion_tradeoff_valid_json_body(async_client: AsyncClient):
    """
    Remediation 6: Verifies propulsion-tradeoff accepts typed JSON request body
    and returns full documented response with trade-off analysis.
    """
    payload = {"m_dry_kg": 850.0, "delta_v_mps": 3200.0}
    response = await async_client.post("/api/v1/physics/propulsion-tradeoff", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["m_dry_kg"] == 850.0
    assert data["delta_v_mps"] == 3200.0
    assert "chemical_bipropellant" in data
    assert "electric_ion_propulsion" in data
    assert "trade_off_analysis" in data
    assert (
        data["chemical_bipropellant"]["propellant_mass_kg"]
        > data["electric_ion_propulsion"]["propellant_mass_kg"]
    )
    assert data["trade_off_analysis"]["propellant_reduction_percent"] > 80.0


@pytest.mark.asyncio
async def test_physics_propulsion_tradeoff_invalid_inputs(async_client: AsyncClient):
    """Rejects missing fields, negative dry mass, and malformed body with 422."""
    # Missing delta_v_mps
    res1 = await async_client.post("/api/v1/physics/propulsion-tradeoff", json={"m_dry_kg": 500.0})
    assert res1.status_code == 422

    # Negative dry mass
    res2 = await async_client.post(
        "/api/v1/physics/propulsion-tradeoff",
        json={"m_dry_kg": -100.0, "delta_v_mps": 2000.0},
    )
    assert res2.status_code == 422

    # Malformed non-JSON
    res3 = await async_client.post(
        "/api/v1/physics/propulsion-tradeoff",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert res3.status_code == 422


@pytest.mark.asyncio
async def test_physics_solar_power(async_client: AsyncClient):
    payload = {"distance_au": 1.524, "area_m2": 10.0, "efficiency": 0.30}
    response = await async_client.post("/api/v1/physics/solar-power", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "solar_flux_w_m2" in data
    assert "generated_power_w" in data
    assert data["generated_power_w"] > 0


@pytest.mark.asyncio
async def test_physics_mmrtg_decay(async_client: AsyncClient):
    payload = {"p_bol_w": 110.0, "time_years": 5.0, "annual_decay_rate": 0.008}
    response = await async_client.post("/api/v1/physics/mmrtg-decay", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["power_output_w"] < 110.0
    assert data["total_degradation_percent"] > 0.0


@pytest.mark.asyncio
async def test_physics_link_budget(async_client: AsyncClient):
    payload = {
        "distance_m": 2.25e11,
        "frequency_hz": 8.425e9,
        "tx_power_w": 20.0,
        "tx_antenna_diameter_m": 1.5,
        "rx_antenna_diameter_m": 70.0,
        "data_rate_bps": 10_000.0,
    }
    response = await async_client.post("/api/v1/physics/link-budget", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "link_margin_db" in data
    assert "rtlt_formatted" in data


@pytest.mark.asyncio
async def test_physics_swapc_direct(async_client: AsyncClient):
    payload = {
        "target": "MARS",
        "mission_class": "DISCOVERY",
        "required_delta_v_mps": 1500.0,
        "components": [
            {
                "name": "Bus Structure",
                "subsystem": "STRUCTURE",
                "mass_kg": 250.0,
                "power_draw_w": 30.0,
                "cost_usd": 15_000_000.0,
            },
            {
                "name": "Chemical Thruster",
                "subsystem": "PROPULSION",
                "mass_kg": 35.0,
                "power_draw_w": 10.0,
                "cost_usd": 3_000_000.0,
                "isp_seconds": 315.0,
                "thrust_newtons": 200.0,
            },
            {
                "name": "Solar Array",
                "subsystem": "POWER",
                "mass_kg": 15.0,
                "power_draw_w": 0.0,
                "cost_usd": 2_000_000.0,
                "solar_area_m2": 8.0,
                "solar_efficiency": 0.30,
            },
        ],
    }
    response = await async_client.post("/api/v1/physics/swapc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "dry_mass_kg" in data
    assert "wet_mass_kg" in data
    assert "is_feasible" in data


# ===========================================================================
# MISSION LIFECYCLE API ROUTE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_mission_lifecycle_crud_and_designs(async_client: AsyncClient):
    """
    End-to-end integration test of Mission creation, listing, retrieval,
    and Spacecraft Design versioning with automatic SWaP-C persistence.
    """
    # 1. Create Mission
    mission_payload = {
        "name": "Europa Deep Explorer",
        "description": "Outer solar system flagship exploration",
        "target": "EUROPA",
        "mission_class": "FLAGSHIP",
        "budget_cap_usd": 3_500_000_000.0,
        "max_launch_mass_kg": 5000.0,
        "min_delta_v_mps": 2200.0,
    }
    create_res = await async_client.post("/api/v1/missions", json=mission_payload)
    assert create_res.status_code == 201
    mission = create_res.json()
    mission_id = mission["id"]
    assert mission["name"] == mission_payload["name"]

    # 2. List Missions
    list_res = await async_client.get("/api/v1/missions")
    assert list_res.status_code == 200
    missions = list_res.json()
    assert any(m["id"] == mission_id for m in missions)

    # 3. Get Mission by ID
    get_res = await async_client.get(f"/api/v1/missions/{mission_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == mission_id

    # 4. Create Spacecraft Design with SWaP-C Evaluation
    design_payload = {
        "name": "Design Alpha",
        "components": [
            {
                "name": "MMRTG Power Unit",
                "subsystem": "POWER",
                "mass_kg": 44.0,
                "power_generation_w": 110.0,
                "cost_usd": 70_000_000.0,
                "is_radioisotope": True,
            },
            {
                "name": "Titanium Bus Structure",
                "subsystem": "STRUCTURE",
                "mass_kg": 400.0,
                "power_draw_w": 40.0,
                "cost_usd": 40_000_000.0,
            },
            {
                "name": "Bipropellant Thruster",
                "subsystem": "PROPULSION",
                "mass_kg": 60.0,
                "power_draw_w": 25.0,
                "cost_usd": 8_000_000.0,
                "isp_seconds": 320.0,
                "thrust_newtons": 440.0,
            },
        ],
    }
    design_res = await async_client.post(
        f"/api/v1/missions/{mission_id}/designs", json=design_payload
    )
    assert design_res.status_code == 201
    design = design_res.json()
    assert design["mission_id"] == mission_id
    assert design["dry_mass_kg"] > 0
    assert design["wet_mass_kg"] >= design["dry_mass_kg"]
    assert "delta_v_mps" in design
    assert "total_cost_usd" in design

    # 5. List Designs for Mission
    designs_list_res = await async_client.get(f"/api/v1/missions/{mission_id}/designs")
    assert designs_list_res.status_code == 200
    assert len(designs_list_res.json()) >= 1


@pytest.mark.asyncio
async def test_get_mission_not_found(async_client: AsyncClient):
    response = await async_client.get("/api/v1/missions/nonexistent-id-999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_design_mission_not_found(async_client: AsyncClient):
    payload = {"name": "Orphan Design", "components": []}
    response = await async_client.post("/api/v1/missions/nonexistent-id-999/designs", json=payload)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_physics_mmrtg_decay_breakdown_endpoint(async_client: AsyncClient):
    """Verifies detailed MMRTG decomposition endpoint separating Pu-238 decay from thermocouples."""
    payload = {"p_bol_w": 110.0, "time_years": 8.0, "annual_decay_rate": 0.008}
    response = await async_client.post("/api/v1/physics/mmrtg-decay/breakdown", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "pu238_isotope_fraction_remaining" in data
    assert "thermocouple_fraction_remaining" in data
    assert "combined_fraction_remaining" in data
    assert data["power_output_w"] < 110.0
    assert data["total_degradation_percent"] > 0.0


@pytest.mark.asyncio
async def test_cross_session_persistence(async_client: AsyncClient):
    """
    Remediation 7: Verifies data persisted in one session is accurately
    retrieved across subsequent sessions.
    """
    payload = {
        "name": "Persistence Verification Mission",
        "description": "Multi-session persistence test",
        "target": "TITAN",
        "mission_class": "NEW_FRONTIERS",
        "budget_cap_usd": 1_000_000_000.0,
        "max_launch_mass_kg": 4000.0,
        "min_delta_v_mps": 3500.0,
    }
    create_res = await async_client.post("/api/v1/missions", json=payload)
    assert create_res.status_code == 201
    mission_id = create_res.json()["id"]

    # Retrieve in a distinct request
    get_res = await async_client.get(f"/api/v1/missions/{mission_id}")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["id"] == mission_id
    assert retrieved["name"] == payload["name"]
    assert retrieved["target"] == "TITAN"
    assert retrieved["budget_cap_usd"] == 1_000_000_000.0


@pytest.mark.asyncio
async def test_transaction_rollback_no_partial_records(async_client: AsyncClient):
    """
    Remediation 7: Failed transactions must cleanly rollback without leaving partial records.
    """
    # 1. Create a valid mission
    m_res = await async_client.post("/api/v1/missions", json={
        "name": "Rollback Test Mission",
        "target": "MARS",
        "mission_class": "DISCOVERY",
    })
    assert m_res.status_code == 201
    m_id = m_res.json()["id"]

    # 2. Count existing designs before
    initial_designs = await async_client.get(f"/api/v1/missions/{m_id}/designs")
    initial_count = len(initial_designs.json())

    # 3. Submit invalid design payload with negative mass
    bad_payload = {
        "name": "Corrupt Design",
        "components": [
            {
                "name": "Broken Component",
                "subsystem": "STRUCTURE",
                "mass_kg": -999.0,  # Invalid negative mass
            }
        ],
    }
    fail_res = await async_client.post(f"/api/v1/missions/{m_id}/designs", json=bad_payload)
    assert fail_res.status_code == 422

    # 4. Verify no partial design was persisted
    after_designs = await async_client.get(f"/api/v1/missions/{m_id}/designs")
    assert len(after_designs.json()) == initial_count


@pytest.mark.asyncio
async def test_europa_mmrtg_scenario_deep_verification(async_client: AsyncClient):
    """
    Remediation 7 Weakness 1: Europa/MMRTG scenario must assert the actual feasibility result
    and inspect ALL violations — not pass merely because one unrelated violation list is empty.
    """
    # Infeasible case: Europa mission with excessive payload load and inadequate power
    infeasible_payload = {
        "target": "EUROPA",
        "mission_class": "FLAGSHIP",
        "required_delta_v_mps": 2500.0,
        "components": [
            {
                "name": "Single MMRTG Unit",
                "subsystem": "POWER",
                "mass_kg": 44.0,
                "power_generation_w": 110.0,
                "cost_usd": 70_000_000.0,
                "is_radioisotope": True,
            },
            {
                "name": "Massive Cryogenic Radar",
                "subsystem": "SCIENCE",
                "mass_kg": 200.0,
                "power_draw_w": 350.0,  # Far exceeds ~100 W MMRTG output
                "cost_usd": 150_000_000.0,
            },
            {
                "name": "Biprop Propulsion",
                "subsystem": "PROPULSION",
                "mass_kg": 50.0,
                "power_draw_w": 20.0,
                "cost_usd": 8_000_000.0,
                "isp_seconds": 315.0,
                "thrust_newtons": 400.0,
            },
            {
                "name": "Bus Structure",
                "subsystem": "STRUCTURE",
                "mass_kg": 400.0,
                "power_draw_w": 30.0,
                "cost_usd": 20_000_000.0,
            },
        ],
    }
    res = await async_client.post("/api/v1/physics/swapc", json=infeasible_payload)
    assert res.status_code == 200
    data = res.json()

    # Must be INFEASIBLE
    assert data["is_feasible"] is False
    assert data["status"] == "INFEASIBLE"
    assert len(data["violations"]) > 0

    # Specifically verify the POWER_DEFICIT violation
    power_violations = [v for v in data["violations"] if v["constraint_type"] == "POWER_DEFICIT"]
    assert len(power_violations) == 1
    pv = power_violations[0]
    assert pv["severity"] == "CRITICAL"
    assert pv["actual_value"] < pv["limit_value"]
    assert "exceeds power generated" in pv["message"]
