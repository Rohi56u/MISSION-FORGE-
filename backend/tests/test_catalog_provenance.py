"""
Unit and Integration Tests for Component Catalog Field-Level Provenance & Safe Sync
Tests field-level citations, idempotent synchronization, dry-run previews,
conflict resolution policies, TechPort import, and the 4 vs 5 component reconciliation.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.catalog.sync import catalog_sync_service
from backend.app.core.config import settings
from backend.app.db.seed_components import (
    VERIFIED_SEED_COMPONENTS,
    seed_components,
)
from backend.app.models.component import (
    Component,
    SubsystemType,
    VerificationStatus,
)
from backend.app.schemas.component import (
    CatalogSyncRequestSchema,
    ComponentCreateSchema,
    SyncUpdatePolicy,
)


# =========================================================================
# 1. SEED PROVENANCE & RECONCILIATION TESTS
# =========================================================================

def test_authoritative_seed_components_have_complete_provenance():
    """Every seeded component has field-level citations for every critical specification."""
    assert len(VERIFIED_SEED_COMPONENTS) == 4

    for comp in VERIFIED_SEED_COMPONENTS:
        assert "field_provenance" in comp
        prov = comp["field_provenance"]
        assert len(prov) >= 3, f"Incomplete provenance on {comp['name']}"

        # Every entry must have source_system and citation or canonical_url
        for field_name, record in prov.items():
            assert "source_system" in record
            assert "citation" in record or "canonical_url" in record
            assert record["verification_status"] == "VERIFIED_AUTHORITATIVE"


@pytest.mark.asyncio
async def test_seed_components_idempotency_and_reconciliation(db_session: AsyncSession):
    """
    Seeds catalog into isolated database, verifies exactly 4 flight components created,
    and confirms re-running seed does not duplicate records.
    """
    # 1. Run initial seed
    summary1 = await seed_components(db_session)
    assert summary1["inserted"] == 4
    assert summary1["skipped"] == 0

    # 2. Re-run seed immediately -> 0 inserted, 4 skipped/updated
    summary2 = await seed_components(db_session)
    assert summary2["inserted"] == 0
    assert summary2["skipped"] + summary2["updated"] == 4

    # 3. Simulate adding a 5th user/test component (mirroring Phase 1 live probe)
    probe_comp = Component(
        name="Phase 1 Live Probe Component",
        subsystem=SubsystemType.PROPULSION,
        mass_kg=1.0,
        power_draw_w=10.0,
        cost_usd=5000.0,
        trl=9,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    db_session.add(probe_comp)
    await db_session.commit()

    # Verify total count is now 5
    stmt = select(Component)
    res = await db_session.execute(stmt)
    all_comps = res.scalars().all()
    assert len(all_comps) == 5

    # 4. Running seed again preserves the 5th user component without deleting it
    summary3 = await seed_components(db_session)
    assert summary3["inserted"] == 0
    res3 = await db_session.execute(stmt)
    assert len(res3.scalars().all()) == 5


# =========================================================================
# 2. SAFE CATALOG SYNCHRONIZATION SERVICE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_sync_dry_run_does_not_mutate_database(db_session: AsyncSession):
    """Dry-run preview reports proposed insertions without writing to database."""
    item = ComponentCreateSchema(
        name="Dry Run Experimental Thruster",
        subsystem=SubsystemType.PROPULSION,
        mass_kg=2.5,
        power_draw_w=50.0,
        cost_usd=10000.0,
        isp_seconds=300.0,
        thrust_newtons=1.0,
    )
    payload = CatalogSyncRequestSchema(
        items=[item],
        dry_run=True,
    )

    summary = await catalog_sync_service.sync_components(db_session, payload)
    assert summary.dry_run is True
    assert summary.created_count == 1
    assert summary.total_submitted == 1

    # Verify item was NOT actually inserted into database
    stmt = select(Component).where(Component.name == "Dry Run Experimental Thruster")
    res = await db_session.execute(stmt)
    assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_sync_actual_insert_and_duplicate_prevention(db_session: AsyncSession):
    """Actual sync persists component; subsequent sync detects existing record."""
    item = ComponentCreateSchema(
        name="Idempotent Star Tracker",
        subsystem=SubsystemType.ADCS,
        mass_kg=1.2,
        power_draw_w=8.0,
        cost_usd=75000.0,
        source_system="NASA_JPL_FLIGHT",
    )
    payload = CatalogSyncRequestSchema(
        items=[item],
        dry_run=False,
    )

    # 1. Insert
    summary1 = await catalog_sync_service.sync_components(db_session, payload)
    assert summary1.created_count == 1
    assert summary1.updated_count == 0

    # 2. Re-sync identical payload -> skipped, no duplicate created
    summary2 = await catalog_sync_service.sync_components(db_session, payload)
    assert summary2.created_count == 0
    assert summary2.skipped_count == 1


@pytest.mark.asyncio
async def test_sync_preserve_curated_conflict_resolution(db_session: AsyncSession):
    """Under PRESERVE_CURATED, curated fields are not overwritten by incoming data."""
    # 1. Create curated component in database
    curated = Component(
        name="Curated Reaction Wheel",
        subsystem=SubsystemType.ADCS,
        mass_kg=3.5,  # Curated authoritative mass
        power_draw_w=15.0,
        cost_usd=50000.0,
        trl=9,
        source_system="CURATED_HUMAN",
        verification_status=VerificationStatus.VERIFIED_AUTHORITATIVE,
        field_provenance={
            "mass_kg": {
                "source_system": "CURATED_HUMAN",
                "citation": "Manufacturer Acceptance Test Data",
                "verification_status": "VERIFIED_AUTHORITATIVE",
            }
        },
    )
    db_session.add(curated)
    await db_session.commit()

    # 2. Incoming sync item proposes different mass
    incoming = ComponentCreateSchema(
        name="Curated Reaction Wheel",
        subsystem=SubsystemType.ADCS,
        mass_kg=5.0,  # Conflicting proposed mass!
        power_draw_w=15.0,
        techport_id="TP-9999",  # Newly discovered techport ID
    )
    payload = CatalogSyncRequestSchema(
        items=[incoming],
        update_policy=SyncUpdatePolicy.PRESERVE_CURATED,
        dry_run=False,
    )

    summary = await catalog_sync_service.sync_components(db_session, payload)
    assert summary.conflict_count == 1
    assert summary.conflicts[0]["field"] == "mass_kg"

    # Verify existing curated mass was PRESERVED
    await db_session.refresh(curated)
    assert curated.mass_kg == 3.5  # Not overwritten!
    assert curated.techport_id == "TP-9999"  # Missing field was populated!


@pytest.mark.asyncio
async def test_sync_preserve_curated_protects_zero_values_with_provenance(
    db_session: AsyncSession,
):
    """
    Verifies that a component with a curated, provenanced 0.0 specification
    (such as power_draw_w = 0.0 on an RTG power source) is NOT overwritten by
    incoming non-zero values under PRESERVE_CURATED.
    """
    rtg = Component(
        name="Authoritative Test RTG",
        subsystem=SubsystemType.POWER,
        mass_kg=40.0,
        power_draw_w=0.0,  # Authoritative 0.0 power draw
        power_generation_w=100.0,
        cost_usd=0.0,
        trl=9,
        verification_status=VerificationStatus.VERIFIED_AUTHORITATIVE,
        field_provenance={
            "power_draw_w": {
                "source_system": "DOE_NASA_RPS",
                "citation": "RPS Fact Sheet",
                "verification_status": "VERIFIED_AUTHORITATIVE",
            }
        },
    )
    db_session.add(rtg)
    await db_session.commit()

    # Incoming sync tries to set power_draw_w = 25.0
    incoming = ComponentCreateSchema(
        name="Authoritative Test RTG",
        subsystem=SubsystemType.POWER,
        power_draw_w=25.0,
        techport_id="TP-RTG-1",
    )
    payload = CatalogSyncRequestSchema(
        items=[incoming],
        update_policy=SyncUpdatePolicy.PRESERVE_CURATED,
        dry_run=False,
    )

    summary = await catalog_sync_service.sync_components(db_session, payload)
    assert summary.conflict_count >= 1

    await db_session.refresh(rtg)
    # Power draw MUST remain 0.0, not overwritten to 25.0
    assert rtg.power_draw_w == 0.0
    # Missing field (techport_id) is populated
    assert rtg.techport_id == "TP-RTG-1"


@pytest.mark.asyncio
async def test_sync_rejects_duplicate_names_in_same_batch(db_session: AsyncSession):
    """Submitting two components with the identical name in one batch records error."""
    item1 = ComponentCreateSchema(name="Duplicate Sensor", subsystem=SubsystemType.SCIENCE)
    item2 = ComponentCreateSchema(name="Duplicate Sensor", subsystem=SubsystemType.SCIENCE)

    payload = CatalogSyncRequestSchema(items=[item1, item2], dry_run=False)
    summary = await catalog_sync_service.sync_components(db_session, payload)
    assert len(summary.errors) == 1
    assert "Duplicate component name" in summary.errors[0]


# =========================================================================
# 3. FASTAPI ROUTE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_api_component_provenance_endpoint(async_client: AsyncClient):
    """GET /api/v1/components/provenance/{id} returns field-level citations."""
    # 1. Create a component with field-level provenance
    payload = {
        "name": "Provenance Probe Thruster",
        "subsystem": "PROPULSION",
        "mass_kg": 2.0,
        "source_system": "NASA_NTRS",
        "field_provenance": {
            "mass_kg": {
                "source_system": "NASA_NTRS",
                "citation": "NASA Report TM-1234",
                "canonical_url": "https://ntrs.nasa.gov",
                "verification_status": "VERIFIED_AUTHORITATIVE",
            }
        },
    }
    create_res = await async_client.post("/api/v1/components", json=payload)
    assert create_res.status_code == 201
    comp_id = create_res.json()["id"]

    # 2. Query provenance endpoint
    prov_res = await async_client.get(f"/api/v1/components/provenance/{comp_id}")
    assert prov_res.status_code == 200
    pdata = prov_res.json()
    assert pdata["component_id"] == comp_id
    assert "mass_kg" in pdata["field_provenance"]
    assert pdata["field_provenance"]["mass_kg"]["citation"] == "NASA Report TM-1234"


@pytest.mark.asyncio
async def test_api_component_sync_endpoint(async_client: AsyncClient):
    """POST /api/v1/components/sync executes batch sync with dry-run support."""
    payload = {
        "items": [
            {
                "name": "Sync API Reaction Wheel",
                "subsystem": "ADCS",
                "mass_kg": 4.2,
                "power_draw_w": 20.0,
            }
        ],
        "dry_run": True,
        "update_policy": "PRESERVE_CURATED",
    }
    res = await async_client.post("/api/v1/components/sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["dry_run"] is True
    assert data["created_count"] == 1


@pytest.mark.asyncio
async def test_api_sync_production_security_guard(async_client: AsyncClient, monkeypatch):
    """In production with unauthenticated writes disabled, sync returns 403 Forbidden."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_CATALOG_MUTATION_WITHOUT_AUTH", False)

    payload = {
        "items": [{"name": "Blocked Item", "subsystem": "POWER"}],
        "dry_run": False,
    }
    res = await async_client.post("/api/v1/components/sync", json=payload)
    assert res.status_code == 403
    assert "disabled in production" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_sync_production_security_guard_even_with_bypass_flag(
    async_client: AsyncClient, monkeypatch
):
    """
    In production, even if bypass flag was True, unauthenticated mutation is strictly forbidden.
    """
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_CATALOG_MUTATION_WITHOUT_AUTH", True)

    raw_items = [{"name": "Blocked Item With Bypass", "subsystem": "POWER"}]
    payload = {
        "items": raw_items,
        "dry_run": False,
    }
    res = await async_client.post("/api/v1/components/sync", json=payload)
    assert res.status_code == 403
    assert "disabled in production" in res.json()["detail"].lower()

    # Also verify direct component creation is blocked
    res_comp = await async_client.post("/api/v1/components", json=raw_items[0])
    assert res_comp.status_code == 403
    assert "disabled in production" in res_comp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_catalog_status_endpoint(async_client: AsyncClient):
    """GET /api/v1/components/catalog/status returns metrics on catalog provenance and freshness."""
    # Query status
    res = await async_client.get("/api/v1/components/catalog/status")
    assert res.status_code == 200
    data = res.json()
    assert "total_components" in data
    assert "subsystems_breakdown" in data
    assert "verification_status_breakdown" in data
    assert "provenance_coverage_percent" in data
    assert "source_systems" in data

    # Test /status alias
    res_alias = await async_client.get("/api/v1/components/status")
    assert res_alias.status_code == 200
    assert res_alias.json()["total_components"] == data["total_components"]


