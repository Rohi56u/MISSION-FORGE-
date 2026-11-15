"""
Concurrent Design Facility (CDF) Service Layer
Mission Forge — Phase 4
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from backend.app.cdf.roles import assert_role_permission, CDFPermissionDeniedError
from backend.app.cdf.state import (
    CDFAuthoritativeState,
    apply_mutation_to_state,
    initialize_default_cdf_state,
)
from backend.app.cdf.broadcast import cdf_connection_manager
from backend.app.models.cdf import (
    CDFDesignRevision,
    CDFEvent,
    CDFRole,
    CDFRoom,
    CDFRoomParticipant,
    CDFRoomStatus,
)
from backend.app.models.mission import Mission
from backend.app.schemas.cdf import (
    CDFServerMessageType,
    StateMutationResponse,
)

logger = logging.getLogger(__name__)

# Recent idempotent message memory cache: client_message_id -> (version, state_dict)
_IDEMPOTENCY_CACHE: Dict[str, Tuple[int, Dict[str, Any]]] = {}


class CDFVersionConflictError(Exception):
    """Raised when an incoming mutation has a stale base_version."""
    def __init__(self, current_version: int, current_state: CDFAuthoritativeState):
        super().__init__(
            f"Version conflict: Expected base_version {current_version}, "
            "client provided a stale or conflicting version."
        )
        self.current_version = current_version
        self.current_state = current_state


async def create_cdf_room(
    db: AsyncSession,
    name: str,
    mission_id: str,
    creator_id: str,
    creator_role: CDFRole,
) -> CDFRoom:
    """
    Creates a new CDF collaboration room, initializes authoritative revision 1,
    and assigns the creator to their chosen role.
    """
    # 1. Verify mission exists
    stmt_m = select(Mission).where(Mission.id == mission_id)
    res_m = await db.execute(stmt_m)
    mission = res_m.scalar_one_or_none()
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission with ID '{mission_id}' not found.",
        )

    # 2. Create Room
    room = CDFRoom(
        name=name.strip(),
        mission_id=mission.id,
        creator_id=creator_id,
        status=CDFRoomStatus.ACTIVE,
        max_participants=4,
        current_version=1,
    )
    db.add(room)
    await db.flush()

    # 3. Add Creator as initial Participant
    participant = CDFRoomParticipant(
        room_id=room.id,
        user_id=creator_id,
        role=creator_role,
        is_connected=True,
    )
    db.add(participant)

    # 4. Initialize Baseline Authoritative State
    tgt = mission.target.value if hasattr(mission.target, "value") else str(mission.target)
    m_cls = (
        mission.mission_class.value
        if hasattr(mission.mission_class, "value")
        else str(mission.mission_class)
    )
    initial_state = initialize_default_cdf_state(
        room_id=room.id,
        mission_id=mission.id,
        target=tgt,
        mission_class=m_cls,
        budget_cap_usd=mission.budget_cap_usd,
        max_launch_mass_kg=mission.max_launch_mass_kg,
        min_delta_v_mps=mission.min_delta_v_mps,
        min_power_margin_percent=mission.min_power_margin_percent,
    )

    # 5. Persist Baseline Revision 1
    rev = CDFDesignRevision(
        room_id=room.id,
        version=1,
        author_id=creator_id,
        author_role=creator_role.value,
        mutation_type="INITIALIZE_ROOM",
        patch_data={"name": room.name, "mission_id": mission.id},
        state_snapshot=initial_state.model_dump(),
        swapc_snapshot=initial_state.calculated_budgets.model_dump(),
    )
    db.add(rev)

    # 6. Persist Initial Event
    event = CDFEvent(
        room_id=room.id,
        event_type="ROOM_CREATED",
        version=1,
        actor_id=creator_id,
        actor_role=creator_role.value,
        payload={
            "room_name": room.name,
            "creator_id": creator_id,
            "role": creator_role.value,
        },
    )
    db.add(event)

    await db.commit()
    await db.refresh(room)
    return room


async def join_cdf_room(
    db: AsyncSession,
    room_id: str,
    user_id: str,
    role: CDFRole,
) -> CDFRoomParticipant:
    """
    Adds an authenticated user to a room with the requested role.
    Enforces maximum capacity (4 participants) and role exclusivity (1 user per role).
    """
    stmt = select(CDFRoom).where(CDFRoom.id == room_id)
    res = await db.execute(stmt)
    room = res.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CDF room not found.")
    if room.status != CDFRoomStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot join room because its status is {room.status.value}.",
        )

    # Fetch existing participants
    stmt_p = select(CDFRoomParticipant).where(CDFRoomParticipant.room_id == room_id)
    res_p = await db.execute(stmt_p)
    participants = res_p.scalars().all()

    # Check if user already joined
    for p in participants:
        if p.user_id == user_id:
            if p.role != role:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"You are already registered in this room with role '{p.role.value}'.",
                )
            # Reconnection: mark active
            p.is_connected = True
            p.last_seen_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(p)
            return p

    # Check role availability
    for p in participants:
        if p.role == role:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Role '{role.value}' is already occupied by another participant.",
            )

    # Check capacity limit
    if len(participants) >= room.max_participants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Room is at maximum capacity ({room.max_participants} participants).",
        )

    # Add new participant
    new_participant = CDFRoomParticipant(
        room_id=room_id,
        user_id=user_id,
        role=role,
        is_connected=True,
    )
    db.add(new_participant)

    # Event log
    event = CDFEvent(
        room_id=room_id,
        event_type="USER_JOINED",
        version=room.current_version,
        actor_id=user_id,
        actor_role=role.value,
        payload={"role": role.value, "timestamp": datetime.now(timezone.utc).isoformat()},
    )
    db.add(event)

    await db.commit()
    await db.refresh(new_participant)

    # Broadcast event
    await cdf_connection_manager.broadcast_to_room(
        room_id,
        {
            "type": CDFServerMessageType.PARTICIPANT_JOINED.value,
            "version": room.current_version,
            "actor_id": user_id,
            "actor_role": role.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "user_id": user_id,
                "role": role.value,
            },
        },
    )

    return new_participant


async def leave_cdf_room(db: AsyncSession, room_id: str, user_id: str) -> bool:
    """Removes or disconnects a participant from the room."""
    stmt = select(CDFRoomParticipant).where(
        and_(CDFRoomParticipant.room_id == room_id, CDFRoomParticipant.user_id == user_id)
    )
    res = await db.execute(stmt)
    participant = res.scalar_one_or_none()
    if not participant:
        return False

    # Fetch room version for authoritative audit event logging
    stmt_r = select(CDFRoom).where(CDFRoom.id == room_id)
    res_r = await db.execute(stmt_r)
    room = res_r.scalar_one_or_none()
    current_ver = room.current_version if room else 1

    role_val = participant.role.value
    await db.delete(participant)

    # Event log
    event = CDFEvent(
        room_id=room_id,
        event_type="USER_LEFT",
        version=current_ver,
        actor_id=user_id,
        actor_role=role_val,
        payload={"role": role_val, "timestamp": datetime.now(timezone.utc).isoformat()},
    )
    db.add(event)
    await db.commit()

    # Broadcast event
    await cdf_connection_manager.broadcast_to_room(
        room_id,
        {
            "type": CDFServerMessageType.PARTICIPANT_LEFT.value,
            "version": current_ver,
            "actor_id": user_id,
            "actor_role": role_val,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"user_id": user_id, "role": role_val},
        },
    )

    # Cleanly terminate and unregister any active WebSocket for the departing participant
    await cdf_connection_manager.disconnect_and_close(room_id, user_id)
    return True


async def get_latest_room_state(db: AsyncSession, room_id: str) -> CDFAuthoritativeState:
    """Retrieves the latest authoritative design state snapshot from the database."""
    stmt = (
        select(CDFDesignRevision)
        .where(CDFDesignRevision.room_id == room_id)
        .order_by(CDFDesignRevision.version.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    latest_rev = res.scalar_one_or_none()
    if not latest_rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No design revisions found for room '{room_id}'.",
        )
    return CDFAuthoritativeState(**latest_rev.state_snapshot)


async def apply_room_mutation(
    db: AsyncSession,
    room_id: str,
    user_id: str,
    base_version: int,
    mutation_category: str,
    patch_data: Dict[str, Any],
    client_message_id: Optional[str] = None,
) -> StateMutationResponse:
    """
    Validates, applies, and transactionally commits an engineering mutation.
    Enforces role-based permissions, state version optimistic concurrency,
    and duplicate message protection.
    """
    # 1. Check duplicate idempotency (Memory Cache & DB Revision Check)
    if client_message_id:
        if client_message_id in _IDEMPOTENCY_CACHE:
            cached_ver, cached_state = _IDEMPOTENCY_CACHE[client_message_id]
            logger.info(
                "Returning cached mutation response for duplicate message %s", client_message_id
            )
            parsed_state = CDFAuthoritativeState(**cached_state)
            return StateMutationResponse(
                success=True,
                new_version=cached_ver,
                mutation_type=mutation_category,
                state=parsed_state,
                constraint_alerts=parsed_state.constraint_alerts,
            )
        # Database persistence check for idempotency across restarts
        stmt_dup = (
            select(CDFDesignRevision)
            .where(CDFDesignRevision.room_id == room_id)
            .order_by(CDFDesignRevision.version.desc())
            .limit(50)
        )
        res_dup = await db.execute(stmt_dup)
        for r in res_dup.scalars().all():
            if (
                isinstance(r.patch_data, dict)
                and r.patch_data.get("_client_message_id") == client_message_id
            ):
                parsed_state = CDFAuthoritativeState(**r.state_snapshot)
                return StateMutationResponse(
                    success=True,
                    new_version=r.version,
                    mutation_type=r.mutation_type,
                    state=parsed_state,
                    constraint_alerts=parsed_state.constraint_alerts,
                )

    # 2. Verify Room and Participant Membership
    stmt_room = select(CDFRoom).where(CDFRoom.id == room_id).with_for_update()
    res_room = await db.execute(stmt_room)
    room = res_room.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CDF room not found.")
    if room.status != CDFRoomStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room is {room.status.value}; mutations are locked.",
        )

    stmt_p = select(CDFRoomParticipant).where(
        and_(CDFRoomParticipant.room_id == room_id, CDFRoomParticipant.user_id == user_id)
    )
    res_p = await db.execute(stmt_p)
    participant = res_p.scalar_one_or_none()
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a registered participant of this CDF room.",
        )

    # 3. Enforce Role Permissions
    try:
        assert_role_permission(participant.role.value, mutation_category)
    except CDFPermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    # 4. Optimistic Concurrency Control (Version Match Check)
    current_state = await get_latest_room_state(db, room_id)
    latest_version = max(room.current_version, current_state.version)
    if base_version != room.current_version or base_version != current_state.version:
        raise CDFVersionConflictError(
            current_version=latest_version, current_state=current_state
        )

    # 5. Apply Mutation & Deterministic SWaP-C Recomputation
    new_state = apply_mutation_to_state(
        current_state=current_state,
        mutation_category=mutation_category,
        patch_data=patch_data,
        actor_role=participant.role.value,
    )

    # 6. Persist Revision and Event Transactionally
    room.current_version = new_state.version

    persisted_patch = dict(patch_data)
    if client_message_id:
        persisted_patch["_client_message_id"] = client_message_id

    rev = CDFDesignRevision(
        room_id=room_id,
        version=new_state.version,
        author_id=user_id,
        author_role=participant.role.value,
        mutation_type=mutation_category,
        patch_data=persisted_patch,
        state_snapshot=new_state.model_dump(),
        swapc_snapshot=new_state.calculated_budgets.model_dump(),
    )
    db.add(rev)

    event = CDFEvent(
        room_id=room_id,
        event_type="MUTATION_APPLIED",
        version=new_state.version,
        actor_id=user_id,
        actor_role=participant.role.value,
        payload={
            "mutation_category": mutation_category,
            "patch_data": patch_data,
            "client_message_id": client_message_id,
            "budgets": new_state.calculated_budgets.model_dump(),
            "alerts": [a.model_dump() for a in new_state.constraint_alerts],
        },
    )
    db.add(event)

    try:
        await db.commit()
        await db.refresh(room)
    except IntegrityError:
        await db.rollback()
        # Handle concurrent commit collision gracefully as a 409 conflict
        latest_state = await get_latest_room_state(db, room_id)
        raise CDFVersionConflictError(
            current_version=latest_state.version, current_state=latest_state
        )

    # Store in idempotency cache
    if client_message_id:
        _IDEMPOTENCY_CACHE[client_message_id] = (new_state.version, new_state.model_dump())
        if len(_IDEMPOTENCY_CACHE) > 500:
            # Simple eviction
            _IDEMPOTENCY_CACHE.pop(next(iter(_IDEMPOTENCY_CACHE)))

    # 7. Broadcast STATE_UPDATED to all connected room participants
    broadcast_payload = {
        "type": CDFServerMessageType.STATE_UPDATED.value,
        "version": new_state.version,
        "actor_id": user_id,
        "actor_role": participant.role.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "mutation_category": mutation_category,
            "state": new_state.model_dump(),
            "constraint_alerts": [a.model_dump() for a in new_state.constraint_alerts],
        },
    }
    await cdf_connection_manager.broadcast_to_room(room_id, broadcast_payload)

    return StateMutationResponse(
        success=True,
        new_version=new_state.version,
        mutation_type=mutation_category,
        state=new_state,
        constraint_alerts=new_state.constraint_alerts,
    )


async def join_cdf_room_with_invite(
    db: AsyncSession,
    invite_token: str,
    user_id: str,
) -> CDFRoomParticipant:
    """Validates an invitation access token and joins the CDF room."""
    from backend.app.core.auth import decode_room_invite_token
    payload = decode_room_invite_token(invite_token)
    room_id = payload.get("room_id")
    role_str = payload.get("role")
    token_jti = payload.get("jti")
    if not room_id or not role_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed room invitation token: missing room_id or role.",
        )

    # Persistent database revocation check across process restarts
    stmt_rev = select(CDFEvent).where(
        and_(
            CDFEvent.room_id == room_id,
            CDFEvent.event_type == "TOKEN_REVOKED",
        )
    )
    res_rev = await db.execute(stmt_rev)
    for ev in res_rev.scalars().all():
        if (
            isinstance(ev.payload, dict)
            and (ev.payload.get("jti") == token_jti or ev.payload.get("token") == invite_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room invitation token has been revoked.",
            )

    try:
        role = CDFRole(role_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{role_str}' in invitation token.",
        )
    return await join_cdf_room(db=db, room_id=room_id, user_id=user_id, role=role)


async def update_room_lifecycle_status(
    db: AsyncSession,
    room_id: str,
    user_id: str,
    new_status: CDFRoomStatus,
) -> CDFRoom:
    """
    Updates the lifecycle status of a room (ACTIVE, LOCKED, ARCHIVED).
    Restricted to room creator or Lead Systems Architect.
    """
    stmt = select(CDFRoom).where(CDFRoom.id == room_id)
    res = await db.execute(stmt)
    room = res.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CDF room not found.")

    stmt_p = select(CDFRoomParticipant).where(
        and_(CDFRoomParticipant.room_id == room_id, CDFRoomParticipant.user_id == user_id)
    )
    res_p = await db.execute(stmt_p)
    participant = res_p.scalar_one_or_none()

    is_creator = (room.creator_id == user_id)
    is_lead = (participant is not None and participant.role == CDFRole.LEAD_SYSTEMS_ARCHITECT)
    if not is_creator and not is_lead:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only the room creator or Lead Systems Architect "
                "can change room lifecycle status."
            ),
        )

    old_status = room.status
    room.status = new_status

    event = CDFEvent(
        room_id=room_id,
        event_type="ROOM_STATUS_CHANGED",
        version=room.current_version,
        actor_id=user_id,
        actor_role=participant.role.value if participant else "CREATOR",
        payload={
            "old_status": old_status.value,
            "new_status": new_status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    db.add(event)
    await db.commit()
    await db.refresh(room)

    # Broadcast status change event
    await cdf_connection_manager.broadcast_to_room(
        room_id,
        {
            "type": "ROOM_STATUS_UPDATED",
            "version": room.current_version,
            "actor_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"old_status": old_status.value, "new_status": new_status.value},
        },
    )
    return room


async def cleanup_inactive_rooms(
    db: AsyncSession,
    max_age_days: int = 14,
) -> List[str]:
    """Archives stale or abandoned rooms and cleans up lingering subscriptions."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    stmt = select(CDFRoom).where(
        and_(
            CDFRoom.status != CDFRoomStatus.ARCHIVED,
            CDFRoom.updated_at < cutoff,
        )
    )
    res = await db.execute(stmt)
    stale_rooms = res.scalars().all()
    cleaned_ids: List[str] = []
    for r in stale_rooms:
        r.status = CDFRoomStatus.ARCHIVED
        cleaned_ids.append(r.id)
    if cleaned_ids:
        await db.commit()
    return cleaned_ids
