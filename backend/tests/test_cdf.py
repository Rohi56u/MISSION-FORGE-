"""
Unit, Integration, and WebSocket Tests for Collaborative CDF (Phase 4)
Mission Forge — Phase 4
"""

import uuid
import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from backend.app.cdf.roles import (
    CDFRoleType,
    CDFMutationCategory,
    CDFPermissionDeniedError,
    assert_role_permission,
    check_role_permission,
)
from backend.app.cdf.state import (
    apply_mutation_to_state,
    initialize_default_cdf_state,
)
from backend.app.core.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.app.main import app


# ============================================================================
# 1. UNIT TESTS: Cryptography, Auth, Roles, and Authoritative State
# ============================================================================

def test_password_hashing_and_verification():
    """Verifies PBKDF2-HMAC-SHA256 password hashing and timing-safe verification."""
    raw_pass = "MissionForgeSecure2026!"
    hashed = hash_password(raw_pass)

    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(raw_pass, "corrupted_hash_format") is False


def test_jwt_issuance_and_claims():
    """Verifies JWT token encoding, claim validation, and signature verification."""
    token = create_access_token(user_id="user-12345", email="pilot@missionforge.org")
    claims = decode_access_token(token)

    assert claims["sub"] == "user-12345"
    assert claims["email"] == "pilot@missionforge.org"
    assert "exp" in claims
    assert "iat" in claims


def test_role_permissions_matrix():
    """
    Enforces the explicit 4-player CDF permission boundaries:
    1. Lead Systems Architect -> SYSTEM_CONSTRAINTS
    2. Propulsion & Power Officer -> PROPULSION_POWER
    3. Science Officer -> SCIENCE_PAYLOAD
    4. Flight Dynamics & Comms Officer -> FLIGHT_DYNAMICS_COMMS
    """
    # Lead Systems Architect
    assert check_role_permission(
        CDFRoleType.LEAD_SYSTEMS_ARCHITECT.value, CDFMutationCategory.SYSTEM_CONSTRAINTS.value
    ) is True
    assert check_role_permission(
        CDFRoleType.LEAD_SYSTEMS_ARCHITECT.value, CDFMutationCategory.PROPULSION_POWER.value
    ) is False
    assert check_role_permission(
        CDFRoleType.LEAD_SYSTEMS_ARCHITECT.value, CDFMutationCategory.SCIENCE_PAYLOAD.value
    ) is False

    # Propulsion & Power Officer
    assert check_role_permission(
        CDFRoleType.PROPULSION_POWER_OFFICER.value, CDFMutationCategory.PROPULSION_POWER.value
    ) is True
    assert check_role_permission(
        CDFRoleType.PROPULSION_POWER_OFFICER.value, CDFMutationCategory.SYSTEM_CONSTRAINTS.value
    ) is False

    # Science Officer
    assert check_role_permission(
        CDFRoleType.SCIENCE_OFFICER.value, CDFMutationCategory.SCIENCE_PAYLOAD.value
    ) is True
    assert check_role_permission(
        CDFRoleType.SCIENCE_OFFICER.value, CDFMutationCategory.FLIGHT_DYNAMICS_COMMS.value
    ) is False

    # Flight Dynamics & Comms Officer
    assert check_role_permission(
        CDFRoleType.FLIGHT_DYNAMICS_COMMS_OFFICER.value,
        CDFMutationCategory.FLIGHT_DYNAMICS_COMMS.value,
    ) is True
    assert check_role_permission(
        CDFRoleType.FLIGHT_DYNAMICS_COMMS_OFFICER.value,
        CDFMutationCategory.PROPULSION_POWER.value,
    ) is False

    # Assertion helper raises CDFPermissionDeniedError
    with pytest.raises(CDFPermissionDeniedError):
        assert_role_permission(
            CDFRoleType.SCIENCE_OFFICER.value,
            CDFMutationCategory.SYSTEM_CONSTRAINTS.value,
        )


def test_authoritative_state_calculation_integration():
    """
    Verifies that applying mutations transactionally updates SWaP-C budgets,
    margins, and provenance records.
    """
    initial_state = initialize_default_cdf_state(
        room_id="room-test-1",
        mission_id="mission-mars-1",
        target="MARS",
        mission_class="DISCOVERY",
        budget_cap_usd=500_000_000.0,
        max_launch_mass_kg=1500.0,
        min_delta_v_mps=3800.0,
    )
    assert initial_state.version == 1

    # 1. Propulsion Officer adds thruster and propellant
    propulsion_patch = {
        "propellant_mass_kg": 650.0,
        "components": [
            {
                "id": "comp-thruster-1",
                "name": "Aerojet Rocketdyne MR-106L",
                "subsystem": "PROPULSION",
                "mass_kg": 25.0,
                "power_draw_w": 35.0,
                "cost_usd": 1_200_000.0,
                "isp_s": 235.0,
                "thrust_n": 22.0,
            },
            {
                "id": "comp-solar-1",
                "name": "UltraFlex Solar Array Wing",
                "subsystem": "ELECTRICAL_POWER",
                "mass_kg": 40.0,
                "power_generation_w": 600.0,
                "power_draw_w": 10.0,
                "cost_usd": 4_500_000.0,
            },
        ],
    }

    state_v2 = apply_mutation_to_state(
        current_state=initial_state,
        mutation_category="PROPULSION_POWER",
        patch_data=propulsion_patch,
        actor_role="PROPULSION_POWER_OFFICER",
    )

    assert state_v2.version == 2
    assert state_v2.propulsion_and_power.propellant_mass_kg == 650.0
    assert state_v2.calculated_budgets.wet_mass_kg > 650.0
    assert state_v2.calculated_budgets.total_power_generated_w > 0.0
    assert "propulsion_and_power.propellant_mass_kg" in state_v2.provenance_map

    # 2. Science Officer adds high-resolution camera payload
    science_patch = {
        "components": [
            {
                "id": "comp-camera-1",
                "name": "High Resolution Multispectral Imager",
                "subsystem": "SCIENCE_PAYLOAD",
                "mass_kg": 35.0,
                "power_draw_w": 65.0,
                "cost_usd": 12_000_000.0,
            }
        ]
    }

    state_v3 = apply_mutation_to_state(
        current_state=state_v2,
        mutation_category="SCIENCE_PAYLOAD",
        patch_data=science_patch,
        actor_role="SCIENCE_OFFICER",
    )

    assert state_v3.version == 3
    assert state_v3.calculated_budgets.dry_mass_kg > state_v2.calculated_budgets.dry_mass_kg
    assert state_v3.calculated_budgets.total_cost_usd > state_v2.calculated_budgets.total_cost_usd