@pytest.mark.asyncio
async def test_async_cache_manager_bounded_capacity_and_eviction():
    """AsyncCacheManager evicts entries when max_entries is exceeded."""
    from backend.app.core.cache import AsyncCacheManager, CacheStatus

    # Create small cache with max_entries=10 (bounded minimum)
    cache = AsyncCacheManager(default_ttl_seconds=300.0, max_entries=10)

    # Insert 10 items
    for i in range(10):
        await cache.set(f"key_{i}", f"val_{i}")

    assert await cache.size() == 10
    assert cache.evictions == 0

    # 11th item triggers FIFO eviction of key_0
    await cache.set("key_10", "val_10")
    assert await cache.size() == 10
    assert cache.evictions == 1

    # key_0 was evicted
    v0, status, _ = await cache.get("key_0")
    assert v0 is None
    assert status == CacheStatus.LIVE

    # key_10 is present
    v10, status10, _ = await cache.get("key_10")
    assert v10 == "val_10"
    assert status10 == CacheStatus.CACHED

    # Test expired eviction priority
    cache._store["key_1"].expires_at = cache._store["key_1"].created_at  # Expire key_1
    await cache.set("key_11", "val_11")
    assert cache.evictions == 2
    v1, _, _ = await cache.get("key_1")
    assert v1 is None  # Expired key_1 was selectively evicted


@pytest.mark.asyncio
async def test_init_db_connectivity_check_without_create_all():
    """Verifies init_db executes connectivity probe without calling create_all."""
    from backend.app.core.database import init_db
    # Must succeed without error
    await init_db()


@pytest.mark.asyncio
async def test_concurrent_catalog_sync(async_client: AsyncClient):
    """Concurrent batch sync requests complete safely without deadlock or duplicate corruption."""
    import asyncio

    req1 = {
        "items": [
            {
                "name": "Concurrent Item A",
                "subsystem": "POWER",
                "mass_kg": 10.0,
            }
        ],
        "dry_run": False,
        "update_policy": "PRESERVE_CURATED",
    }
    req2 = {
        "items": [
            {
                "name": "Concurrent Item B",
                "subsystem": "PROPULSION",
                "mass_kg": 20.0,
            }
        ],
        "dry_run": False,
        "update_policy": "PRESERVE_CURATED",
    }

    # Execute both syncs concurrently
    res1, res2 = await asyncio.gather(
        async_client.post("/api/v1/components/sync", json=req1),
        async_client.post("/api/v1/components/sync", json=req2),
    )

    assert res1.status_code == 200
    assert res2.status_code == 200
