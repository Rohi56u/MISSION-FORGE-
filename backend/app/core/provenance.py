"""
Field-Level Provenance Engine for Mission Forge
Provides structured, traceable provenance models for every technical specification.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.component import VerificationStatus


class FieldProvenanceRecord(BaseModel):
    """
    Provenance metadata for an individual component attribute or measurement.
    Traces values directly to authoritative aerospace documentation.
    """
    model_config = ConfigDict(extra="ignore")

    source_system: str = Field(
        ...,
        description="Source organization/system (e.g. NASA_NTRS, NASA_TECHPORT, JPL_DESCANSO)",
    )
    citation: Optional[str] = Field(
        default=None,
        description="Formal citation or document number (e.g. NASA/TM-2010-216772)",
    )
    canonical_url: Optional[str] = Field(
        default=None,
        description="Authoritative reference or retrieval URL",
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.VERIFIED_AUTHORITATIVE,
        description="Verification rating for this specific field",
    )
    verified_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this field specification was verified",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Operational context, qualification conditions, or measurement caveats",
    )
    raw_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 digest of original source snippet or payload",
    )


def compute_payload_hash(payload: Any) -> str:
    """Computes a deterministic SHA-256 hash of a payload dictionary or string."""
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