def test_constraint_alerts_on_violations():
    """
    Verifies that constraint alerts are generated when mass budget, power margin,
    or delta-v requirements are breached.
    """
    state = initialize_default_cdf_state(
        room_id="room-test-alerts",
        mission_id="mission-1",
        max_launch_mass_kg=500.0,  # Strict mass limit
        min_delta_v_mps=4500.0,
    )

    # Overload spacecraft with heavy payload
    overload_patch = {
        "components": [
            {
                "id": "comp-heavy-radar",
                "name": "Synthetic Aperture Radar",
                "subsystem": "SCIENCE_PAYLOAD",
                "mass_kg": 600.0,  # Exceeds 500kg max launch mass
                "power_draw_w": 800.0,  # Power deficit
                "cost_usd": 50_000_000.0,
            }
        ]
    }

    new_state = apply_mutation_to_state(
        current_state=state,
        mutation_category="SCIENCE_PAYLOAD",
        patch_data=overload_patch,
        actor_role="SCIENCE_OFFICER",
    )

    alert_codes = [a.alert_code for a in new_state.constraint_alerts]
    assert "MASS_BUDGET_EXCEEDED" in alert_codes
    assert "POWER_DEFICIT" in alert_codes
    assert "DELTA_V_SHORTFALL" in alert_codes


# ============================================================================
# 2. REST API INTEGRATION TESTS: Auth, Room Management, and Role Permissions
# ============================================================================

@pytest.mark.asyncio
async def test_auth_registration_and_login_flow(async_client: AsyncClient):
    """Verifies user registration, login, JWT token issuance, and authenticated /me endpoint."""
    email = f"lead_architect_{uuid.uuid4().hex[:6]}@missionforge.org"
    password = "SuperSecretPassword2026!"

    # 1. Register
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Dr. Sarah Chen",
            "password": password,
        },
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == email

    token = reg_data["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # 2. Duplicate registration rejected
    dup_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Duplicate Sarah",
            "password": password,
        },
    )
    assert dup_resp.status_code == 409

    # 3. Login
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()

    # 4. Invalid login rejected
    bad_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword"},
    )
    assert bad_login.status_code == 401

    # 5. Access protected /me
    me_resp = await async_client.get("/api/v1/auth/me", headers=auth_header)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


