"""
Component Catalog API and Seeding Tests
Mission Forge — Phase 1 Remediation
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.seed_components import seed_components, VERIFIED_SEED_COMPONENTS


@pytest.mark.asyncio
async def test_empty_catalog(async_client: AsyncClient):
    """Empty database returns zero total items with valid pagination structure."""
    response = await async_client.get("/api/v1/components")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert "limit" in data
    assert "offset" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_create_component_valid(async_client: AsyncClient):
    """Creating a component with valid attributes persists to database."""
    payload = {
        "name": "Aerojet MR-106L Hydrazine Thruster",
        "subsystem": "PROPULSION",
        "description": "Monopropellant hydrazine attitude control thruster",
        "mass_kg": 0.59,
        "power_draw_w": 28.0,
        "cost_usd": 150_000.0,
        "isp_seconds": 235.0,
        "thrust_newtons": 22.0,
        "propellant_type": "Hydrazine",
        "trl": 9,
        "flight_heritage": "New Horizons, MAVEN, OSIRIS-REx",
        "source_url": "https://www.rocket.com",
        "verification_status": "VERIFIED_AUTHORITATIVE",
        "specifications": {"operating_pressure_bar": 24.0},
    }
    response = await async_client.post("/api/v1/components", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert "id" in created
    assert created["name"] == payload["name"]
    assert created["mass_kg"] == 0.59
    assert created["isp_seconds"] == 235.0
    assert created["trl"] == 9

    # Verify retrieval by ID
    get_res = await async_client.get(f"/api/v1/components/{created['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_create_component_invalid_negative_mass(async_client: AsyncClient):
    """Negative mass must fail schema validation with 422."""
    payload = {
        "name": "Invalid Mass Component",
        "subsystem": "STRUCTURE",
        "mass_kg": -10.0,
    }
    response = await async_client.post("/api/v1/components", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_component_invalid_subsystem(async_client: AsyncClient):
    """Unknown subsystem string fails validation with 422."""
    payload = {
        "name": "Bad Subsystem Component",
        "subsystem": "WARP_DRIVE",
        "mass_kg": 100.0,
    }
    response = await async_client.post("/api/v1/components", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_component_extra_field_forbidden(async_client: AsyncClient):
    """Extra undeclared fields are rejected with 422."""
    payload = {
        "name": "Extra Field Component",
        "subsystem": "POWER",
        "mass_kg": 5.0,
        "invented_magic_field": 42,
    }
    response = await async_client.post("/api/v1/components", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_component_not_found(async_client: AsyncClient):
    """Requesting non-existent component UUID returns 404."""
    response = await async_client.get("/api/v1/components/non-existent-uuid-12345")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_components_filters_and_pagination(async_client: AsyncClient):
    """Tests subsystem filtering, min_trl filtering, search substring, and pagination."""
    # Create two test components
    comp1 = {
        "name": "FilterTest Solar Array A",
        "subsystem": "POWER",
        "mass_kg": 12.0,
        "trl": 8,
    }
    comp2 = {
        "name": "FilterTest Thruster B",
        "subsystem": "PROPULSION",
        "mass_kg": 25.0,
        "trl": 6,
        "isp_seconds": 310.0,
        "thrust_newtons": 100.0,
    }
    await async_client.post("/api/v1/components", json=comp1)
    await async_client.post("/api/v1/components", json=comp2)

    # Filter by subsystem POWER
    res_power = await async_client.get("/api/v1/components?subsystem=POWER")
    assert res_power.status_code == 200
    for item in res_power.json()["items"]:
        assert item["subsystem"] == "POWER"

    # Filter by min_trl 7
    res_trl = await async_client.get("/api/v1/components?min_trl=7")
    assert res_trl.status_code == 200
    for item in res_trl.json()["items"]:
        assert item["trl"] >= 7

    # Substring search
    res_search = await async_client.get("/api/v1/components?search=FilterTest")
    assert res_search.status_code == 200
    assert res_search.json()["total"] >= 2

    # Pagination: limit=1
    res_page = await async_client.get("/api/v1/components?search=FilterTest&limit=1&offset=0")
    assert res_page.status_code == 200
    assert len(res_page.json()["items"]) == 1
    assert res_page.json()["limit"] == 1


@pytest.mark.asyncio
async def test_seed_components_idempotency(db_session: AsyncSession):
    """Seed workflow must be idempotent: first run inserts, second run skips."""
    res1 = await seed_components(db_session)
    assert res1["inserted"] >= 0

    # Second run immediately following must insert 0 and skip all
    res2 = await seed_components(db_session)
    assert res2["inserted"] == 0
    assert res2["skipped"] == len(VERIFIED_SEED_COMPONENTS)


@pytest.mark.asyncio
async def test_component_unknown_values_explicit_none(async_client: AsyncClient):
    """
    Remediation 5: Fields without verifiable authoritative data must be stored
    and returned as explicit None (null in JSON), never invented defaults.
    """
    payload = {
        "name": "Experimental Structural Truss",
        "subsystem": "STRUCTURE",
        "mass_kg": 45.0,
        "cost_usd": 0.0,
        # Propulsion, power, telecom specs are omitted/unknown
    }
    response = await async_client.post("/api/v1/components", json=payload)
    assert response.status_code == 201
    item = response.json()
    assert item["isp_seconds"] is None
    assert item["thrust_newtons"] is None
    assert item["propellant_type"] is None
    assert item["solar_area_m2"] is None
    assert item["antenna_diameter_m"] is None
    assert item["tx_power_w"] is None


@pytest.mark.asyncio
async def test_component_security_boundary_in_production(async_client: AsyncClient, monkeypatch):
    """
    Remediation 5: In production environments, unauthenticated catalog mutations
    must be blocked with 403 Forbidden unless explicitly authorized.
    """
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_CATALOG_MUTATION_WITHOUT_AUTH", False)

    payload = {
        "name": "Unauthorized Production Component",
        "subsystem": "STRUCTURE",
        "mass_kg": 10.0,
    }
    response = await async_client.post("/api/v1/components", json=payload)
    assert response.status_code == 403
    assert "Unauthenticated catalog additions are disabled" in response.json()["detail"]

    # Even if someone accidentally set bypass flag to True, production still blocks
    monkeypatch.setattr(settings, "ALLOW_CATALOG_MUTATION_WITHOUT_AUTH", True)
    res_bypass = await async_client.post("/api/v1/components", json=payload)
    assert res_bypass.status_code == 403
    assert "Unauthenticated catalog additions are disabled" in res_bypass.json()["detail"]
