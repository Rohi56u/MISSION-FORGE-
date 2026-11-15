"""
Firebase Admin Authentication Integration & Identity Provider Mapping
Mission Forge — Security Core

Authoritative Identity Architecture:
- Firebase Authentication is the authoritative identity provider (IdP).
- Mission Forge server verifies ID tokens using the official Firebase Admin SDK.
- Enforces cryptographic signature verification, project audience/issuer validation,
  expiry validation, and server-side token revocation checks.
- Maps verified Firebase UID and claims to internal SQLAlchemy User model.
- Client-supplied UIDs or roles are never trusted.
- Gracefully falls back to local dev/test JWT authentication when FIREBASE_PROJECT_ID
  is unconfigured.
"""

import logging
import os
from typing import Any, Dict, Optional
import uuid

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import (  # type: ignore[import-untyped]
    auth as fb_auth,
    credentials as fb_credentials,
)
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.auth import User

logger = logging.getLogger(__name__)

_FIREBASE_APP: Optional[firebase_admin.App] = None
_FIREBASE_INITIALIZED: bool = False


def is_firebase_configured() -> bool:
    """Returns True if Firebase Project ID is configured in settings."""
    return bool(settings.FIREBASE_PROJECT_ID and settings.FIREBASE_PROJECT_ID.strip())


def get_firebase_app() -> Optional[firebase_admin.App]:
    """
    Initializes or retrieves the singleton Firebase Admin App.
    Initializes credentials from service account file, environment variables,
    or Application Default Credentials (ADC).
    """
    global _FIREBASE_APP, _FIREBASE_INITIALIZED

    if not is_firebase_configured():
        return None

    if _FIREBASE_INITIALIZED and _FIREBASE_APP is not None:
        return _FIREBASE_APP

    project_id = str(settings.FIREBASE_PROJECT_ID).strip()

    # Check if app already initialized in firebase_admin._apps
    try:
        app = firebase_admin.get_app()
        _FIREBASE_APP = app
        _FIREBASE_INITIALIZED = True
        return _FIREBASE_APP
    except ValueError:
        pass

    cred: Optional[fb_credentials.Base] = None

    # 1. Certificate file path
    if settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
        try:
            cred = fb_credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            logger.info(
                "Firebase Admin initialized via certificate file: %s",
                settings.FIREBASE_CREDENTIALS_PATH,
            )
        except Exception as e:
            logger.error("Failed to load Firebase credentials file: %s", e)

    # 2. Inline service account credentials (Private Key & Client Email)
    if cred is None and settings.FIREBASE_CLIENT_EMAIL and settings.FIREBASE_PRIVATE_KEY:
        try:
            # Reconstruct private key newlines if escaped
            pk = settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n")
            cert_dict = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": pk,
                "client_email": settings.FIREBASE_CLIENT_EMAIL,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            cred = fb_credentials.Certificate(cert_dict)
            logger.info("Firebase Admin initialized via inline service account credentials.")
        except Exception as e:
            logger.error("Failed to load inline Firebase service account: %s", e)

    # 3. Application Default Credentials fallback
    if cred is None:
        try:
            cred = fb_credentials.ApplicationDefault()
            logger.info("Firebase Admin initialized via Application Default Credentials (ADC).")
        except Exception as e:
            logger.warning(
                "Application Default Credentials unavailable for Firebase (%s); "
                "initializing default app without explicit credential.",
                e,
            )

    options = {"projectId": project_id}
    try:
        if cred:
            _FIREBASE_APP = firebase_admin.initialize_app(cred, options=options)
        else:
            _FIREBASE_APP = firebase_admin.initialize_app(options=options)
        _FIREBASE_INITIALIZED = True
        logger.info("Firebase Admin successfully initialized for project: %s", project_id)
    except Exception as exc:
        logger.error("Error initializing Firebase Admin SDK: %s", exc)
        _FIREBASE_APP = None
        _FIREBASE_INITIALIZED = False

    return _FIREBASE_APP