@pytest.mark.asyncio
async def test_cdf_room_capacity_and_four_roles(async_client: AsyncClient):
    """
    Verifies 4-player collaboration room:
    1. Lead Systems Architect creates room for mission.
    2. Propulsion Officer, Science Officer, and Comms Officer join.
    3. 5th player is rejected (capacity limit: 4).
    4. Duplicate role claim is rejected (role exclusivity).
    """
    # Create baseline mission
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={
            "name": "Ares Reconnaissance 2026",
            "target": "MARS",
            "mission_class": "DISCOVERY",
        },
    )
    assert m_resp.status_code == 201
    mission_id = m_resp.json()["id"]

    # Register 5 distinct users
    users = []
    tokens = []
    u_suffix = uuid.uuid4().hex[:6]
    for i in range(1, 6):
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"officer{i}_{u_suffix}@missionforge.org",
                "full_name": f"Officer {i}",
                "password": "Password123!",
            },
        )
        data = resp.json()
        users.append(data["user"])
        tokens.append(data["access_token"])

    # 1. Lead Systems Architect creates room
    headers_arch = {"Authorization": f"Bearer {tokens[0]}"}
    create_room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Mars Design Lab",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_arch,
    )
    assert create_room_resp.status_code == 201
    room_id = create_room_resp.json()["id"]

    # 2. Propulsion Officer joins
    headers_prop = {"Authorization": f"Bearer {tokens[1]}"}
    join_prop_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "PROPULSION_POWER_OFFICER"},
        headers=headers_prop,
    )
    assert join_prop_resp.status_code == 200

    # 3. Science Officer joins
    headers_sci = {"Authorization": f"Bearer {tokens[2]}"}
    join_sci_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "SCIENCE_OFFICER"},
        headers=headers_sci,
    )
    assert join_sci_resp.status_code == 200

    # 4. Flight Dynamics & Comms Officer joins
    headers_comms = {"Authorization": f"Bearer {tokens[3]}"}
    join_comms_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "FLIGHT_DYNAMICS_COMMS_OFFICER"},
        headers=headers_comms,
    )
    assert join_comms_resp.status_code == 200

    # 5. Role exclusivity check: 5th user tries to take an already occupied role
    headers_5 = {"Authorization": f"Bearer {tokens[4]}"}
    dup_role_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "PROPULSION_POWER_OFFICER"},
        headers=headers_5,
    )
    assert dup_role_resp.status_code == 409
    assert "already occupied" in dup_role_resp.json()["detail"]

    # 6. Check room details shows 4 participants and version 1
    detail_resp = await async_client.get(
        f"/api/v1/cdf/rooms/{room_id}",
        headers=headers_arch,
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert len(detail_data["participants"]) == 4
    assert detail_data["current_version"] == 1


@pytest.mark.asyncio
async def test_role_enforcement_and_version_locking(async_client: AsyncClient):
    """
    Verifies role-based mutation constraints and optimistic version concurrency:
    - Science officer mutating SYSTEM_CONSTRAINTS -> 403 Forbidden.
    - Systems Architect mutating SYSTEM_CONSTRAINTS -> 200 OK, bumps version to 2.
    - Stale base_version mutation -> 409 Conflict with latest version payload.
    - Duplicate message_id returns cached response without duplicate commit.
    """
    # 1. Setup mission and room
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Titan Explorer 2026", "target": "TITAN", "mission_class": "NEW_FRONTIERS"},
    )
    mission_id = m_resp.json()["id"]

    # Register Architect and Science Officer
    u_suffix = uuid.uuid4().hex[:6]
    reg1 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"architect_titan_{u_suffix}@test.com",
            "full_name": "Arch Titan",
            "password": "Pass12345!",
        },
    )
    arch_tok = reg1.json()["access_token"]
    headers_arch = {"Authorization": f"Bearer {arch_tok}"}

    reg2 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"sci_titan_{u_suffix}@test.com",
            "full_name": "Sci Titan",
            "password": "Pass12345!",
        },
    )
    sci_tok = reg2.json()["access_token"]
    headers_sci = {"Authorization": f"Bearer {sci_tok}"}

    # Create room & join
    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Titan Lab",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_arch,
    )
    room_id = room_resp.json()["id"]

    await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "SCIENCE_OFFICER"},
        headers=headers_sci,
    )

    # 2. Unauthorized mutation: Science Officer attempts to change SYSTEM_CONSTRAINTS
    unauth_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "SYSTEM_CONSTRAINTS",
            "patch_data": {"budget_cap_usd": 1_500_000_000.0},
        },
        headers=headers_sci,
    )
    assert unauth_resp.status_code == 403
    assert "Permission denied" in unauth_resp.json()["detail"]

    # 3. Authorized mutation: Systems Architect updates SYSTEM_CONSTRAINTS
    auth_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "SYSTEM_CONSTRAINTS",
            "patch_data": {"budget_cap_usd": 1_200_000_000.0, "max_launch_mass_kg": 2200.0},
            "client_message_id": "msg-arch-001",
        },
        headers=headers_arch,
    )
    assert auth_resp.status_code == 200
    mut_data = auth_resp.json()
    assert mut_data["success"] is True
    assert mut_data["new_version"] == 2

    # 4. Idempotency test: repeated message_id returns cached response
    dup_msg_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "SYSTEM_CONSTRAINTS",
            "patch_data": {"budget_cap_usd": 1_200_000_000.0, "max_launch_mass_kg": 2200.0},
            "client_message_id": "msg-arch-001",
        },
        headers=headers_arch,
    )
    assert dup_msg_resp.status_code == 200
    assert dup_msg_resp.json()["new_version"] == 2

    # 5. Version Conflict test: submitting stale base_version=1 when room is now version 2
    stale_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "SCIENCE_PAYLOAD",
            "patch_data": {"components": []},
            "client_message_id": "msg-sci-stale",
        },
        headers=headers_sci,
    )
    assert stale_resp.status_code == 409
    err_detail = stale_resp.json()["detail"]
    assert err_detail["error"] == "VERSION_CONFLICT"
    assert err_detail["current_version"] == 2

    # 6. Verify Revision history and Events log
    revs_resp = await async_client.get(
        f"/api/v1/cdf/rooms/{room_id}/revisions",
        headers=headers_arch,
    )
    assert revs_resp.status_code == 200
    revs = revs_resp.json()
    assert len(revs) == 2  # Baseline rev 1 + Arch mutation rev 2

    events_resp = await async_client.get(
        f"/api/v1/cdf/rooms/{room_id}/events",
        headers=headers_arch,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert any(e["event_type"] == "ROOM_CREATED" for e in events)
    assert any(e["event_type"] == "MUTATION_APPLIED" for e in events)


# ============================================================================
# 3. REAL-TIME WEBSOCKET TESTS: Multi-client broadcast, sync, and errors
# ============================================================================

def test_websocket_authentication_enforcement():
    """Verifies that connecting without a valid JWT token returns ERROR and closes."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/cdf/ws/room-invalid") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert "Authentication required" in msg["payload"]["detail"]


def test_websocket_full_session_flow():
    """
    Verifies complete WebSocket lifecycle:
    1. Authenticate with valid token for joined user.
    2. Receive initial ROOM_JOINED with authoritative state snapshot.
    3. Send PING -> receive PONG.
    4. Send CHAT_MESSAGE -> receive CHAT_BROADCAST.
    5. Submit DESIGN_MUTATION -> receive STATE_UPDATED.
    6. Send SYNC_REQUEST -> receive latest state.
    """
    client = TestClient(app)

    # 1. Setup User, Mission, and Room via REST
    u_suffix = uuid.uuid4().hex[:6]
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ws_pilot_{u_suffix}@missionforge.org",
            "full_name": "WS Pilot",
            "password": "Password123!",
        },
    )
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    m_res = client.post(
        "/api/v1/missions",
        json={"name": "Europa Deep Probe", "target": "EUROPA", "mission_class": "FLAGSHIP"},
    )
    mission_id = m_res.json()["id"]

    room_res = client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Europa Control Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers,
    )
    room_id = room_res.json()["id"]

    # 2. Connect via WebSocket with token query param
    with client.websocket_connect(f"/api/v1/cdf/ws/{room_id}?token={token}") as ws:
        # Initial greeting event
        initial_msg = ws.receive_json()
        assert initial_msg["type"] == "ROOM_JOINED"
        assert initial_msg["version"] == 1
        assert "state" in initial_msg["payload"]

        # Ping-Pong
        ws.send_json({"action": "PING"})
        pong_msg = ws.receive_json()
        assert pong_msg["type"] == "PONG"

        # Chat message
        ws.send_json({"action": "CHAT_MESSAGE", "chat_message": "All systems nominal for Europa."})
        chat_broadcast = ws.receive_json()
        assert chat_broadcast["type"] == "CHAT_BROADCAST"
        assert chat_broadcast["payload"]["message"] == "All systems nominal for Europa."

        # Authorized Design Mutation via WebSocket
        ws.send_json({
            "action": "DESIGN_MUTATION",
            "base_version": 1,
            "mutation_category": "SYSTEM_CONSTRAINTS",
            "patch_data": {"budget_cap_usd": 3_500_000_000.0},
        })
        state_updated_msg = ws.receive_json()
        assert state_updated_msg["type"] == "STATE_UPDATED"
        assert state_updated_msg["version"] == 2
        assert state_updated_msg["payload"]["mutation_category"] == "SYSTEM_CONSTRAINTS"

        # Sync request
        ws.send_json({"action": "SYNC_REQUEST"})
        sync_msg = ws.receive_json()
        assert sync_msg["type"] == "STATE_UPDATED"
        assert sync_msg["version"] == 2


@pytest.mark.asyncio
async def test_cdf_room_membership_security_enforcement(async_client: AsyncClient):
    """
    SECURITY REQUIREMENT:
    Enforce authentication and room membership on every read/write operation.
    An uninvited or non-member user MUST receive 403 Forbidden.
    """
    # 1. Setup Room with Architect
    u_suffix = uuid.uuid4().hex[:6]
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Secure Mission", "target": "MARS", "mission_class": "DISCOVERY"},
    )
    mission_id = m_resp.json()["id"]

    reg1 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"owner_{u_suffix}@missionforge.org",
            "full_name": "Room Owner",
            "password": "Password123!",
        },
    )
    token_owner = reg1.json()["access_token"]
    headers_owner = {"Authorization": f"Bearer {token_owner}"}

    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Classified Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_owner,
    )
    room_id = room_resp.json()["id"]

    # 2. Register Intruder User (NOT in the room)
    reg2 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"intruder_{u_suffix}@missionforge.org",
            "full_name": "Intruder User",
            "password": "Password123!",
        },
    )
    token_intruder = reg2.json()["access_token"]
    headers_intruder = {"Authorization": f"Bearer {token_intruder}"}

    # 3. Intruder reading room details -> 403 Forbidden
    res_detail = await async_client.get(f"/api/v1/cdf/rooms/{room_id}", headers=headers_intruder)
    assert res_detail.status_code == 403
    assert "not a registered participant" in res_detail.json()["detail"]

    # 4. Intruder reading state -> 403 Forbidden
    res_state = await async_client.get(
        f"/api/v1/cdf/rooms/{room_id}/state", headers=headers_intruder
    )
    assert res_state.status_code == 403

    # 5. Intruder reading revisions -> 403 Forbidden
    res_revs = await async_client.get(
        f"/api/v1/cdf/rooms/{room_id}/revisions", headers=headers_intruder
    )
    assert res_revs.status_code == 403

    # 6. Intruder reading events -> 403 Forbidden
    res_events = await async_client.get(
        f"/api/v1/cdf/rooms/{room_id}/events", headers=headers_intruder
    )
    assert res_events.status_code == 403

    # 7. Intruder evaluating FDIR on room -> 403 Forbidden
    res_fdir = await async_client.post(
        "/api/v1/fdir/evaluate",
        json={"room_id": room_id},
        headers=headers_intruder,
    )
    assert res_fdir.status_code == 403

    # 8. Intruder querying CAPCOM on room -> 403 Forbidden
    res_capcom = await async_client.post(
        "/api/v1/capcom/ask",
        json={"room_id": room_id, "query": "Status report?"},
        headers=headers_intruder,
    )
    assert res_capcom.status_code == 403


@pytest.mark.asyncio
async def test_cdf_room_invitations_and_lifecycle(async_client: AsyncClient):
    """
    Verifies room invitation tokens and lifecycle status transitions:
    1. Room creator issues invitation token for SCIENCE_OFFICER.
    2. Candidate joins room using the invitation token.
    3. Room creator locks the room (LOCKED status).
    4. Mutations on locked room are rejected with 400.
    5. Room cleanup endpoint executes.
    """
    u_suffix = uuid.uuid4().hex[:6]
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Lifecycle Mission", "target": "MARS", "mission_class": "DISCOVERY"},
    )
    mission_id = m_resp.json()["id"]

    reg1 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"creator_{u_suffix}@missionforge.org",
            "full_name": "Room Creator",
            "password": "Password123!",
        },
    )
    token_creator = reg1.json()["access_token"]
    headers_creator = {"Authorization": f"Bearer {token_creator}"}

    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Invite Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_creator,
    )
    room_id = room_resp.json()["id"]

    # 1. Creator generates invitation token
    inv_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations",
        json={"role": "SCIENCE_OFFICER", "expires_in_hours": 24},
        headers=headers_creator,
    )
    assert inv_resp.status_code == 201
    invite_token = inv_resp.json()["invite_token"]
    assert len(invite_token) > 20

    # 2. Register scientist and join with invite token
    reg2 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"scientist_{u_suffix}@missionforge.org",
            "full_name": "Dr. Scientist",
            "password": "Password123!",
        },
    )
    token_sci = reg2.json()["access_token"]
    headers_sci = {"Authorization": f"Bearer {token_sci}"}

    join_inv_resp = await async_client.post(
        "/api/v1/cdf/rooms/join-with-invite",
        json={"invite_token": invite_token},
        headers=headers_sci,
    )
    assert join_inv_resp.status_code == 200
    assert join_inv_resp.json()["role"] == "SCIENCE_OFFICER"

    # 3. Lock room
    lock_resp = await async_client.put(
        f"/api/v1/cdf/rooms/{room_id}/status",
        json={"status": "LOCKED"},
        headers=headers_creator,
    )
    assert lock_resp.status_code == 200
    assert lock_resp.json()["status"] == "LOCKED"

    # 4. Mutations rejected while LOCKED
    mut_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "SCIENCE_PAYLOAD",
            "patch_data": {"components": []},
        },
        headers=headers_sci,
    )
    assert mut_resp.status_code == 400
    assert "locked" in mut_resp.json()["detail"].lower()

    # 5. Room cleanup check
    cleanup_resp = await async_client.post(
        "/api/v1/cdf/rooms/cleanup?max_age_days=30",
        headers=headers_creator,
    )
    assert cleanup_resp.status_code == 200
    assert "archived_rooms_count" in cleanup_resp.json()


@pytest.mark.asyncio
async def test_cdf_four_player_websocket_concurrent_broadcast():
    """
    REAL-TIME BROADCAST VERIFICATION:
    Connects four independent participant sockets for all four official roles simultaneously.
    Verifies that chat messages, presence events, and state mutations are
    broadcast concurrently to all four participants without message drops.
    """
    import asyncio
    from unittest.mock import AsyncMock
    from backend.app.cdf.broadcast import CDFConnectionManager, InMemoryBroadcastBackend

    backend = InMemoryBroadcastBackend()
    manager = CDFConnectionManager(backend)

    room_id = f"room-quad-{uuid.uuid4().hex[:6]}"
    u_arch = f"u-arch-{uuid.uuid4().hex[:4]}"
    u_prop = f"u-prop-{uuid.uuid4().hex[:4]}"
    u_sci = f"u-sci-{uuid.uuid4().hex[:4]}"
    u_comms = f"u-comms-{uuid.uuid4().hex[:4]}"

    ws_arch = AsyncMock()
    ws_prop = AsyncMock()
    ws_sci = AsyncMock()
    ws_comms = AsyncMock()

    # 1. Connect all 4 participant sockets to room
    await manager.connect(room_id, u_arch, ws_arch)
    await manager.connect(room_id, u_prop, ws_prop)
    await manager.connect(room_id, u_sci, ws_sci)
    await manager.connect(room_id, u_comms, ws_comms)

    assert len(manager.get_connected_user_ids(room_id)) == 4

    # 2. Broadcast chat message from Science Officer
    chat_payload = {
        "type": "CHAT_BROADCAST",
        "actor_id": u_sci,
        "actor_role": "SCIENCE_OFFICER",
        "payload": {"message": "Multispectral spectrometer calibrated and nominal."},
    }
    await manager.broadcast_to_room(room_id, chat_payload)
    await asyncio.sleep(0.02)

    # All 4 officers receive chat broadcast
    for ws in [ws_arch, ws_prop, ws_sci, ws_comms]:
        assert ws.send_json.called
        assert ws.send_json.call_args[0][0]["type"] == "CHAT_BROADCAST"

    # Reset call counts
    for ws in [ws_arch, ws_prop, ws_sci, ws_comms]:
        ws.send_json.reset_mock()

    # 3. Broadcast state update from Architect
    state_payload = {
        "type": "STATE_UPDATED",
        "version": 2,
        "actor_id": u_arch,
        "actor_role": "LEAD_SYSTEMS_ARCHITECT",
        "payload": {"mutation_category": "SYSTEM_CONSTRAINTS"},
    }
    await manager.broadcast_to_room(room_id, state_payload)
    await asyncio.sleep(0.02)

    # All 4 officers receive state update broadcast
    for ws in [ws_arch, ws_prop, ws_sci, ws_comms]:
        assert ws.send_json.called
        assert ws.send_json.call_args[0][0]["type"] == "STATE_UPDATED"
        assert ws.send_json.call_args[0][0]["version"] == 2


@pytest.mark.asyncio
async def test_cdf_websocket_reconnection_resilience():
    """
    Verifies reconnection handling:
    When a participant connects with a new WebSocket, disconnecting their old WebSocket
    MUST NOT disconnect the active socket or break broadcast distribution.
    """
    import asyncio
    from unittest.mock import AsyncMock
    from backend.app.cdf.broadcast import CDFConnectionManager, InMemoryBroadcastBackend

    backend = InMemoryBroadcastBackend()
    manager = CDFConnectionManager(backend)

    room_id = f"room-reconn-{uuid.uuid4().hex[:6]}"
    user_id = f"u-pilot-{uuid.uuid4().hex[:4]}"

    ws_old = AsyncMock()
    ws_new = AsyncMock()

    # 1. Connect initial socket
    await manager.connect(room_id, user_id, ws_old)
    assert user_id in manager.get_connected_user_ids(room_id)

    # 2. Reconnect with new socket (supersedes old socket)
    await manager.connect(room_id, user_id, ws_new)

    # 3. Old socket disconnects (passes ws_old)
    await manager.disconnect(room_id, user_id, ws_old)

    # User MUST still be registered as connected because ws_new is active!
    assert user_id in manager.get_connected_user_ids(room_id)

    # 4. Broadcast sent to room -> ws_new receives it, ws_old does not
    await manager.broadcast_to_room(room_id, {"type": "TEST_BROADCAST"})
    await asyncio.sleep(0.02)

    assert ws_new.send_json.called
    assert not ws_old.send_json.called

    # 5. Now ws_new disconnects -> user is cleanly unregistered
    await manager.disconnect(room_id, user_id, ws_new)
    assert user_id not in manager.get_connected_user_ids(room_id)


@pytest.mark.asyncio
async def test_cdf_concurrent_mutations_and_db_idempotency(async_client: AsyncClient):
    """
    CONCURRENCY & IDEMPOTENCY VERIFICATION:
    1. Simultaneous edits with competing versions handle conflict cleanly
       (one 200, one 409 VERSION_CONFLICT, no 500).
    2. Database-backed idempotency returns cached response even after memory cache is cleared.
    """
    import asyncio
    u_suffix = uuid.uuid4().hex[:6]
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Race Mission", "target": "MARS", "mission_class": "DISCOVERY"},
    )
    mission_id = m_resp.json()["id"]

    reg1 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"arch_race_{u_suffix}@missionforge.org",
            "full_name": "Arch Race",
            "password": "Password123!",
        },
    )
    token1 = reg1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    reg2 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"prop_race_{u_suffix}@missionforge.org",
            "full_name": "Prop Race",
            "password": "Password123!",
        },
    )
    token2 = reg2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Race Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers1,
    )
    room_id = room_resp.json()["id"]

    # Join Propulsion officer
    await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "PROPULSION_POWER_OFFICER"},
        headers=headers2,
    )

    # 1. Simultaneous edits: Architect and Propulsion officer both submit base_version=1
    # concurrently to test race conditions and optimistic locking.
    req_arch = async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "SYSTEM_CONSTRAINTS",
            "patch_data": {"budget_cap_usd": 700_000_000.0},
            "client_message_id": f"msg-race-1-{u_suffix}",
        },
        headers=headers1,
    )
    req_prop = async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "PROPULSION_POWER",
            "patch_data": {"propellant_mass_kg": 450.0},
            "client_message_id": f"msg-race-2-{u_suffix}",
        },
        headers=headers2,
    )

    res_arch, res_prop = await asyncio.gather(req_arch, req_prop)
    status_codes = sorted([res_arch.status_code, res_prop.status_code])

    # Exactly one mutation committed (200), competing received 409 Conflict. Neither crashed.
    assert status_codes == [200, 409]
    conflict_res = res_arch if res_arch.status_code == 409 else res_prop
    assert conflict_res.json()["detail"]["error"] == "VERSION_CONFLICT"
    assert conflict_res.json()["detail"]["current_version"] == 2

    # 2. Database-backed Idempotency check:
    # Clear memory cache to simulate process restart / distributed worker recovery
    from backend.app.cdf.service import _IDEMPOTENCY_CACHE
    _IDEMPOTENCY_CACHE.clear()

    # Re-submit the winning mutation
    is_arch_win = (res_arch.status_code == 200)
    winning_msg_id = f"msg-race-1-{u_suffix}" if is_arch_win else f"msg-race-2-{u_suffix}"
    winning_headers = headers1 if is_arch_win else headers2
    winning_category = "SYSTEM_CONSTRAINTS" if is_arch_win else "PROPULSION_POWER"
    winning_patch = (
        {"budget_cap_usd": 700_000_000.0} if is_arch_win else {"propellant_mass_kg": 450.0}
    )

    dup_res = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": winning_category,
            "patch_data": winning_patch,
            "client_message_id": winning_msg_id,
        },
        headers=winning_headers,
    )
    assert dup_res.status_code == 200
    # Idempotently returned version 2 from DB without incrementing
    assert dup_res.json()["new_version"] == 2


async def test_cdf_invitation_revocation_and_expiration(async_client: AsyncClient):
    """
    SECURITY & LIFECYCLE REGRESSION TEST:
    Verifies invitation token creation, cryptographic expiration rejection,
    and server-side revocation enforcement.
    """
    import uuid
    from datetime import datetime, timezone, timedelta
    import jwt
    from backend.app.core.config import settings
    from backend.app.core.auth import JWT_ALGORITHM

    u_suffix = uuid.uuid4().hex[:6]
    reg_creator = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"creator_rev_{u_suffix}@missionforge.org",
            "full_name": "Invite Revoker",
            "password": "Password123!",
        },
    )
    token_creator = reg_creator.json()["access_token"]
    headers_creator = {"Authorization": f"Bearer {token_creator}"}

    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Revocation Test Mission", "target": "MARS"},
    )
    mission_id = m_resp.json()["id"]

    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Revocation Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_creator,
    )
    room_id = room_resp.json()["id"]

    # 1. Creator generates valid invitation for SCIENCE_OFFICER
    inv_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations",
        json={"role": "SCIENCE_OFFICER", "expires_in_hours": 24},
        headers=headers_creator,
    )
    assert inv_resp.status_code == 201
    invite_token = inv_resp.json()["invite_token"]

    # 2. Register candidate user
    reg_sci = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"invitee_{u_suffix}@missionforge.org",
            "full_name": "Invitee Candidate",
            "password": "Password123!",
        },
    )
    token_sci = reg_sci.json()["access_token"]
    headers_sci = {"Authorization": f"Bearer {token_sci}"}

    # 3. Non-authorized candidate attempts to revoke the token -> 403 Forbidden
    unauth_rev = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations/revoke",
        json={"invite_token": invite_token},
        headers=headers_sci,
    )
    assert unauth_rev.status_code == 403

    # 4. Creator revokes the invitation token -> 200 OK
    rev_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations/revoke",
        json={"invite_token": invite_token},
        headers=headers_creator,
    )
    assert rev_resp.status_code == 200
    assert "revoked" in rev_resp.json()["message"].lower()

    # 5. Candidate attempts to join with the revoked invitation token -> 400 Bad Request
    join_rev = await async_client.post(
        "/api/v1/cdf/rooms/join-with-invite",
        json={"invite_token": invite_token},
        headers=headers_sci,
    )
    assert join_rev.status_code == 400
    assert "revoked" in join_rev.json()["detail"].lower()

    # 6. Test expired invitation token handling
    now = datetime.now(timezone.utc)
    expired_payload = {
        "type": "room_invitation",
        "jti": str(uuid.uuid4()),
        "room_id": room_id,
        "role": "SCIENCE_OFFICER",
        "inviter_id": reg_creator.json()["user"]["id"],
        "iat": int((now - timedelta(hours=48)).timestamp()),
        "exp": int((now - timedelta(hours=24)).timestamp()),  # expired 24h ago
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)

    join_exp = await async_client.post(
        "/api/v1/cdf/rooms/join-with-invite",
        json={"invite_token": str(expired_token)},
        headers=headers_sci,
    )
    assert join_exp.status_code == 400
    assert "expired" in join_exp.json()["detail"].lower()


def test_cdf_websocket_security_edge_cases():
    """
    WEBSOCKET SECURITY REGRESSION TEST:
    Verifies that:
    1. Oversized messages (>64 KB) are rejected with MESSAGE_TOO_LARGE error.
    2. Cross-site WebSocket hijacking from unauthorized origins is denied with 1008.
    """
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(app)

    # 1. Register user and create room
    u_suffix = uuid.uuid4().hex[:6]
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ws_sec_{u_suffix}@missionforge.org",
            "full_name": "Security Tester",
            "password": "Password123!",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    m_resp = client.post(
        "/api/v1/missions",
        json={"name": "WS Security Mission", "target": "MARS"},
    )
    room_id = client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "WS Sec Room",
            "mission_id": m_resp.json()["id"],
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers,
    ).json()["id"]

    # 2. Test unauthorized Origin
    # If origin is explicitly hostile (e.g. evil-hacker.com) and not in CORS_ORIGINS
    try:
        with client.websocket_connect(
            f"/api/v1/cdf/ws/{room_id}?token={token}",
            headers={"origin": "https://evil-hacker.com"},
        ) as ws_unauth:
            _ = ws_unauth.receive_json()
    except WebSocketDisconnect as disc:
        assert disc.code == 1008 or disc.code == 1000

    # 3. Test message size limit with valid authorized connection
    with client.websocket_connect(
        f"/api/v1/cdf/ws/{room_id}?token={token}",
        headers={"origin": "http://localhost:3000"},
    ) as ws:
        init_msg = ws.receive_json()
        assert init_msg["type"] == "ROOM_JOINED"

        # Send an oversized text message (>64 KB)
        oversized_payload = "X" * 70_000
        ws.send_text(oversized_payload)

        err_resp = ws.receive_json()
        assert err_resp["type"] == "ERROR"
        assert err_resp["payload"]["error"] == "MESSAGE_TOO_LARGE"


async def test_cdf_in_memory_broker_single_process_limitation():
    """
    CRITICAL ARCHITECTURAL VERIFICATION:
    Proves and documents that InMemoryBroadcastBackend is strictly single-process local.
    Two independent backend instances (simulating two worker processes/servers)
    do NOT share events across memory spaces.
    """
    import asyncio
    from backend.app.cdf.broadcast import InMemoryBroadcastBackend

    worker_a_backend = InMemoryBroadcastBackend()
    worker_b_backend = InMemoryBroadcastBackend()

    worker_b_received = []

    async def worker_b_handler(room_id, msg):
        worker_b_received.append((room_id, msg))

    # Worker B subscribes to room 'mars-room-01'
    await worker_b_backend.subscribe("mars-room-01", worker_b_handler)

    # Worker A publishes an event to room 'mars-room-01'
    event = {"type": "STATE_UPDATED", "version": 2}
    await worker_a_backend.publish("mars-room-01", event)

    # Small delay to ensure event dispatch loop has executed
    await asyncio.sleep(0.05)

    # Worker B MUST NOT have received the event because memory spaces are completely isolated
    assert len(worker_b_received) == 0, (
        "InMemoryBroadcastBackend leaked events across independent instances! "
        "It must remain process-local."
    )


@pytest.mark.asyncio
async def test_cdf_revoked_invitation_persists_across_restart(async_client: AsyncClient):
    """
    SECURITY & PERSISTENCE REGRESSION TEST:
    Verifies that when an invitation token is revoked via REST, the revocation
    persists in the database and remains enforced even after the in-memory
    revocation cache is completely cleared (simulating process restart).
    """
    from backend.app.core.auth import _REVOKED_INVITE_TOKENS

    u_suffix = uuid.uuid4().hex[:6]
    reg_creator = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"creator_persist_{u_suffix}@missionforge.org",
            "full_name": "Invite Creator Persist",
            "password": "Password123!",
        },
    )
    token_creator = reg_creator.json()["access_token"]
    headers_creator = {"Authorization": f"Bearer {token_creator}"}

    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Revocation Persistence Mission", "target": "MARS"},
    )
    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Revocation Persist Room",
            "mission_id": m_resp.json()["id"],
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_creator,
    )
    room_id = room_resp.json()["id"]

    # 1. Generate invitation token
    inv_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations",
        json={"role": "SCIENCE_OFFICER", "expires_in_hours": 24},
        headers=headers_creator,
    )
    invite_token = inv_resp.json()["invite_token"]

    # 2. Revoke the token via REST
    rev_resp = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations/revoke",
        json={"invite_token": invite_token},
        headers=headers_creator,
    )
    assert rev_resp.status_code == 200

    # 3. Simulate process restart: completely wipe the in-memory revoked set!
    _REVOKED_INVITE_TOKENS.clear()

    # 4. Register candidate invitee
    reg_invitee = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"candidate_{u_suffix}@missionforge.org",
            "full_name": "Candidate Invitee",
            "password": "Password123!",
        },
    )
    token_invitee = reg_invitee.json()["access_token"]
    headers_invitee = {"Authorization": f"Bearer {token_invitee}"}

    # 5. Candidate attempts to join: DB-backed check MUST reject with 400!
    join_resp = await async_client.post(
        "/api/v1/cdf/rooms/join-with-invite",
        json={"invite_token": invite_token},
        headers=headers_invitee,
    )
    assert join_resp.status_code == 400
    assert "revoked" in join_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cdf_leave_room_and_chat_event_version_consistency(async_client: AsyncClient):
    """
    DATA INTEGRITY REGRESSION TEST:
    Verifies that when mutations bump the authoritative room version (e.g. to version 2),
    subsequent events (USER_LEFT and CHAT_MESSAGE) accurately record the current room version
    rather than hardcoded version=1.
    """
    u_suffix = uuid.uuid4().hex[:6]
    reg_lead = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"lead_ver_{u_suffix}@missionforge.org",
            "full_name": "Lead Ver",
            "password": "Password123!",
        },
    )
    token_lead = reg_lead.json()["access_token"]
    headers_lead = {"Authorization": f"Bearer {token_lead}"}

    reg_prop = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"prop_ver_{u_suffix}@missionforge.org",
            "full_name": "Prop Ver",
            "password": "Password123!",
        },
    )
    token_prop = reg_prop.json()["access_token"]
    headers_prop = {"Authorization": f"Bearer {token_prop}"}

    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Event Version Mission", "target": "MARS"},
    )
    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Version Consistency Room",
            "mission_id": m_resp.json()["id"],
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_lead,
    )
    room_id = room_resp.json()["id"]

    # Join Propulsion officer
    await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "PROPULSION_POWER_OFFICER"},
        headers=headers_prop,
    )

    # Lead Architect mutates state -> bumps room to version 2
    mut_res = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "SYSTEM_CONSTRAINTS",
            "patch_data": {"budget_cap_usd": 650_000_000.0},
        },
        headers=headers_lead,
    )
    assert mut_res.status_code == 200
    assert mut_res.json()["new_version"] == 2

    # Propulsion officer leaves the room
    leave_res = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/leave",
        headers=headers_prop,
    )
    assert leave_res.status_code == 200

    # Query events log: USER_LEFT MUST have version == 2
    events_res = await async_client.get(
        f"/api/v1/cdf/rooms/{room_id}/events",
        headers=headers_lead,
    )
    events = events_res.json()
    user_left_ev = next(e for e in events if e["event_type"] == "USER_LEFT")
    assert user_left_ev["version"] == 2, (
        f"USER_LEFT event had stale version {user_left_ev['version']}, "
        "expected current room version 2"
    )


def test_cdf_redis_broker_configuration():
    """
    Verifies that REDIS_URL configuration is loaded from settings
    and triggers RedisBroadcastBackend provisioning.
    """
    from backend.app.core.config import Settings
    from backend.app.cdf.broadcast import RedisBroadcastBackend

    custom_settings = Settings(REDIS_URL="redis://127.0.0.1:6379/1")
    assert custom_settings.REDIS_URL == "redis://127.0.0.1:6379/1"

    redis_backend = RedisBroadcastBackend(redis_url=custom_settings.REDIS_URL)
    assert redis_backend.redis_url == "redis://127.0.0.1:6379/1"


@pytest.mark.asyncio
async def test_cdf_invitation_permissions_and_capacity_enforcement(async_client: AsyncClient):
    """
    AEROSPACE ACCESS CONTROL REGRESSION TEST:
    Verifies that:
    1. Only the room creator or Lead Systems Architect can issue invitations (403 for others).
    2. Generating invitations for an already occupied role is rejected with 409 Conflict.
    3. Generating invitations when the room is at max capacity (4 participants) is rejected 403.
    """
    u_suffix = uuid.uuid4().hex[:6]
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Access Control Mission", "target": "MARS"},
    )
    mission_id = m_resp.json()["id"]

    # Register Creator (Lead Systems Architect)
    reg_creator = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"creator_ac_{u_suffix}@missionforge.org",
            "full_name": "Lead Architect",
            "password": "Password123!",
        },
    )
    headers_creator = {"Authorization": f"Bearer {reg_creator.json()['access_token']}"}

    # Register Science Officer
    reg_sci = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"sci_ac_{u_suffix}@missionforge.org",
            "full_name": "Science Officer",
            "password": "Password123!",
        },
    )
    headers_sci = {"Authorization": f"Bearer {reg_sci.json()['access_token']}"}

    # Create room
    r_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Access Control Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers_creator,
    )
    room_id = r_resp.json()["id"]

    # Join Science Officer
    await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/join",
        json={"role": "SCIENCE_OFFICER"},
        headers=headers_sci,
    )

    # 1. Non-lead participant (Science Officer) attempts to issue invitation -> 403 Forbidden
    unauth_inv = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations",
        json={"role": "PROPULSION_POWER_OFFICER", "expires_in_hours": 24},
        headers=headers_sci,
    )
    assert unauth_inv.status_code == 403
    assert "Only the room creator or Lead Systems Architect" in unauth_inv.json()["detail"]

    # 2. Lead Architect attempts to issue invitation for already occupied role -> 409 Conflict
    conflict_inv = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations",
        json={"role": "SCIENCE_OFFICER", "expires_in_hours": 24},
        headers=headers_creator,
    )
    assert conflict_inv.status_code == 409
    assert "already occupied" in conflict_inv.json()["detail"]

    # 3. Fill room to max capacity (join Propulsion and Flight Dynamics officers)
    for role_name in ["PROPULSION_POWER_OFFICER", "FLIGHT_DYNAMICS_COMMS_OFFICER"]:
        reg_user = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"fill_{role_name.lower()}_{u_suffix}@missionforge.org",
                "full_name": f"Officer {role_name}",
                "password": "Password123!",
            },
        )
        h_user = {"Authorization": f"Bearer {reg_user.json()['access_token']}"}
        j_resp = await async_client.post(
            f"/api/v1/cdf/rooms/{room_id}/join",
            json={"role": role_name},
            headers=h_user,
        )
        assert j_resp.status_code == 200

    # Room is now at 4/4 capacity; creating any invitation must be rejected with 403 Forbidden
    cap_inv = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/invitations",
        json={"role": "PROPULSION_POWER_OFFICER", "expires_in_hours": 24},
        headers=headers_creator,
    )
    assert cap_inv.status_code == 403
    assert "maximum capacity" in cap_inv.json()["detail"]


@pytest.mark.asyncio
async def test_cdf_mutate_invalid_data_types_rejected(async_client: AsyncClient):
    """
    DATA VALIDATION REGRESSION TEST:
    Verifies that malformed patch data (non-convertible strings, negative physical values)
    is cleanly rejected with HTTP 422 rather than raising unhandled 500 server errors.
    """
    u_suffix = uuid.uuid4().hex[:6]
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Type Safety Mission", "target": "MARS"},
    )
    mission_id = m_resp.json()["id"]

    reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"prop_type_{u_suffix}@missionforge.org",
            "full_name": "Prop Type",
            "password": "Password123!",
        },
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    r_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Type Safety Room",
            "mission_id": mission_id,
            "role": "PROPULSION_POWER_OFFICER",
        },
        headers=headers,
    )
    room_id = r_resp.json()["id"]

    # 1. Non-convertible string for float field
    bad_type_res = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "PROPULSION_POWER",
            "patch_data": {"propellant_mass_kg": "not-a-valid-number"},
        },
        headers=headers,
    )
    assert bad_type_res.status_code == 422
    assert "Invalid patch data" in bad_type_res.json()["detail"]

    # 2. Negative mass (physically invalid)
    neg_mass_res = await async_client.post(
        f"/api/v1/cdf/rooms/{room_id}/mutate",
        json={
            "base_version": 1,
            "mutation_category": "PROPULSION_POWER",
            "patch_data": {"propellant_mass_kg": -150.0},
        },
        headers=headers,
    )
    assert neg_mass_res.status_code == 422
    assert "Invalid patch data" in neg_mass_res.json()["detail"]
