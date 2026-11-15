"""
Mission Concept Dossier Comprehensive Test Suite
Mission Forge — Phase 6 Verification Suite

Tests Cover:
1. Exact 5-page PDF structural validation and visual content extraction via PyMuPDF.
2. Versioned JSON frozen snapshot schema verification, reproducibility, and immutability.
3. Strict RBAC authorization, ownership enforcement, and cross-user access denial.
4. Malicious user content escaping (HTML/XML injection, oversized payload, path traversal).
5. Background job execution, dynamic progress polling, and failure cleanup.
6. Startup recovery of orphaned queued/generating jobs after process restart.
7. System health and readiness probes with storage verification.
8. Complete end-to-end dossier lifecycle from mission creation to artifact download.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import uuid
import pymupdf  # PyMuPDF
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import create_access_token, hash_password
from backend.app.core.config import settings
from backend.app.dossier.builder import (
    compile_dossier_snapshot,
    sanitize_filename,
    sanitize_text,
)
from backend.app.dossier.pdf_generator import render_dossier_pdf
from backend.app.dossier.service import (
    get_dossier_file_path,
    recover_orphaned_dossier_jobs,
    reset_dossier_rate_limits,
)
from backend.app.models.auth import User
from backend.app.models.cdf import CDFRole, CDFRoom, CDFRoomParticipant, CDFRoomStatus
from backend.app.models.component import Component, SubsystemType, VerificationStatus
from backend.app.models.dossier import (
    DossierJob,
    DossierReport,
    DossierReportStatus,
)
from backend.app.models.fdir import FDIRFindingLog
from backend.app.models.mission import Mission, MissionClass, MissionTarget, SpacecraftDesign
from backend.app.schemas.dossier import DossierFrozenSnapshot


# --- Helper Setup Functions ---

async def make_test_user(db_session: AsyncSession, email: str, name: str) -> tuple[User, str]:
    """Creates a user record and returns (User, jwt_token)."""
    user = User(
        email=email,
        full_name=name,
        hashed_password=hash_password("ClassifiedFlightPass2026!"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token(user_id=user.id, email=user.email)
    return user, token


async def make_test_mission(
    db_session: AsyncSession, name: str = "Europa Life Finder"
) -> tuple[Mission, SpacecraftDesign]:
    """Creates a fully populated mission with components and designs."""
    mission = Mission(
        name=name,
        description="A Flagship mission to evaluate habitability in Europa sub-surface oceans.",
        target=MissionTarget.EUROPA,
        mission_class=MissionClass.FLAGSHIP,
        budget_cap_usd=3_200_000_000.0,
        max_launch_mass_kg=6000.0,
        min_delta_v_mps=4200.0,
        min_power_margin_percent=15.0,
    )
    db_session.add(mission)
    await db_session.commit()
    await db_session.refresh(mission)

    c1 = Component(
        name="Aerojet Dual-Mode Apogee Engine",
        subsystem=SubsystemType.PROPULSION,
        mass_kg=24.5,
        power_draw_w=45.0,
        power_generation_w=0.0,
        cost_usd=12_000_000.0,
        isp_seconds=325.0,
        thrust_newtons=450.0,
        verification_status=VerificationStatus.VERIFIED_AUTHORITATIVE,
    )
    c2 = Component(
        name="UltraFlex Solar Array Wing",
        subsystem=SubsystemType.POWER,
        mass_kg=65.0,
        power_draw_w=0.0,
        power_generation_w=950.0,
        cost_usd=25_000_000.0,
        solar_area_m2=18.5,
        solar_efficiency=0.32,
        verification_status=VerificationStatus.VERIFIED_AUTHORITATIVE,
    )
    c3 = Component(
        name="X/Ka-Band Deep Space Transponder",
        subsystem=SubsystemType.TELECOM,
        mass_kg=12.0,
        power_draw_w=110.0,
        cost_usd=8_500_000.0,
        antenna_diameter_m=2.4,
        verification_status=VerificationStatus.VERIFIED_AUTHORITATIVE,
    )
    db_session.add_all([c1, c2, c3])
    await db_session.commit()
    await db_session.refresh(c1)
    await db_session.refresh(c2)
    await db_session.refresh(c3)

    design = SpacecraftDesign(
        mission_id=mission.id,
        name="Baseline Europa Orbiter Rev 1",
        version=1,
        component_ids=[c1.id, c2.id, c3.id],
        propellant_mass_kg=3200.0,
        dry_mass_kg=1850.0,
        wet_mass_kg=5050.0,
        power_draw_w=650.0,
        power_generation_w=820.0,
        delta_v_mps=4380.0,
        total_cost_usd=1_950_000_000.0,
        is_feasible=True,
        violations=[],
    )
    db_session.add(design)
    await db_session.commit()
    await db_session.refresh(design)

    return mission, design


# --- Unit Tests: Sanitization and Formatting ---

def test_sanitize_text_escaping_and_length():
    """Verifies that HTML/XML entities are safely escaped and strings are bounded."""
    # 1. HTML injection
    raw_html = "<script>alert('pwned');</script> & \"malicious\""
    clean = sanitize_text(raw_html)
    assert "<script>" not in clean
    assert "&lt;script&gt;" in clean
    assert "&amp;" in clean
    assert "&quot;malicious&quot;" in clean

    # 2. Control characters and dangerous schemes
    dangerous_url = "javascript:alert(1)\x00\x08Nominal Text"
    clean_url = sanitize_text(dangerous_url)
    assert "javascript:" not in clean_url
    assert "\x00" not in clean_url
    assert "Nominal Text" in clean_url

    # 3. Truncation
    oversized = "A" * 1000
    clean_bounded = sanitize_text(oversized, max_len=50)
    assert len(clean_bounded) <= 53  # 50 + "..."


def test_sanitize_filename_prevents_path_traversal():
    """Verifies that filename sanitizer strips relative traversal and illegal symbols."""
    raw = "../../../etc/passwd"
    clean = sanitize_filename(raw)
    assert ".." not in clean
    assert "/" not in clean
    assert "\\" not in clean
    assert clean == "etc_passwd"

    dangerous = "Mission Dossier: Europa / Moon & * ! #.pdf"
    clean_safe = sanitize_filename(dangerous)
    assert ".." not in clean_safe
    assert "/" not in clean_safe
    assert "\\" not in clean_safe
    assert clean_safe.endswith(".pdf")


# --- Unit Tests: PDF Generation & Exact 5-Page Layout ---

def test_pdf_exact_5_page_layout():
    """
    Renders a full mission dossier PDF from mock data and verifies with PyMuPDF
    that it produces exactly 5 pages, with non-empty content and authoritative disclaimers.
    """
    snapshot = {
        "schema_version": "1.0.0",
        "software_version": "1.0.0",
        "snapshot_timestamp_utc": "2026-11-15T12:00:00Z",
        "canonical_hash_sha256": "3a7b9c1d8e2f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b",
        "authoritative_disclaimer": (
            "Mission Forge-generated mission concept dossier. Not an official NASA document, "
            "NASA-approved proposal, or NASA-certified analysis."
        ),
        "title": "Mission Concept Dossier: Europa Life Finder",
        "mission": {
            "id": "m-001",
            "name": "Europa Life Finder",
            "description": "Scientific exploration of Europa ocean habitability.",
            "target": "EUROPA",
            "mission_class": "FLAGSHIP",
            "budget_cap_usd": 3200000000.0,
            "max_launch_mass_kg": 6000.0,
            "min_delta_v_mps": 4200.0,
            "min_power_margin_percent": 15.0,
        },
        "design": {
            "id": "d-001",
            "name": "Europa Flagship Baseline",
            "version": 1,
            "dry_mass_kg": 1850.0,
            "wet_mass_kg": 5050.0,
            "propellant_mass_kg": 3200.0,
            "power_draw_w": 650.0,
            "power_generation_w": 820.0,
            "delta_v_mps": 4380.0,
            "total_cost_usd": 1950000000.0,
            "is_feasible": True,
            "violations": [],
        },
        "swapc": {
            "mass_by_subsystem": {
                "STRUCTURE": 500.0,
                "PROPULSION": 400.0,
                "POWER": 350.0,
                "TELECOM": 150.0,
                "SCIENCE": 300.0,
                "THERMAL": 150.0,
            },
            "power_by_subsystem": {
                "SCIENCE": 300.0,
                "TELECOM": 150.0,
                "AVIONICS_BASE": 50.0,
                "ADCS": 150.0,
            },
            "dry_mass_kg": 1850.0,
            "wet_mass_kg": 5050.0,
            "propellant_mass_kg": 3200.0,
            "mass_margin_percent": 15.8,
            "power_draw_w": 650.0,
            "power_generation_w": 820.0,
            "power_margin_percent": 26.2,
            "total_cost_usd": 1950000000.0,
            "cost_margin_percent": 39.1,
            "delta_v_mps": 4380.0,
            "delta_v_margin_percent": 4.3,
            "assumptions": ["Tsiolkovsky equation", "NASA SP-2016-6105 margins"],
        },
        "components": [
            {
                "name": f"Subsystem Unit {i}",
                "subsystem": "SCIENCE",
                "mass_kg": 25.0,
                "power_draw_w": 30.0,
                "cost_usd": 4000000.0,
                "trl": 9,
                "verification_status": "VERIFIED_AUTHORITATIVE",
            }
            for i in range(8)
        ],
        "trajectory": {
            "origin_body": "EARTH",
            "target_body": "EUROPA",
            "departure_epoch": "2026-10-15T00:00:00Z",
            "arrival_epoch": "2032-04-10T00:00:00Z",
            "time_of_flight_days": 2004.0,
            "c3_km2_s2": 31.4,
            "total_delta_v_mps": 4380.0,
            "arrival_v_inf_mps": 2850.0,
            "solver_name": "Lambert Universal Variable Solver",
            "ephemeris_source": "JPL SSD Horizons",
            "coordinate_frame": "ICRF / J2000",
            "time_scale": "TDB",
            "status": "SOLVED_NUMERICAL",
            "astrodynamics_disclaimer": (
                "Two-body Lambert transfer; not a complete operational Jovian tour trajectory."
            ),
        },
        "telecommunications": {
            "ground_network": "NASA Deep Space Network (DSN)",
            "carrier_frequency_hz": 8.425e9,
            "distance_au": 5.2,
            "tx_power_w": 35.0,
            "antenna_diameter_m": 2.4,
            "space_loss_db": 285.4,
            "downlink_rate_bps": 24000.0,
            "link_margin_db": 6.8,
        },
        "cdf": {"status": "STANDALONE_DESIGN"},
        "fdir": {"findings": []},
        "capcom": {
            "authoritative_notice": "AI-GENERATED ADVISORY",
            "mission_synthesis": "Europa exploration mission concept.",
            "critical_tradeoffs": ["High radiation environment", "Long cruise time"],
        },
    }

    pdf_bytes = render_dossier_pdf(snapshot)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF-")

    # PyMuPDF Document Validation
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 5, f"Expected exactly 5 pages, found {len(doc)}"

    # Page 1 checks
    p1_text = doc[0].get_text()
    assert "Europa Life Finder" in p1_text
    assert "AUTHORITATIVE ENGINEERING DISCLAIMER" in p1_text
    assert "01. Mission Objectives" in p1_text
    assert "Page 1 of 5" in p1_text

    # Page 2 checks
    p2_text = doc[1].get_text()
    assert "02. Spacecraft Architecture" in p2_text
    assert "Subsystem Mass & Power Breakdown" in p2_text
    assert "Page 2 of 5" in p2_text

    # Page 3 checks
    p3_text = doc[2].get_text()
    assert "03. Spacecraft Component Ledger" in p3_text
    assert "Bill of Materials (BOM)" in p3_text
    assert "Page 3 of 5" in p3_text

    # Page 4 checks
    p4_text = doc[3].get_text()
    assert "04. Trajectory Optimization" in p4_text
    assert "Deep Space Network (DSN)" in p4_text
    assert "Page 4 of 5" in p4_text

    # Page 5 checks
    p5_text = doc[4].get_text()
    assert "05. Concurrent Engineering" in p5_text
    assert "AI-GENERATED ADVISORY" in p5_text
    assert "Mathematical Snapshot Verification" in p5_text
    assert "Page 5 of 5" in p5_text


# --- Unit Tests: JSON Snapshot Schema & Provenance ---

async def test_compile_dossier_snapshot_schema_validity(db_session: AsyncSession):
    """
    Compiles a snapshot from database records and validates that it strictly satisfies
    the versioned Pydantic DossierFrozenSnapshot schema and includes provenance metadata.
    """
    user, _ = await make_test_user(db_session, "alex@forge.org", "Alex")
    mission, design = await make_test_mission(db_session, "Europa Snapshot Mission")

    snapshot_data = await compile_dossier_snapshot(
        db=db_session,
        mission_id=mission.id,
        user=user,
        design_id=design.id,
        custom_title="Europa Certified Dossier",
    )

    # Validate against Pydantic schema
    validated = DossierFrozenSnapshot.model_validate(snapshot_data)
    assert validated.schema_version == "1.0.0"
    assert validated.title == "Europa Certified Dossier"
    assert validated.mission.name == "Europa Snapshot Mission"
    assert validated.canonical_hash_sha256 is not None
    assert len(validated.canonical_hash_sha256) == 64
    assert len(validated.components) == 3

    # Check component field-level provenance
    comp = validated.components[0]
    assert comp.verification_status == "VERIFIED_AUTHORITATIVE"
    assert "Aerojet" in comp.name


# --- Unit Tests: Immutability and Reproducibility ---

async def test_snapshot_immutability_against_subsequent_mission_mutation(db_session: AsyncSession):
    """
    Proves that mutating a mission in the database does NOT alter an already compiled
    and stored dossier report, guaranteeing mathematical reproducibility.
    """
    user, _ = await make_test_user(db_session, "immutable@forge.org", "Immutable Officer")
    mission, _ = await make_test_mission(db_session, "Immutable Mission")

    # 1. Compile original frozen snapshot
    original_snapshot = await compile_dossier_snapshot(
        db=db_session,
        mission_id=mission.id,
        user=user,
    )
    orig_hash = original_snapshot["canonical_hash_sha256"]
    orig_budget = original_snapshot["mission"]["budget_cap_usd"]

    # 2. Persist DossierReport record
    report = DossierReport(
        mission_id=mission.id,
        user_id=user.id,
        title="Frozen Snapshot Mission Report",
        format="BOTH",
        schema_version="1.0.0",
        snapshot_data=original_snapshot,
        page_count=5,
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    # 3. Later User Mutation: Alter mission name and budget cap radically in database
    mission.name = "Mutated Compromised Mission"
    mission.budget_cap_usd = 999_999_999.0
    await db_session.commit()

    # 4. Fetch the historical report from database
    stmt_rep = select(DossierReport).where(DossierReport.id == report.id)
    res_rep = await db_session.execute(stmt_rep)
    fetched_report = res_rep.scalar_one()

    # 5. Verify the historical snapshot was NOT affected by the later mission mutation
    assert fetched_report.snapshot_data["mission"]["name"] == "Immutable Mission"
    assert fetched_report.snapshot_data["mission"]["budget_cap_usd"] == orig_budget
    assert fetched_report.snapshot_data["canonical_hash_sha256"] == orig_hash


# --- Unit Tests: Orphaned Job Recovery ---

async def test_recover_orphaned_dossier_jobs_on_process_restart(db_session: AsyncSession):
    """
    Verifies that orphaned jobs left in QUEUED or GENERATING state from an unexpected
    server shutdown are recovered and marked FAILED with clear diagnostic messages.
    """
    user, _ = await make_test_user(db_session, "recovery@forge.org", "Recovery Officer")
    mission, _ = await make_test_mission(db_session, "Recovery Mission")

    job_queued = DossierJob(
        mission_id=mission.id,
        user_id=user.id,
        status=DossierReportStatus.QUEUED,
        progress_percent=0.0,
    )
    job_generating = DossierJob(
        mission_id=mission.id,
        user_id=user.id,
        status=DossierReportStatus.GENERATING,
        progress_percent=45.0,
    )
    db_session.add_all([job_queued, job_generating])
    await db_session.commit()

    # Execute startup recovery procedure
    recovered = await recover_orphaned_dossier_jobs(db_session)
    assert recovered == 2

    # Verify both jobs are marked as FAILED
    await db_session.refresh(job_queued)
    await db_session.refresh(job_generating)
    assert job_queued.status == DossierReportStatus.FAILED
    assert "Process restarted" in (job_queued.error_message or "")
    assert job_generating.status == DossierReportStatus.FAILED
    assert "Process restarted" in (job_generating.error_message or "")


# --- Integration & REST API Tests ---

async def test_api_generate_dossier_end_to_end(async_client: AsyncClient, db_session: AsyncSession):
    """
    Full end-to-end integration test:
    1. Authenticated user submits dossier generation request (POST /api/v1/dossiers/generate).
    2. Receives 202 Accepted with job tracking metadata.
    3. Polls job status until COMPLETED (100%).
    4. Downloads generated PDF artifact and verifies 5-page layout.
    5. Downloads generated JSON artifact and verifies cryptographic checksum.
    6. Lists mission dossiers and verifies presence.
    """
    user_a, token_a = await make_test_user(
        db_session, f"pilot_{uuid.uuid4().hex[:6]}@forge.org", "Pilot"
    )
    mission, design = await make_test_mission(db_session, "E2E Mission")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. Submit Generation Request
    payload = {
        "mission_id": mission.id,
        "design_id": design.id,
        "format": "BOTH",
        "title": "Europa Integrated Dossier",
        "include_cdf_history": True,
        "include_fdir_audit": True,
        "include_capcom_summary": True,
    }
    resp = await async_client.post("/api/v1/dossiers/generate", json=payload, headers=headers_a)
    assert resp.status_code == 202, resp.text
    job_data = resp.json()
    job_id = job_data["job_id"]
    assert job_data["status"] == "QUEUED"

    # 2. Poll Job Status Until Completed (Bounded loop)
    report_id = None
    for _ in range(30):
        poll_resp = await async_client.get(f"/api/v1/dossiers/jobs/{job_id}", headers=headers_a)
        assert poll_resp.status_code == 200
        poll_data = poll_resp.json()
        if poll_data["status"] == "COMPLETED":
            report_id = poll_data["report_id"]
            assert poll_data["progress_percent"] == 100.0
            break
        await asyncio.sleep(0.2)

    assert report_id is not None, "Job did not complete within expected timeout window."

    # 3. Retrieve Report Metadata
    meta_resp = await async_client.get(f"/api/v1/dossiers/{report_id}", headers=headers_a)
    assert meta_resp.status_code == 200
    meta_data = meta_resp.json()
    assert meta_data["title"] == "Europa Integrated Dossier"
    assert meta_data["page_count"] == 5
    assert meta_data["pdf_sha256"] is not None
    assert meta_data["json_sha256"] is not None

    # 4. Download PDF Artifact
    pdf_resp = await async_client.get(
        f"/api/v1/dossiers/{report_id}/download?format=pdf", headers=headers_a
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["Content-Type"] == "application/pdf"
    assert "attachment" in pdf_resp.headers["Content-Disposition"]
    assert pdf_resp.headers["ETag"].strip('"') == meta_data["pdf_sha256"]
    pdf_bytes = pdf_resp.content
    assert pdf_bytes.startswith(b"%PDF-")

    # Verify PDF content with PyMuPDF
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 5

    # 5. Download JSON Artifact
    json_resp = await async_client.get(
        f"/api/v1/dossiers/{report_id}/download?format=json", headers=headers_a
    )
    assert json_resp.status_code == 200
    assert json_resp.headers["Content-Type"] == "application/json"
    assert json_resp.headers["ETag"].strip('"') == meta_data["json_sha256"]
    parsed_json = json_resp.json()
    assert parsed_json["schema_version"] == "1.0.0"
    assert parsed_json["mission"]["id"] == mission.id

    # 6. List Mission Dossiers
    list_resp = await async_client.get(
        f"/api/v1/dossiers/missions/{mission.id}", headers=headers_a
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == report_id for r in list_data["reports"])


# --- Security Negative Tests: RBAC Cross-User Access Denial ---

async def test_rbac_cross_user_dossier_access_denied(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Negative Security Test:
    Verifies that User B cannot query or download a private dossier job or report
    compiled by User A, strictly returning 403 Forbidden.
    """
    user_a, token_a = await make_test_user(
        db_session, f"owner_{uuid.uuid4().hex[:6]}@forge.org", "Owner A"
    )
    user_b, token_b = await make_test_user(
        db_session, f"hacker_{uuid.uuid4().hex[:6]}@external.org", "Hacker B"
    )
    mission, design = await make_test_mission(db_session, "Secure Mission")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. User A creates a dossier job
    resp = await async_client.post(
        "/api/v1/dossiers/generate",
        json={"mission_id": mission.id, "design_id": design.id, "format": "BOTH"},
        headers=headers_a,
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Wait for completion
    report_id = None
    for _ in range(30):
        poll_resp = await async_client.get(f"/api/v1/dossiers/jobs/{job_id}", headers=headers_a)
        if poll_resp.json()["status"] == "COMPLETED":
            report_id = poll_resp.json()["report_id"]
            break
        await asyncio.sleep(0.2)
    assert report_id is not None

    # 2. User B tries to access User A's job status -> 403 Forbidden
    cross_job = await async_client.get(f"/api/v1/dossiers/jobs/{job_id}", headers=headers_b)
    assert cross_job.status_code == 403
    assert "not have authorization" in cross_job.json()["detail"]

    # 3. User B tries to view User A's report metadata -> 403 Forbidden
    cross_meta = await async_client.get(f"/api/v1/dossiers/{report_id}", headers=headers_b)
    assert cross_meta.status_code == 403

    # 4. User B tries to download User A's PDF artifact -> 403 Forbidden
    cross_dl = await async_client.get(
        f"/api/v1/dossiers/{report_id}/download?format=pdf", headers=headers_b
    )
    assert cross_dl.status_code == 403

    # 5. Unauthenticated user (no token) -> 401 Unauthorized
    unauth = await async_client.get(f"/api/v1/dossiers/{report_id}/download?format=pdf")
    assert unauth.status_code == 401


# --- Security Negative Tests: Path Traversal & Parameter Tampering ---

async def test_path_traversal_attempts_blocked(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Negative Security Test:
    Ensures that path traversal payloads in URL parameters are rejected before reaching storage.
    """
    _, token_a = await make_test_user(
        db_session, f"guard_{uuid.uuid4().hex[:6]}@forge.org", "Guard"
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Malicious report_id attempting directory traversal
    traversal_ids = [
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "nested/../../secret.key",
        "invalid-uuid-symbols!@#",
    ]
    for tid in traversal_ids:
        resp = await async_client.get(f"/api/v1/dossiers/{tid}/download", headers=headers_a)
        assert resp.status_code in (400, 404), f"Traversal '{tid}' did not return 400/404"


# --- System Health & Readiness Tests ---

async def test_readiness_probe_with_storage(async_client: AsyncClient):
    """
    Verifies that /ready probe checks both database connectivity and dossier storage directory.
    """
    resp = await async_client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["dossier_storage"] == "writable"


# --- Additional Edge Case & Robustness Tests ---

async def test_dossier_empty_components_and_zero_delta_v(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Verifies that a mission with no attached components or design is handled
    gracefully without crashing, resulting in valid fallback estimates and disclosures.
    """
    user, token = await make_test_user(
        db_session, f"empty_{uuid.uuid4().hex[:6]}@forge.org", "Empty Tester"
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Mission with no design or components
    mission = Mission(
        name="Empty Concept Probe",
        description="Concept probe with zero defined hardware.",
        target=MissionTarget.MARS,
        mission_class=MissionClass.DISCOVERY,
        budget_cap_usd=500_000_000.0,
        max_launch_mass_kg=1500.0,
        min_delta_v_mps=3800.0,
        min_power_margin_percent=15.0,
    )
    db_session.add(mission)
    await db_session.commit()
    await db_session.refresh(mission)

    resp = await async_client.post(
        "/api/v1/dossiers/generate",
        json={"mission_id": mission.id, "format": "BOTH"},
        headers=headers,
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    for _ in range(30):
        poll = await async_client.get(f"/api/v1/dossiers/jobs/{job_id}", headers=headers)
        if poll.json()["status"] == "COMPLETED":
            break
        await asyncio.sleep(0.2)

    report_id = poll.json()["report_id"]
    assert report_id is not None

    # Download PDF and verify
    pdf_resp = await async_client.get(
        f"/api/v1/dossiers/{report_id}/download?format=pdf", headers=headers
    )
    assert pdf_resp.status_code == 200
    doc = pymupdf.open(stream=pdf_resp.content, filetype="pdf")
    assert len(doc) == 5
    p3_text = doc[2].get_text()
    assert "No individual components configured" in p3_text


async def test_dossier_malicious_content_and_script_injection(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Submits a dossier with script tags, HTML entities, and Unicode exploit payloads,
    and proves that the sanitizer escapes them and the PDF builds without XML parse errors.
    """
    user, token = await make_test_user(
        db_session, f"sec_{uuid.uuid4().hex[:6]}@forge.org", "Sec Tester"
    )
    headers = {"Authorization": f"Bearer {token}"}

    xss_name = "Injection Probe <script>alert('xss')</script> & </title>"
    mission, design = await make_test_mission(db_session, xss_name)

    malicious_title = "<img src=x onerror=alert(1)> Custom Exploit Title & <bold>"
    resp = await async_client.post(
        "/api/v1/dossiers/generate",
        json={
            "mission_id": mission.id,
            "design_id": design.id,
            "title": malicious_title,
            "format": "BOTH",
        },
        headers=headers,
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    for _ in range(30):
        poll = await async_client.get(f"/api/v1/dossiers/jobs/{job_id}", headers=headers)
        if poll.json()["status"] == "COMPLETED":
            break
        await asyncio.sleep(0.2)

    report_id = poll.json()["report_id"]
    assert report_id is not None

    # Check JSON
    json_resp = await async_client.get(
        f"/api/v1/dossiers/{report_id}/download?format=json", headers=headers
    )
    assert json_resp.status_code == 200
    j_data = json_resp.json()
    assert "<script>" not in j_data["mission"]["name"]
    assert "&lt;script&gt;" in j_data["mission"]["name"]

    # Check PDF builds cleanly
    pdf_resp = await async_client.get(
        f"/api/v1/dossiers/{report_id}/download?format=pdf", headers=headers
    )
    assert pdf_resp.status_code == 200
    doc = pymupdf.open(stream=pdf_resp.content, filetype="pdf")
    assert len(doc) == 5


async def test_dossier_api_nonexistent_resources(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verifies standard 404 responses for non-existent mission, job, or report IDs."""
    _, token = await make_test_user(
        db_session, f"probe_{uuid.uuid4().hex[:6]}@forge.org", "Probe"
    )
    headers = {"Authorization": f"Bearer {token}"}
    fake_uuid = str(uuid.uuid4())

    # Generate with non-existent mission
    g_404 = await async_client.post(
        "/api/v1/dossiers/generate",
        json={"mission_id": fake_uuid},
        headers=headers,
    )
    assert g_404.status_code == 404

    # Get non-existent job
    j_404 = await async_client.get(f"/api/v1/dossiers/jobs/{fake_uuid}", headers=headers)
    assert j_404.status_code == 404

    # Get non-existent report
    r_404 = await async_client.get(f"/api/v1/dossiers/{fake_uuid}", headers=headers)
    assert r_404.status_code == 404

    # Download non-existent report
    d_404 = await async_client.get(f"/api/v1/dossiers/{fake_uuid}/download", headers=headers)
    assert d_404.status_code == 404


async def test_dossier_cdf_room_authorization_check(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Verifies that a user attempting to generate a dossier with a room_id they do NOT
    belong to is rejected with 403 Forbidden.
    """
    user_a, token_a = await make_test_user(
        db_session, f"owner_{uuid.uuid4().hex[:6]}@forge.org", "Owner A"
    )
    user_b, token_b = await make_test_user(
        db_session, f"outsider_{uuid.uuid4().hex[:6]}@forge.org", "Outsider B"
    )
    mission, design = await make_test_mission(db_session, "CDF Restricted Mission")

    # Create CDF Room owned by User A
    room = CDFRoom(
        name="Private CDF Room",
        mission_id=mission.id,
        creator_id=user_a.id,
        status=CDFRoomStatus.ACTIVE,
    )
    db_session.add(room)
    await db_session.commit()
    await db_session.refresh(room)

    # Add User A as participant
    part = CDFRoomParticipant(
        room_id=room.id,
        user_id=user_a.id,
        role=CDFRole.LEAD_SYSTEMS_ARCHITECT,
    )
    db_session.add(part)
    await db_session.commit()

    # User B tries to generate with User A's room_id -> 403 Forbidden
    headers_b = {"Authorization": f"Bearer {token_b}"}
    forbidden_resp = await async_client.post(
        "/api/v1/dossiers/generate",
        json={"mission_id": mission.id, "room_id": room.id},
        headers=headers_b,
    )
    assert forbidden_resp.status_code == 403
    assert "not a registered participant" in forbidden_resp.json()["detail"]


# --- Rate Limiting Tests ---

async def test_dossier_rate_limiting_enforcement(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """
    Verifies that excessive requests breach sliding-window rate limit, returning HTTP 429.
    """
    reset_dossier_rate_limits()

    # Stub background generation task so test focuses purely on API
    # rate-limiting without database lock contention
    async def _noop_job(*args, **kwargs):
        pass

    monkeypatch.setattr("backend.app.api.v1.dossiers.run_dossier_generation_job", _noop_job)

    user, token = await make_test_user(
        db_session, f"ratelimit_{uuid.uuid4().hex[:6]}@forge.org", "Rate Limit Officer"
    )
    mission, design = await make_test_mission(db_session, "Rate Limit Mission")
    headers = {"Authorization": f"Bearer {token}"}

    # Consume allowed generate quota (10 requests per minute)
    for _ in range(settings.DOSSIER_RATE_LIMIT_GENERATE_PER_MINUTE):
        resp = await async_client.post(
            "/api/v1/dossiers/generate",
            json={"mission_id": mission.id, "design_id": design.id, "format": "JSON"},
            headers=headers,
        )
        assert resp.status_code == 202

    # 11th request must be rejected with 429 Too Many Requests
    blocked_resp = await async_client.post(
        "/api/v1/dossiers/generate",
        json={"mission_id": mission.id, "design_id": design.id, "format": "JSON"},
        headers=headers,
    )
    assert blocked_resp.status_code == 429
    assert "rate limit exceeded" in blocked_resp.json()["detail"]
    assert "Retry-After" in blocked_resp.headers
    reset_dossier_rate_limits()


# --- Retention Policy and Expiration Tests ---

async def test_dossier_retention_cleanup_and_expired_artifact(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Verifies that reports exceeding the 30-day retention window:
    1. Return HTTP 410 GONE on download attempts.
    2. Are pruned from storage and database via the cleanup endpoint.
    """
    user, token = await make_test_user(
        db_session, f"retention_{uuid.uuid4().hex[:6]}@forge.org", "Retention Officer"
    )
    mission, _ = await make_test_mission(db_session, "Retention Mission")
    headers = {"Authorization": f"Bearer {token}"}

    # Create backdated expired report (40 days old)
    expired_time = datetime.now(timezone.utc) - timedelta(days=40)
    rep_id = str(uuid.uuid4())
    pdf_p = get_dossier_file_path(rep_id, ".pdf")
    pdf_p.write_bytes(b"%PDF-1.4 Mock Expired Dossier Content")

    expired_report = DossierReport(
        id=rep_id,
        mission_id=mission.id,
        user_id=user.id,
        title="Old Mission Dossier",
        format="PDF",
        pdf_path=str(pdf_p),
        pdf_size_bytes=len(b"%PDF-1.4 Mock Expired Dossier Content"),
        pdf_sha256="abc" * 20,
        schema_version="1.0.0",
        snapshot_data={"mission": {"name": "Old"}},
        page_count=5,
        created_at=expired_time,
    )
    db_session.add(expired_report)
    await db_session.commit()

    # Attempt to download expired report -> HTTP 410 GONE
    dl_resp = await async_client.get(
        f"/api/v1/dossiers/{rep_id}/download?format=pdf", headers=headers
    )
    assert dl_resp.status_code == 410
    assert "expired" in dl_resp.json()["detail"]

    # Run administrative cleanup endpoint
    cleanup_resp = await async_client.post(
        "/api/v1/dossiers/cleanup?max_age_days=30", headers=headers
    )
    assert cleanup_resp.status_code == 200
    c_data = cleanup_resp.json()
    assert c_data["cleaned_reports_count"] >= 1
    assert c_data["reclaimed_bytes"] > 0
    assert not pdf_p.exists()


# --- Role-Aware Access Control Tests ---

async def test_role_aware_dossier_compilation(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Verifies that compiling a dossier as Science Officer vs Propulsion Officer
    correctly preserves compiler role and domain-filters FDIR findings.
    """
    lead_user, _ = await make_test_user(
        db_session, f"lead_{uuid.uuid4().hex[:6]}@forge.org", "Lead Architect"
    )
    sci_user, sci_token = await make_test_user(
        db_session, f"sci_{uuid.uuid4().hex[:6]}@forge.org", "Science Officer"
    )
    prop_user, prop_token = await make_test_user(
        db_session, f"prop_{uuid.uuid4().hex[:6]}@forge.org", "Propulsion Officer"
    )
    mission, design = await make_test_mission(db_session, "Role CDF Mission")

    # Create CDF Room
    room = CDFRoom(
        name="Role Governed CDF Room",
        mission_id=mission.id,
        creator_id=lead_user.id,
        status=CDFRoomStatus.ACTIVE,
    )
    db_session.add(room)
    await db_session.commit()
    await db_session.refresh(room)

    # Add participants
    p1 = CDFRoomParticipant(
        room_id=room.id, user_id=sci_user.id, role=CDFRole.SCIENCE_OFFICER
    )
    p2 = CDFRoomParticipant(
        room_id=room.id, user_id=prop_user.id, role=CDFRole.PROPULSION_POWER_OFFICER
    )
    db_session.add_all([p1, p2])

    # Add FDIR finding logs: one science, one propulsion warning
    f1 = FDIRFindingLog(
        mission_id=mission.id,
        room_id=room.id,
        rule_id="FDIR-SCI-01",
        rule_version="1.0.0",
        severity="WARNING",
        status="TRIGGERED",
        affected_subsystem="SCIENCE",
        input_evidence={"temp_c": 85.0},
        thresholds={"max_c": 75.0},
        confidence_status="DETERMINISTIC",
        explanation="Spectrometer sensor temperature elevated.",
        triage_guidance="Reduce duty cycle.",
        acknowledged=False,
    )
    f2 = FDIRFindingLog(
        mission_id=mission.id,
        room_id=room.id,
        rule_id="FDIR-PROP-01",
        rule_version="1.0.0",
        severity="WARNING",
        status="TRIGGERED",
        affected_subsystem="PROPULSION",
        input_evidence={"pressure_bar": 12.0},
        thresholds={"nominal_bar": 22.0},
        confidence_status="DETERMINISTIC",
        explanation="RCS propellant manifold pressure fluctuation.",
        triage_guidance="Switch to redundant line B.",
        acknowledged=False,
    )
    db_session.add_all([f1, f2])
    await db_session.commit()

    # Compile snapshot as Science Officer
    sci_snapshot = await compile_dossier_snapshot(
        db=db_session,
        mission_id=mission.id,
        user=sci_user,
        room_id=room.id,
    )
    assert sci_snapshot["compiled_by_user"]["role"] == "SCIENCE_OFFICER"
    assert sci_snapshot["fdir"]["role_access_filter"] == "SCIENCE_OFFICER"
    sci_subsystems = [f["affected_subsystem"] for f in sci_snapshot["fdir"]["findings"]]
    assert "SCIENCE" in sci_subsystems
    assert "PROPULSION" not in sci_subsystems

    # Compile snapshot as Propulsion Officer
    prop_snapshot = await compile_dossier_snapshot(
        db=db_session,
        mission_id=mission.id,
        user=prop_user,
        room_id=room.id,
    )
    assert prop_snapshot["compiled_by_user"]["role"] == "PROPULSION_POWER_OFFICER"
    assert prop_snapshot["fdir"]["role_access_filter"] == "PROPULSION_POWER_OFFICER"
    prop_subsystems = [f["affected_subsystem"] for f in prop_snapshot["fdir"]["findings"]]
    assert "PROPULSION" in prop_subsystems
    assert "SCIENCE" not in prop_subsystems


# --- Mission Existence and 404 Validation ---

async def test_nonexistent_mission_dossiers_returns_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Verifies that querying dossiers for a non-existent mission returns 404 Not Found.
    """
    _, token = await make_test_user(
        db_session, f"check404_{uuid.uuid4().hex[:6]}@forge.org", "Officer"
    )
    fake_id = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}

    resp = await async_client.get(f"/api/v1/dossiers/missions/{fake_id}", headers=headers)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


# --- Component Unverified Provenance Test ---

async def test_unverified_component_flagged_as_estimated(db_session: AsyncSession):
    """
    Verifies that a component with UNVERIFIED status has is_estimated = True in snapshot.
    """
    user, _ = await make_test_user(
        db_session, f"unver_{uuid.uuid4().hex[:6]}@forge.org", "Provenance Officer"
    )
    mission, _ = await make_test_mission(db_session, "Unverified Hardware Mission")

    # Add unverified component
    unver_comp = Component(
        name="Experimental Graphene Radiator",
        subsystem=SubsystemType.THERMAL,
        mass_kg=15.0,
        power_draw_w=0.0,
        cost_usd=2_000_000.0,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    db_session.add(unver_comp)
    await db_session.commit()
    await db_session.refresh(unver_comp)

    design = SpacecraftDesign(
        mission_id=mission.id,
        name="Experimental Design",
        version=1,
        component_ids=[unver_comp.id],
        propellant_mass_kg=100.0,
        dry_mass_kg=115.0,
        wet_mass_kg=215.0,
        delta_v_mps=1000.0,
        total_cost_usd=5_000_000.0,
        is_feasible=True,
    )
    db_session.add(design)
    await db_session.commit()
    await db_session.refresh(design)

    snapshot = await compile_dossier_snapshot(
        db=db_session,
        mission_id=mission.id,
        user=user,
        design_id=design.id,
    )
    c_entry = snapshot["components"][0]
    assert c_entry["verification_status"] == "UNVERIFIED"
    assert c_entry["is_estimated"] is True


# --- PDF Stress & Extreme Component Count Pagination ---

def test_extreme_component_count_pdf_pagination():
    """
    Stress tests PDF renderer with 150 components to guarantee pagination stays strictly at 5 pages.
    """
    snapshot = {
        "schema_version": "1.0.0",
        "software_version": "1.0.0",
        "snapshot_timestamp_utc": "2026-11-15T12:00:00Z",
        "canonical_hash_sha256": "f" * 64,
        "authoritative_disclaimer": "Mission Forge-generated concept dossier.",
        "title": "Mega Spacecraft Architecture Dossier",
        "mission": {
            "id": "m-mega",
            "name": "Mega Constellation Flagship",
            "target": "MARS",
            "mission_class": "FLAGSHIP",
            "budget_cap_usd": 5e9,
            "max_launch_mass_kg": 15000,
            "min_delta_v_mps": 5000,
            "min_power_margin_percent": 20,
        },
        "design": {
            "id": "d-mega",
            "name": "Mega Bus Rev 1",
            "version": 1,
            "dry_mass_kg": 5000,
            "wet_mass_kg": 12000,
            "propellant_mass_kg": 7000,
            "power_draw_w": 2500,
            "power_generation_w": 3500,
            "delta_v_mps": 5200,
            "total_cost_usd": 3.8e9,
            "is_feasible": True,
            "violations": [],
        },
        "swapc": {
            "mass_by_subsystem": {f"SUB_{i}": 150.0 for i in range(10)},
            "power_by_subsystem": {f"SUB_{i}": 100.0 for i in range(10)},
            "assumptions": [f"Assumption {i}" for i in range(5)],
        },
        "components": [
            {
                "name": f"Avionics Computer Rack Unit {i:03d}",
                "subsystem": "AVIONICS",
                "mass_kg": 12.5,
                "power_draw_w": 25.0,
                "cost_usd": 1500000.0,
                "trl": 9,
                "verification_status": "VERIFIED_AUTHORITATIVE",
            }
            for i in range(150)
        ],
        "trajectory": {"origin_body": "EARTH", "target_body": "MARS"},
        "telecommunications": {},
        "cdf": {"status": "STANDALONE_DESIGN"},
        "fdir": {"findings": []},
        "capcom": {"critical_tradeoffs": ["Thermal load at perigee"]},
    }

    pdf_bytes = render_dossier_pdf(snapshot)
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 5, f"Expected 5 pages under 150 components stress, got {len(doc)}"


# --- Download Artifact Size Limit Check ---

async def test_download_file_size_limit_rejection(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """
    Verifies that if an artifact exceeds MAX_DOSSIER_DOWNLOAD_BYTES, download returns 413.
    """
    user, token = await make_test_user(
        db_session, f"sizelimit_{uuid.uuid4().hex[:6]}@forge.org", "Size Officer"
    )
    mission, _ = await make_test_mission(db_session, "Size Mission")
    headers = {"Authorization": f"Bearer {token}"}

    rep_id = str(uuid.uuid4())
    pdf_p = get_dossier_file_path(rep_id, ".pdf")
    pdf_p.write_bytes(b"%PDF-1.4 Mock Artifact Data" * 100)

    report = DossierReport(
        id=rep_id,
        mission_id=mission.id,
        user_id=user.id,
        title="Oversized Dossier",
        format="PDF",
        pdf_path=str(pdf_p),
        pdf_size_bytes=len(pdf_p.read_bytes()),
        pdf_sha256="123" * 21,
        schema_version="1.0.0",
        snapshot_data={},
        page_count=5,
    )
    db_session.add(report)
    await db_session.commit()

    # Monkeypatch MAX_DOSSIER_DOWNLOAD_BYTES to a tiny value (50 bytes)
    monkeypatch.setattr(settings, "MAX_DOSSIER_DOWNLOAD_BYTES", 50)

    resp = await async_client.get(
        f"/api/v1/dossiers/{rep_id}/download?format=pdf", headers=headers
    )
    assert resp.status_code == 413
    assert "exceeds maximum allowable download limit" in resp.json()["detail"]

    # Clean up file
    if pdf_p.exists():
        pdf_p.unlink()
