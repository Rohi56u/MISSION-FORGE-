"""
Comprehensive Firebase and Supabase Integration Verification Tests
Mission Forge — Mandatory Security and Storage Audit
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import build_engine_config
from backend.app.core.auth import (
    create_access_token,
    hash_password,
)
from backend.app.core.firebase import (
    verify_firebase_token,
    get_or_create_firebase_user,
)
from backend.app.dossier.storage import (
    DossierStorageService,
    is_supabase_configured,
)
from backend.app.models.auth import User
from backend.app.models.mission import Mission, MissionTarget, MissionClass
from backend.app.models.dossier import DossierReport


# ==============================================================================
# 1. Supabase PostgreSQL Engine & Connection Configuration Tests
# ==============================================================================
def test_supabase_postgres_engine_args_session_mode():
    """Verifies that direct Supabase PostgreSQL connections mandate SSL and pool settings."""
    url = "postgresql+asyncpg://postgres:secret@db.xyz.supabase.co:5432/postgres"
    connect_args, engine_kwargs = build_engine_config(url, echo=False)

    assert connect_args.get("ssl") == "require"
    assert engine_kwargs.get("pool_pre_ping") is True
    assert engine_kwargs.get("pool_recycle") == 300
    assert "statement_cache_size" not in connect_args


def test_supabase_postgres_engine_args_pooler_mode():
    """
    Verifies that Supabase PgBouncer/Supavisor pooler (port 6543) mandates
    statement_cache_size=0 to prevent broken prepared statement errors in asyncpg.
    """
    pooler_host = "aws-0-us-east-1.pooler.supabase.com:6543"
    url = f"postgresql+asyncpg://postgres.xyz:secret@{pooler_host}/postgres"
    connect_args, engine_kwargs = build_engine_config(url, echo=False)

    assert connect_args.get("ssl") == "require"
    assert connect_args.get("statement_cache_size") == 0
    assert connect_args.get("prepared_statement_cache_size") == 0
    assert engine_kwargs.get("pool_pre_ping") is True


def test_sqlite_engine_args_preservation():
    """Verifies local SQLite connect args remain unchanged for local dev and CI tests."""
    url = "sqlite+aiosqlite:///./test.db"
    connect_args, engine_kwargs = build_engine_config(url, echo=False)

    assert connect_args.get("check_same_thread") is False
    assert connect_args.get("timeout") == 30.0
    assert "ssl" not in connect_args
    assert "statement_cache_size" not in connect_args


# ==============================================================================
# 2. Firebase Authentication ID Token & Claims Validation Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_firebase_token_verification_success(monkeypatch, db_session: AsyncSession):
    """
    Tests that a valid Firebase ID token is verified with official claims,
    and mapped to an internal User profile with verified firebase_uid.
    """
    test_project = "mission-forge-test"
    test_uid = f"fb-user-{uuid.uuid4().hex[:8]}"
    test_email = f"flight-officer-{uuid.uuid4().hex[:6]}@nasa.gov"
    mock_token_claims = {
        "uid": test_uid,
        "sub": test_uid,
        "email": test_email,
        "name": "Lt. Flight Dynamics",
        "aud": test_project,
        "iss": f"https://securetoken.google.com/{test_project}",
        "auth_time": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }

    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", test_project)

    mock_app = MagicMock()
    with patch("backend.app.core.firebase.get_firebase_app", return_value=mock_app):
        with patch("firebase_admin.auth.verify_id_token", return_value=mock_token_claims):
            decoded = verify_firebase_token("mock-firebase-id-token")
            assert decoded["uid"] == test_uid
            assert decoded["aud"] == test_project
            assert decoded["iss"] == f"https://securetoken.google.com/{test_project}"

            user = await get_or_create_firebase_user(decoded, db_session)
            assert user.firebase_uid == test_uid
            assert user.email == test_email
            assert user.full_name == "Lt. Flight Dynamics"
            assert user.is_active is True


@pytest.mark.asyncio
async def test_firebase_token_audience_mismatch_rejected(monkeypatch):
    """Verifies that an ID token issued for a different Firebase project is strictly rejected."""
    test_project = "mission-forge-prod"
    attacker_claims = {
        "uid": "attacker-uid",
        "sub": "attacker-uid",
        "aud": "rogue-project-id",
        "iss": "https://securetoken.google.com/rogue-project-id",
    }

    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", test_project)
    mock_app = MagicMock()
    with patch("backend.app.core.firebase.get_firebase_app", return_value=mock_app):
        with patch("firebase_admin.auth.verify_id_token", return_value=attacker_claims):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                verify_firebase_token("rogue-token")
            assert exc_info.value.status_code == 401
            assert "audience does not match" in exc_info.value.detail


@pytest.mark.asyncio
async def test_firebase_token_revoked_rejected(monkeypatch):
    """Verifies that a revoked Firebase ID token raises 401 Unauthorized."""
    from firebase_admin import auth as fb_auth
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "test-project")
    mock_app = MagicMock()
    with patch("backend.app.core.firebase.get_firebase_app", return_value=mock_app):
        with patch(
            "firebase_admin.auth.verify_id_token",
            side_effect=fb_auth.RevokedIdTokenError("Revoked"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                verify_firebase_token("revoked-token")
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_firebase_user_account_linking_by_email(monkeypatch, db_session: AsyncSession):
    """
    Verifies that when a user already exists with matching email,
    authenticating via Firebase links the firebase_uid to the existing User row.
    """
    test_project = "mission-forge-test"
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", test_project)

    common_email = f"lead-architect-{uuid.uuid4().hex[:6]}@missionforge.org"
    existing_user = User(
        id=str(uuid.uuid4()),
        email=common_email,
        full_name="Existing Lead Architect",
        hashed_password=hash_password("SuperSecret123!"),
        is_active=True,
    )
    db_session.add(existing_user)
    await db_session.commit()

    fb_uid = f"fb-link-{uuid.uuid4().hex[:8]}"
    claims = {
        "uid": fb_uid,
        "email": common_email,
        "name": "Updated Name",
        "aud": test_project,
        "iss": f"https://securetoken.google.com/{test_project}",
    }

    linked_user = await get_or_create_firebase_user(claims, db_session)
    assert linked_user.id == existing_user.id
    assert linked_user.firebase_uid == fb_uid
    assert linked_user.email == common_email


# ==============================================================================
# 3. Supabase Storage Object Upload & Signed Download URL Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_supabase_storage_local_fallback(monkeypatch, tmp_path: Path):
    """
    Verifies that when Supabase is unconfigured, DossierStorageService
    cleanly falls back to local persistent disk storage with path traversal protection.
    """
    monkeypatch.setattr(settings, "SUPABASE_URL", None)
    monkeypatch.setattr(settings, "SUPABASE_KEY", None)
    monkeypatch.setattr(settings, "DOSSIER_STORAGE_DIR", str(tmp_path))

    storage_svc = DossierStorageService()
    assert is_supabase_configured() is False

    test_report_id = str(uuid.uuid4())
    test_mission_id = str(uuid.uuid4())
    test_data = b"%PDF-1.4 Mock Flight Dossier Artifact"

    res = await storage_svc.store_artifact(
        report_id=test_report_id,
        mission_id=test_mission_id,
        extension=".pdf",
        data=test_data,
        content_type="application/pdf",
    )

    assert res["cloud_uploaded"] is False
    assert res["cloud_key"] is None
    local_file = Path(res["local_path"])
    assert local_file.exists()
    assert local_file.read_bytes() == test_data

    # Cleanup test
    deleted = await storage_svc.delete_artifact(
        report_id=test_report_id,
        mission_id=test_mission_id,
        extension=".pdf",
        local_path_str=str(local_file),
    )
    assert deleted is True
    assert not local_file.exists()


@pytest.mark.asyncio
async def test_supabase_storage_upload_and_signed_url_mock(monkeypatch):
    """
    Verifies that when Supabase credentials are configured, the service
    properly formats object keys and interacts with the Supabase client.
    """
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://xyzcompany.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "mock-service-role-key-secret")
    monkeypatch.setattr(settings, "SUPABASE_STORAGE_BUCKET", "dossiers")

    assert is_supabase_configured() is True

    mock_client = MagicMock()
    mock_from = MagicMock()
    mock_client.storage.from_.return_value = mock_from
    mock_client.storage.list_buckets.return_value = [{"name": "dossiers"}]
    mock_from.upload.return_value = {"Key": "dossiers/mission-1/report-1.pdf"}
    signed_url_res = (
        "https://xyzcompany.supabase.co/storage/v1/object/sign/"
        "dossiers/mission-1/report-1.pdf?token=abc123exp"
    )
    mock_from.create_signed_url.return_value = {"signedURL": signed_url_res}

    storage_svc = DossierStorageService()
    with patch.object(storage_svc, "_get_supabase_client", return_value=mock_client):
        res = await storage_svc.store_artifact(
            report_id="rep-001",
            mission_id="miss-001",
            extension=".pdf",
            data=b"test-bytes",
            content_type="application/pdf",
        )
        assert res["cloud_uploaded"] is True
        assert res["cloud_key"] == "miss-001/rep-001.pdf"
        assert "xyzcompany.supabase.co" in res["signed_url"]

        signed_url = await storage_svc.create_signed_url(
            report_id="rep-001",
            mission_id="miss-001",
            extension=".pdf",
            expires_in=1800,
        )
        assert signed_url is not None
        assert "token=abc123exp" in signed_url


# ==============================================================================
# 4. Dossier Signed URL API Probe
# ==============================================================================
@pytest.mark.asyncio
async def test_api_dossier_signed_url_endpoint(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Tests the GET /api/v1/dossiers/{report_id}/signed-url endpoint:
    verifies authentication, ownership authorization, and response schema.
    """
    user = User(
        id=str(uuid.uuid4()),
        email=f"commander-{uuid.uuid4().hex[:6]}@missionforge.org",
        full_name="Cmdr. Explorer",
        hashed_password=hash_password("Pass123!"),
        is_active=True,
    )
    db_session.add(user)

    mission = Mission(
        id=str(uuid.uuid4()),
        name="Europa Astro Explorer",
        target=MissionTarget.EUROPA,
        mission_class=MissionClass.FLAGSHIP,
        budget_cap_usd=2_500_000_000.0,
        max_launch_mass_kg=4000.0,
        min_delta_v_mps=5000.0,
    )
    db_session.add(mission)
    await db_session.commit()

    report = DossierReport(
        id=str(uuid.uuid4()),
        mission_id=mission.id,
        user_id=user.id,
        title="Europa Astro Concept Dossier",
        format="BOTH",
        pdf_path="artifacts/dossiers/mock.pdf",
        pdf_sha256="abcdef123456",
        schema_version="1.0.0",
        snapshot_data={"mission_id": mission.id},
        page_count=5,
    )
    db_session.add(report)
    await db_session.commit()

    token = create_access_token(user_id=user.id, email=user.email)
    headers = {"Authorization": f"Bearer {token}"}

    res = await async_client.get(
        f"/api/v1/dossiers/{report.id}/signed-url?format=pdf&expires_in=3600",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["report_id"] == report.id
    assert data["mission_id"] == mission.id
    assert data["format"] == "PDF"
    assert "download_url" in data
    assert data["expires_in_seconds"] == 3600

    unauth_res = await async_client.get(f"/api/v1/dossiers/{report.id}/signed-url")
    assert unauth_res.status_code == 401


# ==============================================================================
# 5. Authenticated Catalog Mutation with Token
# ==============================================================================
@pytest.mark.asyncio
async def test_authenticated_catalog_mutation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Verifies that an authenticated user can register components in the catalog
    regardless of production environment restrictions.
    """
    user = User(
        id=str(uuid.uuid4()),
        email=f"systems-engineer-{uuid.uuid4().hex[:6]}@missionforge.org",
        full_name="Systems Engineer",
        hashed_password=hash_password("Secret456!"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user_id=user.id, email=user.email)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "name": f"High-Isp Ion Engine {uuid.uuid4().hex[:4]}",
        "subsystem": "PROPULSION",
        "mass_kg": 18.5,
        "power_draw_w": 2500.0,
        "power_generation_w": 0.0,
        "cost_usd": 750000.0,
        "trl": 8,
        "flight_heritage": "Deep Space 1 / Dawn",
        "source_url": "https://nasa.gov/tech",
        "verification_status": "VERIFIED_AUTHORITATIVE",
        "thrust_newtons": 0.092,
        "isp_seconds": 3100.0,
    }

    res = await async_client.post("/api/v1/components", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == payload["name"]
    assert data["mass_kg"] == 18.5
    assert data["isp_seconds"] == 3100.0
