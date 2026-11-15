"""
Concurrent Design Facility (CDF) REST & WebSocket API Endpoints
Mission Forge — Phase 4
"""

from datetime import datetime, timezone, timedelta
import asyncio
import json
import logging
from typing import Dict, List, Optional
from pydantic import ValidationError
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.cdf.broadcast import cdf_connection_manager
from backend.app.cdf.service import (
    CDFVersionConflictError,
    apply_room_mutation,
    cleanup_inactive_rooms,
    create_cdf_room,
    get_latest_room_state,
    join_cdf_room,
    join_cdf_room_with_invite,
    leave_cdf_room,
    update_room_lifecycle_status,
)
from backend.app.core.auth import (
    create_room_invite_token,
    revoke_invite_token,
    get_current_user,
    get_current_user_from_token,
)
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, get_db
from backend.app.models.auth import User
from backend.app.models.cdf import (
    CDFDesignRevision,
    CDFEvent,
    CDFRole,
    CDFRoom,
    CDFRoomParticipant,
    CDFRoomStatus,
)
from backend.app.schemas.cdf import (
    CDFClientActionType,
    CDFServerMessageType,
    CDFWebSocketInbound,
    EventResponse,
    JoinRoomRequest,
    JoinWithInviteRequest,
    ParticipantResponse,
    RevisionResponse,
    RoomCleanupResponse,
    RoomCreateRequest,
    RoomDetailResponse,
    RoomInviteCreateRequest,
    RoomInviteResponse,
    RoomInviteRevokeRequest,
    RoomResponse,
    RoomStatusUpdateRequest,
    StateMutationRequest,
    StateMutationResponse,
)

logger = logging.getLogger(__name__)


async def assert_room_membership(
    db: AsyncSession, room_id: str, user_id: str
) -> CDFRoomParticipant:
    """Verifies that the user is an authorized participant of the room."""
    stmt = select(CDFRoomParticipant).where(
        and_(CDFRoomParticipant.room_id == room_id, CDFRoomParticipant.user_id == user_id)
    )
    res = await db.execute(stmt)
    participant = res.scalar_one_or_none()
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a registered participant of this CDF room.",
        )
    return participant

router = APIRouter(prefix="/cdf", tags=["Concurrent Design Facility (CDF)"])


