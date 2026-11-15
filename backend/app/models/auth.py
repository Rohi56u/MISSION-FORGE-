"""
Authentication Database Models
Mission Forge — Phase 4
"""

from typing import Optional
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import UUIDModelMixin, TimestampModelMixin


class User(Base, UUIDModelMixin, TimestampModelMixin):
    """User account entity for authentication and room participant attribution."""
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    firebase_uid: Mapped[Optional[str]] = mapped_column(
        String(128), unique=True, index=True, nullable=True
    )
