"""
Concurrent Design Facility (CDF) Request & Response Schemas
Mission Forge — Phase 4
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from backend.app.models.cdf import CDFRole, CDFRoomStatus
from backend.app.cdf.state import (
    CDFAuthoritativeState,
    ConstraintAlert,
)


class CDFClientActionType(str, Enum):
    """Supported WebSocket and HTTP action types submitted by clients."""
    JOIN_ROOM = "JOIN_ROOM"
    LEAVE_ROOM = "LEAVE_ROOM"
    DESIGN_MUTATION = "DESIGN_MUTATION"
    CHAT_MESSAGE = "CHAT_MESSAGE"
    SYNC_REQUEST = "SYNC_REQUEST"
    PING = "PING"


class CDFServerMessageType(str, Enum):
    """Typed WebSocket event types emitted by the server."""
    ROOM_JOINED = "ROOM_JOINED"
    PARTICIPANT_JOINED = "PARTICIPANT_JOINED"
    PARTICIPANT_LEFT = "PARTICIPANT_LEFT"
    STATE_UPDATED = "STATE_UPDATED"
    MUTATION_REJECTED = "MUTATION_REJECTED"
    CONSTRAINT_ALERT = "CONSTRAINT_ALERT"
    CHAT_BROADCAST = "CHAT_BROADCAST"
    ERROR = "ERROR"
    PONG = "PONG"


# --- REST Schemas ---

class RoomCreateRequest(BaseModel):
    """Payload to create a new concurrent design facility room."""
    name: str = Field(..., min_length=2, max_length=128, description="Room name")
    mission_id: str = Field(..., description="Target mission UUID")
    role: CDFRole = Field(
        default=CDFRole.LEAD_SYSTEMS_ARCHITECT,
        description="Creator's assigned role in the room",
    )


class ParticipantResponse(BaseModel):
    """CDF room participant membership details."""
    id: str
    user_id: str
    full_name: str
    email: str
    role: CDFRole
    is_connected: bool
    joined_at: datetime
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoomResponse(BaseModel):
    """Summary of a CDF room."""
    id: str
    name: str
    mission_id: str
    status: CDFRoomStatus
    max_participants: int
    current_version: int
    participant_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoomDetailResponse(BaseModel):
    """Comprehensive details of a room including participant roster and latest design state."""
    id: str
    name: str
    mission_id: str
    status: CDFRoomStatus
    max_participants: int
    current_version: int
    participants: List[ParticipantResponse]
    state: CDFAuthoritativeState
    created_at: datetime


class JoinRoomRequest(BaseModel):
    """Request to join a room under a specific role."""
    role: CDFRole = Field(..., description="Role to assume in the room")


class RoomInviteCreateRequest(BaseModel):
    """Request to generate an invitation access token for a specific role."""
    role: CDFRole = Field(..., description="Role to invite the user to assume")
    expires_in_hours: int = Field(default=24, ge=1, le=168, description="Token validity in hours")


class RoomInviteResponse(BaseModel):
    """Issued room invitation token."""
    invite_token: str
    room_id: str
    role: CDFRole
    expires_at: datetime


class JoinWithInviteRequest(BaseModel):
    """Request to join a room using an authorized invitation token."""
    invite_token: str = Field(..., description="Cryptographically signed invitation token")


class RoomInviteRevokeRequest(BaseModel):
    """Request to revoke an active invitation token."""
    invite_token: str = Field(
        ..., description="Cryptographically signed invitation token to revoke"
    )


class RoomStatusUpdateRequest(BaseModel):
    """Request by Lead Systems Architect or room creator to change room lifecycle status."""
    status: CDFRoomStatus = Field(..., description="Target status: ACTIVE, LOCKED, ARCHIVED")


class RoomCleanupResponse(BaseModel):
    """Summary of cleaned up inactive rooms."""
    archived_rooms_count: int
    cleaned_room_ids: List[str]


class StateMutationRequest(BaseModel):
    """Atomic design mutation submitted by an authorized participant."""
    base_version: int = Field(..., description="Current version the client is modifying")
    mutation_category: str = Field(
        ...,
        description=(
            "Target domain: SYSTEM_CONSTRAINTS, PROPULSION_POWER, "
            "SCIENCE_PAYLOAD, FLIGHT_DYNAMICS_COMMS"
        ),
    )
    patch_data: Dict[str, Any] = Field(..., description="Fields to update within the domain")
    client_message_id: Optional[str] = Field(
        None, description="Client idempotency key for duplicate-protection"
    )


class StateMutationResponse(BaseModel):
    """Result of an applied mutation."""
    success: bool
    new_version: int
    mutation_type: str
    state: CDFAuthoritativeState
    constraint_alerts: List[ConstraintAlert]


class RevisionResponse(BaseModel):
    """Snapshot of a committed revision in history."""
    id: str
    room_id: str
    version: int
    author_id: str
    author_role: str
    mutation_type: str
    patch_data: Dict[str, Any]
    swapc_snapshot: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventResponse(BaseModel):
    """Audit log event."""
    id: str
    room_id: str
    event_type: str
    version: int
    actor_id: str
    actor_role: Optional[str]
    payload: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- WebSocket Contracts ---

class CDFWebSocketInbound(BaseModel):
    """Strict schema for messages sent by clients to the WebSocket."""
    action: CDFClientActionType
    base_version: Optional[int] = None
    mutation_category: Optional[str] = None
    patch_data: Optional[Dict[str, Any]] = None
    chat_message: Optional[str] = None
    client_message_id: Optional[str] = None


class CDFWebSocketOutbound(BaseModel):
    """Strict schema for messages broadcasted or returned by the server."""
    type: CDFServerMessageType
    version: Optional[int] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