@router.post(
    "/rooms",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Collaborative CDF Room",
)
async def create_room(
    payload: RoomCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Creates a new CDF collaboration room and assigns the creator to the chosen role."""
    room = await create_cdf_room(
        db=db,
        name=payload.name,
        mission_id=payload.mission_id,
        creator_id=current_user.id,
        creator_role=payload.role,
    )
    return RoomResponse(
        id=room.id,
        name=room.name,
        mission_id=room.mission_id,
        status=room.status,
        max_participants=room.max_participants,
        current_version=room.current_version,
        participant_count=1,
        created_at=room.created_at,
    )


@router.get(
    "/rooms",
    response_model=List[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="List Active CDF Rooms",
)
async def list_rooms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[RoomResponse]:
    """Lists all active CDF collaboration rooms."""
    stmt = select(CDFRoom).order_by(CDFRoom.created_at.desc())
    res = await db.execute(stmt)
    rooms = res.scalars().all()

    output: List[RoomResponse] = []
    for r in rooms:
        stmt_count = select(CDFRoomParticipant).where(CDFRoomParticipant.room_id == r.id)
        res_count = await db.execute(stmt_count)
        p_count = len(res_count.scalars().all())
        output.append(
            RoomResponse(
                id=r.id,
                name=r.name,
                mission_id=r.mission_id,
                status=r.status,
                max_participants=r.max_participants,
                current_version=r.current_version,
                participant_count=p_count,
                created_at=r.created_at,
            )
        )
    return output


@router.get(
    "/rooms/{room_id}",
    response_model=RoomDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get CDF Room Details & Authoritative State",
)
async def get_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomDetailResponse:
    """Retrieves full room details, participant roster, and latest design state snapshot."""
    stmt = select(CDFRoom).where(CDFRoom.id == room_id)
    res = await db.execute(stmt)
    room = res.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CDF room not found.")

    # Enforce room membership on read
    await assert_room_membership(db, room_id, current_user.id)

    stmt_p = (
        select(CDFRoomParticipant, User)
        .join(User, CDFRoomParticipant.user_id == User.id)
        .where(CDFRoomParticipant.room_id == room_id)
    )
    res_p = await db.execute(stmt_p)
    participant_rows = res_p.all()

    participants_resp: List[ParticipantResponse] = []
    for part, user in participant_rows:
        participants_resp.append(
            ParticipantResponse(
                id=part.id,
                user_id=user.id,
                full_name=user.full_name,
                email=user.email,
                role=part.role,
                is_connected=part.is_connected,
                joined_at=part.joined_at,
                last_seen_at=part.last_seen_at,
            )
        )

    state = await get_latest_room_state(db, room_id)

    return RoomDetailResponse(
        id=room.id,
        name=room.name,
        mission_id=room.mission_id,
        status=room.status,
        max_participants=room.max_participants,
        current_version=room.current_version,
        participants=participants_resp,
        state=state,
        created_at=room.created_at,
    )


@router.post(
    "/rooms/{room_id}/join",
    response_model=ParticipantResponse,
    status_code=status.HTTP_200_OK,
    summary="Join CDF Room with Role",
)
async def join_room(
    room_id: str,
    payload: JoinRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParticipantResponse:
    """Joins an active CDF room assuming an authorized role."""
    participant = await join_cdf_room(
        db=db,
        room_id=room_id,
        user_id=current_user.id,
        role=payload.role,
    )
    return ParticipantResponse(
        id=participant.id,
        user_id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=participant.role,
        is_connected=participant.is_connected,
        joined_at=participant.joined_at,
        last_seen_at=participant.last_seen_at,
    )


@router.post(
    "/rooms/{room_id}/leave",
    status_code=status.HTTP_200_OK,
    summary="Leave CDF Room",
)
async def leave_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Leaves a CDF collaboration room."""
    ok = await leave_cdf_room(db=db, room_id=room_id, user_id=current_user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a registered participant in this room.",
        )
    return {"message": "Successfully left room."}


@router.get(
    "/rooms/{room_id}/state",
    status_code=status.HTTP_200_OK,
    summary="Get Authoritative Room Design State",
)
async def get_state(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves current authoritative state and calculated SWaP-C budgets."""
    await assert_room_membership(db, room_id, current_user.id)
    return await get_latest_room_state(db, room_id)


@router.get(
    "/rooms/{room_id}/revisions",
    response_model=List[RevisionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Room Design Revision History",
)
async def list_revisions(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[RevisionResponse]:
    """Retrieves full versioned revision history for audit trail and rollback analysis."""
    await assert_room_membership(db, room_id, current_user.id)
    stmt = (
        select(CDFDesignRevision)
        .where(CDFDesignRevision.room_id == room_id)
        .order_by(CDFDesignRevision.version.asc())
    )
    res = await db.execute(stmt)
    return [RevisionResponse.model_validate(r) for r in res.scalars().all()]


@router.get(
    "/rooms/{room_id}/events",
    response_model=List[EventResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Room Event Log",
)
async def list_events(
    room_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EventResponse]:
    """Retrieves room audit log and event stream."""
    await assert_room_membership(db, room_id, current_user.id)
    stmt = (
        select(CDFEvent)
        .where(CDFEvent.room_id == room_id)
        .order_by(CDFEvent.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return [EventResponse.model_validate(e) for e in res.scalars().all()]


@router.post(
    "/rooms/{room_id}/invitations",
    response_model=RoomInviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create CDF Room Role Invitation Token",
)
async def create_room_invitation(
    room_id: str,
    payload: RoomInviteCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomInviteResponse:
    """Generates a secure, cryptographically signed invitation token for an assigned role."""
    participant = await assert_room_membership(db, room_id, current_user.id)
    stmt = select(CDFRoom).where(CDFRoom.id == room_id)
    res = await db.execute(stmt)
    room = res.scalar_one_or_none()
    if not room or room.status != CDFRoomStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate invitations for inactive or locked rooms.",
        )

    is_creator = (room.creator_id == current_user.id)
    is_lead = (participant.role == CDFRole.LEAD_SYSTEMS_ARCHITECT)
    if not is_creator and not is_lead:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the room creator or Lead Systems Architect can create room invitations.",
        )

    # Check capacity limit
    stmt_p = select(CDFRoomParticipant).where(CDFRoomParticipant.room_id == room_id)
    res_p = await db.execute(stmt_p)
    existing_participants = res_p.scalars().all()
    if len(existing_participants) >= room.max_participants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Room is at maximum capacity ({room.max_participants} participants).",
        )

    # Check if role is already occupied
    for p in existing_participants:
        if p.role == payload.role:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Role '{payload.role.value}' is already occupied in this room.",
            )

    token = create_room_invite_token(
        room_id=room_id,
        role=payload.role.value,
        inviter_id=current_user.id,
        expires_in_hours=payload.expires_in_hours,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours)
    return RoomInviteResponse(
        invite_token=token,
        room_id=room_id,
        role=payload.role,
        expires_at=expires_at,
    )


@router.post(
    "/rooms/{room_id}/invitations/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke CDF Room Role Invitation Token",
)
async def revoke_room_invitation(
    room_id: str,
    payload: RoomInviteRevokeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Revokes an invitation token. Restricted to room creator or Lead Systems Architect."""
    stmt = select(CDFRoom).where(CDFRoom.id == room_id)
    res = await db.execute(stmt)
    room = res.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CDF room not found.")

    stmt_p = select(CDFRoomParticipant).where(
        and_(CDFRoomParticipant.room_id == room_id, CDFRoomParticipant.user_id == current_user.id)
    )
    res_p = await db.execute(stmt_p)
    participant = res_p.scalar_one_or_none()

    is_creator = (room.creator_id == current_user.id)
    is_lead = (participant is not None and participant.role == CDFRole.LEAD_SYSTEMS_ARCHITECT)
    if not is_creator and not is_lead:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the room creator or Lead Systems Architect can revoke invitations.",
        )

    import jwt
    from backend.app.core.auth import JWT_ALGORITHM
    try:
        t_payload = jwt.decode(
            payload.invite_token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        if t_payload.get("room_id") != room_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token does not belong to this room.",
            )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation token.",
        )

    revoke_invite_token(payload.invite_token)

    # Persist revocation audit event for durable token revocation across process restarts
    jti_val = t_payload.get("jti")
    rev_event = CDFEvent(
        room_id=room_id,
        event_type="TOKEN_REVOKED",
        version=room.current_version,
        actor_id=current_user.id,
        actor_role=participant.role.value if participant else "LEAD_SYSTEMS_ARCHITECT",
        payload={
            "jti": jti_val,
            "token": payload.invite_token,
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    db.add(rev_event)
    await db.commit()

    return {"message": "Invitation token successfully revoked."}


@router.post(
    "/rooms/join-with-invite",
    response_model=ParticipantResponse,
    status_code=status.HTTP_200_OK,
    summary="Join CDF Room with Invitation Token",
)
async def join_room_with_invite(
    payload: JoinWithInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParticipantResponse:
    """Joins a CDF collaboration room using a cryptographically signed invitation token."""
    participant = await join_cdf_room_with_invite(
        db=db,
        invite_token=payload.invite_token,
        user_id=current_user.id,
    )
    return ParticipantResponse(
        id=participant.id,
        user_id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=participant.role,
        is_connected=participant.is_connected,
        joined_at=participant.joined_at,
        last_seen_at=participant.last_seen_at,
    )


@router.put(
    "/rooms/{room_id}/status",
    response_model=RoomResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Room Lifecycle Status",
)
async def update_room_status(
    room_id: str,
    payload: RoomStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Updates the room lifecycle status (ACTIVE, LOCKED, ARCHIVED)."""
    room = await update_room_lifecycle_status(
        db=db,
        room_id=room_id,
        user_id=current_user.id,
        new_status=payload.status,
    )
    stmt_count = select(CDFRoomParticipant).where(CDFRoomParticipant.room_id == room.id)
    res_count = await db.execute(stmt_count)
    p_count = len(res_count.scalars().all())
    return RoomResponse(
        id=room.id,
        name=room.name,
        mission_id=room.mission_id,
        status=room.status,
        max_participants=room.max_participants,
        current_version=room.current_version,
        participant_count=p_count,
        created_at=room.created_at,
    )


@router.post(
    "/rooms/cleanup",
    response_model=RoomCleanupResponse,
    status_code=status.HTTP_200_OK,
    summary="Clean Up Inactive CDF Rooms",
)
async def cleanup_rooms(
    max_age_days: int = Query(14, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomCleanupResponse:
    """Archives stale or abandoned rooms and frees inactive subscriptions."""
    cleaned = await cleanup_inactive_rooms(db=db, max_age_days=max_age_days)
    return RoomCleanupResponse(
        archived_rooms_count=len(cleaned),
        cleaned_room_ids=cleaned,
    )


@router.post(
    "/rooms/{room_id}/mutate",
    response_model=StateMutationResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Atomic Design Mutation",
)
async def mutate_room_state(
    room_id: str,
    payload: StateMutationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StateMutationResponse:
    """
    Submits an atomic mutation to the authoritative design state.
    Enforces role permissions, optimistic version locking, duplicate protection,
    and recalculates all engineering budgets and alerts.
    """
    try:
        return await apply_room_mutation(
            db=db,
            room_id=room_id,
            user_id=current_user.id,
            base_version=payload.base_version,
            mutation_category=payload.mutation_category,
            patch_data=payload.patch_data,
            client_message_id=payload.client_message_id,
        )
    except CDFVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "VERSION_CONFLICT",
                "message": str(exc),
                "current_version": exc.current_version,
                "current_state": exc.current_state.model_dump(),
            },
        )
    except (ValueError, TypeError, ValidationError) as val_exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid patch data: {val_exc}",
        )


# --- Real-Time WebSocket Endpoint ---

MAX_WS_MESSAGE_SIZE = 65_536  # 64 KB message size limit


@router.websocket("/ws/{room_id}")
async def cdf_websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: Optional[str] = Query(None),
) -> None:
    """
    Real-time bidirectional WebSocket endpoint for CDF participants.
    Validates authentication token, verifies room membership, synchronizes state,
    and broadcasts design updates and alerts with sub-second latency.
    """
    await websocket.accept()

    # 0. Validate Origin Header against CORS Configuration
    origin = websocket.headers.get("origin")
    if origin and settings.CORS_ORIGINS:
        allowed_origins = [o.rstrip("/") for o in settings.CORS_ORIGINS]
        norm_origin = origin.rstrip("/")
        if "*" not in allowed_origins and norm_origin not in allowed_origins:
            logger.warning("Rejected WebSocket connection from unauthorized origin: %s", origin)
            await websocket.send_json({
                "type": CDFServerMessageType.ERROR.value,
                "payload": {"detail": f"Origin '{origin}' not permitted by CORS policy."},
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # 1. Authenticate Token
    if not token:
        auth_hdr = websocket.headers.get("authorization")
        if auth_hdr and auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()

    if not token:
        await websocket.send_json({
            "type": CDFServerMessageType.ERROR.value,
            "payload": {"detail": "Authentication required. Supply valid JWT token."},
        })
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with AsyncSessionLocal() as session:
        try:
            current_user = await get_current_user_from_token(token, session)
        except Exception as exc:
            await websocket.send_json({
                "type": CDFServerMessageType.ERROR.value,
                "payload": {"detail": f"Authentication failed: {exc}"},
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # 2. Verify Room Membership
        stmt_p = select(CDFRoomParticipant).where(
            and_(
                CDFRoomParticipant.room_id == room_id,
                CDFRoomParticipant.user_id == current_user.id,
            )
        )
        res_p = await session.execute(stmt_p)
        participant = res_p.scalar_one_or_none()
        if not participant:
            await websocket.send_json({
                "type": CDFServerMessageType.ERROR.value,
                "payload": {
                    "detail": "You must join this room via REST before connecting via WebSocket."
                },
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        participant_role = participant.role.value
        participant.is_connected = True
        participant.last_seen_at = datetime.now(timezone.utc)
        await session.commit()

        # Fetch latest authoritative state for initial synchronization
        try:
            current_state = await get_latest_room_state(session, room_id)
        except Exception:
            current_state = None

    # Register active WebSocket connection
    await cdf_connection_manager.connect(room_id, current_user.id, websocket)

    # Send initial ROOM_JOINED with full authoritative state
    await websocket.send_json({
        "type": CDFServerMessageType.ROOM_JOINED.value,
        "version": current_state.version if current_state else 1,
        "actor_id": current_user.id,
        "actor_role": participant_role,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "room_id": room_id,
            "user_id": current_user.id,
            "role": participant_role,
            "state": current_state.model_dump() if current_state else {},
        },
    })

    try:
        while True:
            try:
                raw_text = await asyncio.wait_for(websocket.receive_text(), timeout=120.0)
            except asyncio.TimeoutError:
                logger.info(
                    "WebSocket connection timed out due to inactivity for user %s in room %s",
                    current_user.id,
                    room_id,
                )
                try:
                    await websocket.send_json({
                        "type": CDFServerMessageType.ERROR.value,
                        "payload": {"detail": "Connection timed out due to inactivity."},
                    })
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                except Exception:
                    pass
                break

            # Enforce message size limit (64 KB)
            if len(raw_text) > MAX_WS_MESSAGE_SIZE:
                await websocket.send_json({
                    "type": CDFServerMessageType.ERROR.value,
                    "payload": {
                        "error": "MESSAGE_TOO_LARGE",
                        "detail": (
                            f"Message size ({len(raw_text)} bytes) exceeds "
                            f"maximum limit ({MAX_WS_MESSAGE_SIZE} bytes)."
                        ),
                    },
                })
                continue

            try:
                msg_data = json.loads(raw_text)
                inbound = CDFWebSocketInbound(**msg_data)
            except Exception as exc:
                await websocket.send_json({
                    "type": CDFServerMessageType.ERROR.value,
                    "payload": {"detail": f"Malformed WebSocket message: {exc}"},
                })
                continue

            if inbound.action == CDFClientActionType.PING:
                await websocket.send_json({
                    "type": CDFServerMessageType.PONG.value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {},
                })

            elif inbound.action == CDFClientActionType.SYNC_REQUEST:
                async with AsyncSessionLocal() as session:
                    # Verify participant membership is still active
                    stmt_chk = select(CDFRoomParticipant).where(
                        and_(
                            CDFRoomParticipant.room_id == room_id,
                            CDFRoomParticipant.user_id == current_user.id,
                        )
                    )
                    res_chk = await session.execute(stmt_chk)
                    if not res_chk.scalar_one_or_none():
                        await websocket.send_json({
                            "type": CDFServerMessageType.ERROR.value,
                            "payload": {
                                "detail": "You are no longer an active participant of this room."
                            },
                        })
                        continue
                    state = await get_latest_room_state(session, room_id)

                await websocket.send_json({
                    "type": CDFServerMessageType.STATE_UPDATED.value,
                    "version": state.version,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "state": state.model_dump(),
                        "constraint_alerts": [a.model_dump() for a in state.constraint_alerts],
                    },
                })

            elif inbound.action == CDFClientActionType.CHAT_MESSAGE:
                if inbound.chat_message:
                    async with AsyncSessionLocal() as session:
                        # Verify participant membership is still active
                        stmt_chk = select(CDFRoomParticipant).where(
                            and_(
                                CDFRoomParticipant.room_id == room_id,
                                CDFRoomParticipant.user_id == current_user.id,
                            )
                        )
                        res_chk = await session.execute(stmt_chk)
                        if not res_chk.scalar_one_or_none():
                            await websocket.send_json({
                                "type": CDFServerMessageType.ERROR.value,
                                "payload": {
                                    "detail": (
                                        "You are no longer an active participant of this room."
                                    )
                                },
                            })
                            continue

                        # Fetch current room version for consistent event stream numbering
                        stmt_r = select(CDFRoom).where(CDFRoom.id == room_id)
                        res_r = await session.execute(stmt_r)
                        room_obj = res_r.scalar_one_or_none()
                        cur_room_ver = room_obj.current_version if room_obj else 1

                        chat_event = CDFEvent(
                            room_id=room_id,
                            event_type="CHAT_MESSAGE",
                            version=cur_room_ver,
                            actor_id=current_user.id,
                            actor_role=participant_role,
                            payload={
                                "message": inbound.chat_message.strip(),
                                "client_message_id": inbound.client_message_id,
                            },
                        )
                        session.add(chat_event)
                        await session.commit()

                    await cdf_connection_manager.broadcast_to_room(
                        room_id,
                        {
                            "type": CDFServerMessageType.CHAT_BROADCAST.value,
                            "version": cur_room_ver,
                            "actor_id": current_user.id,
                            "actor_role": participant_role,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "payload": {
                                "user_name": current_user.full_name,
                                "role": participant_role,
                                "message": inbound.chat_message.strip(),
                                "client_message_id": inbound.client_message_id,
                            },
                        },
                    )

            elif inbound.action == CDFClientActionType.DESIGN_MUTATION:
                if (
                    not inbound.mutation_category
                    or inbound.base_version is None
                    or inbound.patch_data is None
                ):
                    await websocket.send_json({
                        "type": CDFServerMessageType.MUTATION_REJECTED.value,
                        "payload": {
                            "error": "INVALID_MUTATION_PAYLOAD",
                            "detail": "mutation_category, base_version, and patch_data required.",
                        },
                    })
                    continue

                async with AsyncSessionLocal() as session:
                    try:
                        _ = await apply_room_mutation(
                            db=session,
                            room_id=room_id,
                            user_id=current_user.id,
                            base_version=inbound.base_version,
                            mutation_category=inbound.mutation_category,
                            patch_data=inbound.patch_data,
                            client_message_id=inbound.client_message_id,
                        )
                    except CDFVersionConflictError as conf_exc:
                        await websocket.send_json({
                            "type": CDFServerMessageType.MUTATION_REJECTED.value,
                            "version": conf_exc.current_version,
                            "payload": {
                                "error": "VERSION_CONFLICT",
                                "message": str(conf_exc),
                                "current_version": conf_exc.current_version,
                                "current_state": conf_exc.current_state.model_dump(),
                            },
                        })
                    except HTTPException as http_exc:
                        await websocket.send_json({
                            "type": CDFServerMessageType.MUTATION_REJECTED.value,
                            "payload": {
                                "error": "HTTP_EXCEPTION",
                                "detail": http_exc.detail,
                            },
                        })
                    except (ValueError, TypeError, ValidationError) as val_exc:
                        await websocket.send_json({
                            "type": CDFServerMessageType.MUTATION_REJECTED.value,
                            "payload": {
                                "error": "INVALID_MUTATION_DATA",
                                "detail": str(val_exc),
                            },
                        })
                    except Exception as exc:
                        logger.exception("Error processing WebSocket mutation: %s", exc)
                        await websocket.send_json({
                            "type": CDFServerMessageType.MUTATION_REJECTED.value,
                            "payload": {
                                "error": "INTERNAL_ERROR",
                                "detail": str(exc),
                            },
                        })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user %s in room %s", current_user.id, room_id)
    finally:
        await cdf_connection_manager.disconnect(room_id, current_user.id, websocket)
        if current_user.id not in cdf_connection_manager.get_connected_user_ids(room_id):
            async with AsyncSessionLocal() as session:
                try:
                    stmt_disc = (
                        update(CDFRoomParticipant)
                        .where(
                            and_(
                                CDFRoomParticipant.room_id == room_id,
                                CDFRoomParticipant.user_id == current_user.id,
                            )
                        )
                        .values(is_connected=False, last_seen_at=datetime.now(timezone.utc))
                    )
                    await session.execute(stmt_disc)
                    await session.commit()
                except Exception as exc:
                    logger.debug("Failed updating participant disconnected status: %s", exc)
