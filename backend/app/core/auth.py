"""
Authentication, Cryptographic Hashing, and JWT Utilities
Mission Forge — Phase 4
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Set
import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.auth import User

# JWT Configuration
JWT_ALGORITHM = "HS256"
_security_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with a cryptographically secure random salt.
    Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    """
    salt = secrets.token_hex(16)
    iterations = 100_000
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${hash_bytes.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored PBKDF2-HMAC-SHA256 hash
    using constant-time comparison.
    """
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hash = parts[3]
        test_hash = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), iterations
        )
        return hmac.compare_digest(test_hash.hex(), expected_hash)
    except Exception:
        return False


def create_access_token(
    user_id: str,
    email: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Generates a signed JWT access token for an authenticated user."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    encoded_jwt = jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)
    return str(encoded_jwt)


_REVOKED_INVITE_TOKENS: Set[str] = set()


def create_room_invite_token(
    room_id: str,
    role: str,
    inviter_id: str,
    expires_in_hours: int = 24,
) -> str:
    """Generates a cryptographically signed room invitation token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_in_hours)
    token_jti = str(uuid.uuid4())
    payload = {
        "type": "room_invitation",
        "jti": token_jti,
        "room_id": room_id,
        "role": role,
        "inviter_id": inviter_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return str(jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM))


def revoke_invite_token(token: str) -> bool:
    """Revokes an invitation token by registering its jti or token string."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
        if jti:
            _REVOKED_INVITE_TOKENS.add(str(jti))
    except Exception:
        pass
    _REVOKED_INVITE_TOKENS.add(token)
    return True


def is_invite_token_revoked(token: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Checks whether an invitation token has been explicitly revoked."""
    if token in _REVOKED_INVITE_TOKENS:
        return True
    if payload:
        jti = payload.get("jti")
        if jti and str(jti) in _REVOKED_INVITE_TOKENS:
            return True
    return False


def decode_room_invite_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a room invitation token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "room_invitation":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type: not a room invitation token.",
            )
        if is_invite_token_revoked(token, payload):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room invitation token has been revoked.",
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room invitation token has expired.",
        )
    except HTTPException:
        raise
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid room invitation token.",
        )


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token.
    Raises HTTPException 401 if invalid, expired, or malformed.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_from_token(token: str, db: AsyncSession) -> User:
    """
    Resolves an active User instance from an authentication token.
    If Firebase Authentication is configured, verifies the Firebase ID token
    via official Firebase Admin SDK and maps claims to internal User model.
    If unconfigured or in non-production, falls back gracefully to local JWT auth.
    """
    from backend.app.core.firebase import (
        is_firebase_configured,
        verify_firebase_token,
        get_or_create_firebase_user,
    )

    if is_firebase_configured():
        try:
            decoded = verify_firebase_token(token, check_revoked=True)
            return await get_or_create_firebase_user(decoded, db)
        except HTTPException:
            # If in non-production, allow local test/dev JWT token fallback
            if settings.ENVIRONMENT != "production":
                try:
                    payload = decode_access_token(token)
                    dev_user_id: Optional[str] = payload.get("sub")
                    if dev_user_id:
                        stmt = select(User).where(User.id == dev_user_id)
                        res = await db.execute(stmt)
                        user = res.scalar_one_or_none()
                        if user and user.is_active:
                            return user
                except Exception:
                    pass
            raise

    # Fallback to local JWT token validation (when Firebase unconfigured)
    payload = decode_access_token(token)
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )
    return user


async def get_current_user_optional(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(_security_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Optional authentication dependency.
    If Authorization Bearer token is provided, validates credentials and returns User.
    If header is absent, returns None without raising 401.
    """
    if not auth or not auth.credentials:
        return None
    try:
        return await get_current_user_from_token(auth.credentials, db)
    except HTTPException:
        return None


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(_security_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency for authenticating endpoints via Authorization: Bearer <token>."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await get_current_user_from_token(auth.credentials, db)