def verify_firebase_token(
    token: str,
    check_revoked: bool = True,
) -> Dict[str, Any]:
    """
    Verifies a Firebase ID token server-side using the official Admin SDK.

    Enforces:
    - RS256 signature verification against Google's public x509 certificates.
    - Expiration time (exp).
    - Issued-at time (iat).
    - Project audience (aud) matching settings.FIREBASE_PROJECT_ID.
    - Issuer (iss) matching https://securetoken.google.com/<project_id>.
    - Subject (sub/uid) existence.
    - Revocation check (check_revoked) against Firebase Auth backend.

    Raises:
        HTTPException 401 if token is expired, revoked, invalid, or belongs to wrong project.
    """
    if not is_firebase_configured():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase Authentication is not configured on this server.",
        )

    app = get_firebase_app()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase Admin SDK is not properly initialized.",
        )

    expected_project_id = str(settings.FIREBASE_PROJECT_ID).strip()
    expected_issuer = f"https://securetoken.google.com/{expected_project_id}"

    try:
        decoded = fb_auth.verify_id_token(
            token,
            app=app,
            check_revoked=check_revoked,
            clock_skew_seconds=10,
        )
    except fb_auth.RevokedIdTokenError:
        logger.warning("Rejected revoked Firebase ID token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase authentication token has been revoked.",
            headers={
                "WWW-Authenticate": (
                    'Bearer error="invalid_token", error_description="Token revoked"'
                )
            },
        )
    except fb_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase authentication token has expired.",
            headers={
                "WWW-Authenticate": (
                    'Bearer error="invalid_token", error_description="Token expired"'
                )
            },
        )
    except fb_auth.InvalidIdTokenError as e:
        logger.warning("Invalid Firebase ID token received: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error("Unexpected error verifying Firebase ID token: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate Firebase credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Explicit Issuer, Audience, and Project Validation
    token_aud = decoded.get("aud")
    token_iss = decoded.get("iss")
    token_uid = decoded.get("uid") or decoded.get("sub")

    if token_aud != expected_project_id:
        logger.critical(
            "Security Alert: Firebase token audience mismatch. Expected: '%s', Got: '%s'",
            expected_project_id,
            token_aud,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token audience does not match configured Firebase project.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_iss != expected_issuer:
        logger.critical(
            "Security Alert: Firebase token issuer mismatch. Expected: '%s', Got: '%s'",
            expected_issuer,
            token_iss,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token issuer does not match official Google Firebase Authority.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not token_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token missing user subject identifier (UID).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return decoded


async def get_or_create_firebase_user(
    decoded_token: Dict[str, Any],
    db: AsyncSession,
) -> User:
    """
    Maps a verified Firebase ID token to the internal Mission Forge User model.
    Never trusts client-supplied UIDs or roles; uses authoritative token claims.
    """
    firebase_uid = decoded_token.get("uid") or decoded_token.get("sub")
    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing verified Firebase UID in token claims.",
        )

    email = decoded_token.get("email")
    if not email:
        email = f"{firebase_uid}@firebase.missionforge.internal"

    name = decoded_token.get("name") or decoded_token.get("display_name")
    if not name:
        name = email.split("@")[0] or f"Officer {firebase_uid[:8]}"

    # 1. Lookup by verified firebase_uid
    stmt = select(User).where(User.firebase_uid == firebase_uid)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if user:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated.",
            )
        return user

    # 2. Lookup by email for accounts linking Firebase to an existing profile
    stmt_email = select(User).where(User.email == email)
    res_email = await db.execute(stmt_email)
    existing_user_by_email = res_email.scalar_one_or_none()

    if existing_user_by_email:
        if not existing_user_by_email.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated.",
            )
        # Link Firebase UID to existing account
        existing_user_by_email.firebase_uid = firebase_uid
        await db.commit()
        await db.refresh(existing_user_by_email)
        return existing_user_by_email

    # 3. Auto-provision internal User profile from verified claims
    new_user = User(
        id=str(uuid.uuid4()),
        firebase_uid=firebase_uid,
        email=email,
        full_name=name,
        hashed_password="FIREBASE_EXTERNAL_AUTHENTICATION",
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    logger.info(
        "Auto-provisioned internal User profile for Firebase UID: %s (%s)",
        firebase_uid,
        email,
    )
    return new_user
