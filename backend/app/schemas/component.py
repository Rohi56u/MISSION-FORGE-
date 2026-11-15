"""
Pydantic v2 Schemas for Component Catalog API
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
from backend.app.models.component import SubsystemType, VerificationStatus


class ComponentCreateSchema(BaseModel):
    """
    Schema for creating a catalog component.
    Note: Phase 1 provides development-level access without OAuth/RBAC.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128, description="Component name")
    subsystem: SubsystemType = Field(..., description="Spacecraft subsystem category")
    description: Optional[str] = Field(default=None, max_length=1024)

    # Physical parameters (SI units)
    mass_kg: float = Field(default=0.0, ge=0.0, description="Dry mass in kilograms")
    power_draw_w: float = Field(
        default=0.0, ge=0.0, description="Electrical load in Watts"
    )
    power_generation_w: float = Field(
        default=0.0, ge=0.0, description="Power generated at 1 AU in Watts"
    )
    cost_usd: float = Field(
        default=0.0, ge=0.0, description="Procurement/fabrication cost in USD"
    )

    # Subsystem specific specs
    isp_seconds: Optional[float] = Field(
        default=None, gt=0.0, description="Specific impulse in seconds"
    )
    thrust_newtons: Optional[float] = Field(
        default=None, gt=0.0, description="Operating thrust in Newtons"
    )
    propellant_type: Optional[str] = Field(default=None, max_length=64)

    solar_area_m2: Optional[float] = Field(
        default=None, gt=0.0, description="Photovoltaic area in m^2"
    )
    solar_efficiency: Optional[float] = Field(
        default=None, gt=0.0, le=1.0, description="Cell conversion efficiency (0-1)"
    )
    decay_rate_annual: Optional[float] = Field(
        default=None, ge=0.0, lt=1.0, description="Annual degradation fraction"
    )

    antenna_diameter_m: Optional[float] = Field(
        default=None, gt=0.0, description="Parabolic dish aperture in meters"
    )
    frequency_band: Optional[str] = Field(
        default=None, max_length=32, description="RF Band: S, X, Ka, Optical"
    )
    tx_power_w: Optional[float] = Field(
        default=None, gt=0.0, description="Transmitter RF power in Watts"
    )

    # Provenance and flight heritage
    trl: int = Field(
        default=9, ge=1, le=9, description="NASA Technology Readiness Level (1-9)"
    )
    flight_heritage: Optional[str] = Field(
        default=None, max_length=256, description="Flight heritage missions"
    )
    techport_id: Optional[str] = Field(
        default=None, max_length=64, description="NASA TechPort project ID"
    )
    source_url: Optional[str] = Field(
        default=None, max_length=512, description="Authoritative reference URL"
    )
    source_system: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Originating source system (e.g. NASA_NTRS, NASA_TECHPORT)",
    )
    raw_source_hash: Optional[str] = Field(
        default=None, max_length=64, description="SHA-256 digest of original source payload"
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.VERIFIED_AUTHORITATIVE,
        description="Data verification confidence rating",
    )

    # Field-level provenance mapping {field_name: {source_system, citation, canonical_url, ...}}
    field_provenance: Dict[str, Any] = Field(
        default_factory=dict, description="Field-level source provenance and citation records"
    )
    specifications: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary verified technical specs"
    )
    is_active: bool = Field(default=True, description="Whether active in catalog")


class ComponentResponseSchema(ComponentCreateSchema):
    """Full component response with database IDs, timestamps, and provenance tracking."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ComponentProvenanceResponseSchema(BaseModel):
    """Detailed field-level provenance audit report for a catalog component."""
    component_id: str
    component_name: str
    subsystem: SubsystemType
    verification_status: VerificationStatus
    source_system: Optional[str] = None
    source_url: Optional[str] = None
    techport_id: Optional[str] = None
    raw_source_hash: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    field_provenance: Dict[str, Any] = Field(default_factory=dict)
    audit_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CatalogStatusResponseSchema(BaseModel):
    """Catalog-wide provenance, freshness, and synchronization audit report."""
    total_components: int = Field(..., description="Total active components in catalog")
    subsystems_breakdown: Dict[str, int] = Field(
        default_factory=dict, description="Component count by subsystem"
    )
    verification_status_breakdown: Dict[str, int] = Field(
        default_factory=dict, description="Component count by verification confidence"
    )
    components_with_provenance: int = Field(
        ..., description="Number of components possessing field-level source citations"
    )
    provenance_coverage_percent: float = Field(
        ..., description="Percentage of components possessing field-level provenance"
    )
    source_systems: List[str] = Field(
        default_factory=list, description="Unique source systems recorded across catalog"
    )
    last_synced_at: Optional[datetime] = Field(
        default=None, description="Most recent component synchronization timestamp"
    )
    audit_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SyncUpdatePolicy(str, Enum):
    """Policy for resolving conflicts during component catalog synchronization."""
    PRESERVE_CURATED = "PRESERVE_CURATED"
    OVERWRITE_ALL = "OVERWRITE_ALL"
    UPDATE_MISSING_ONLY = "UPDATE_MISSING_ONLY"


class CatalogSyncRequestSchema(BaseModel):
    """Request payload for safe, idempotent component catalog synchronization."""
    items: List[ComponentCreateSchema] = Field(
        ..., min_length=1, max_length=200, description="Components to import or sync"
    )
    update_policy: SyncUpdatePolicy = Field(
        default=SyncUpdatePolicy.PRESERVE_CURATED,
        description="Policy when matching component already exists",
    )
    dry_run: bool = Field(
        default=False,
        description="Preview synchronization changes without modifying database",
    )
    source_system: Optional[str] = Field(
        default="MANUAL_SYNC", description="Source system identifier for audit trail"
    )


class CatalogSyncSummarySchema(BaseModel):
    """Audit summary of catalog synchronization or dry-run execution."""
    dry_run: bool
    update_policy: SyncUpdatePolicy
    total_submitted: int
    created_count: int
    updated_count: int
    skipped_count: int
    conflict_count: int
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    created_ids: List[str] = Field(default_factory=list)
    updated_ids: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class ComponentListResponseSchema(BaseModel):
    """Paginated list of catalog components."""
    total: int = Field(..., ge=0, description="Total matching components in catalog")
    items: List[ComponentResponseSchema]
    limit: int = Field(..., ge=1, description="Page size limit")
    offset: int = Field(..., ge=0, description="Page offset")
