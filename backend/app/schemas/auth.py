"""
Authentication Request & Response Schemas
Mission Forge — Phase 4
"""

from datetime import datetime
import re
from pydantic import BaseModel, Field, ConfigDict, field_validator

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserRegisterRequest(BaseModel):
    """User registration payload."""
    email: str = Field(..., min_length=5, max_length=255, description="Unique email address")
    full_name: str = Field(..., min_length=2, max_length=128, description="Participant's full name")
    password: str = Field(..., min_length=8, max_length=128, description="Strong password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if not _EMAIL_REGEX.match(v_clean):
            raise ValueError("Invalid email format.")
        return v_clean


class UserLoginRequest(BaseModel):
    """User login credential payload."""
    email: str = Field(..., min_length=5, max_length=255, description="Registered email address")
    password: str = Field(..., description="Account password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if not _EMAIL_REGEX.match(v_clean):
            raise ValueError("Invalid email format.")
        return v_clean


class UserResponse(BaseModel):
    """Public user profile response."""
    id: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """JWT bearer token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
