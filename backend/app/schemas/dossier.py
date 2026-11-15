"""
Mission Concept Dossier Pydantic Schemas
Mission Forge — Phase 6
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.dossier import DossierFormat, DossierReportStatus


class DossierGenerateRequest(BaseModel):
    """Payload for submitting an asynchronous mission dossier generation job."""
    mission_id: str = Field(
        ..., min_length=1, max_length=64, description="UUID of the target mission"
    )
    room_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional CDF room ID for collaborative revision state",
    )
    design_id: Optional[str] = Field(
        default=None, max_length=64, description="Optional specific spacecraft design UUID"
    )
    format: DossierFormat = Field(
        default=DossierFormat.BOTH, description="Target export format (PDF, JSON, or BOTH)"
    )
    title: Optional[str] = Field(
        default=None, max_length=128, description="Custom title for the mission dossier"
    )
    include_cdf_history: bool = Field(
        default=True, description="Whether to include CDF design decision and revision history"
    )
    include_fdir_audit: bool = Field(
        default=True, description="Whether to include deterministic FDIR anomaly audit trail"
    )
    include_capcom_summary: bool = Field(
        default=True, description="Whether to include grounded CAPCOM AI recommendations"
    )
    trajectory_job_id: Optional[str] = Field(
        default=None, max_length=64, description="Optional solved porkchop trajectory job ID"
    )


class DossierJobResponse(BaseModel):
    """Status and tracking details of a dossier generation background task."""
    job_id: str
    mission_id: str
    status: DossierReportStatus
    format: DossierFormat
    progress_percent: float
    report_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DossierReportMetadataResponse(BaseModel):
    """Metadata, file sizes, SHA-256 hashes, and download links for a compiled dossier."""
    id: str
    job_id: Optional[str] = None
    mission_id: str
    room_id: Optional[str] = None
    design_id: Optional[str] = None
    title: str
    format: str
    pdf_size_bytes: Optional[int] = None
    pdf_sha256: Optional[str] = None
    json_size_bytes: Optional[int] = None
    json_sha256: Optional[str] = None
    schema_version: str
    page_count: int
    created_at: datetime
    download_url_pdf: Optional[str] = None
    download_url_json: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DossierReportListResponse(BaseModel):
    """List of compiled dossier reports for a mission."""
    reports: List[DossierReportMetadataResponse]
    total: int


# --- Typed Frozen Snapshot Schemas ---

class MissionMetadataSnapshot(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    target: str
    mission_class: str
    budget_cap_usd: float
    max_launch_mass_kg: float
    min_delta_v_mps: float
    min_power_margin_percent: float


class SpacecraftDesignSnapshot(BaseModel):
    id: Optional[str] = None
    name: str
    version: int
    dry_mass_kg: float
    wet_mass_kg: float
    propellant_mass_kg: float
    power_draw_w: float
    power_generation_w: float
    delta_v_mps: float
    total_cost_usd: float
    is_feasible: bool
    violations: List[Dict[str, Any]] = Field(default_factory=list)


class SWaPCSnapshot(BaseModel):
    mass_by_subsystem: Dict[str, float]
    power_by_subsystem: Dict[str, float]
    dry_mass_kg: float
    wet_mass_kg: float
    propellant_mass_kg: float
    mass_margin_percent: float
    power_draw_w: float
    power_generation_w: float
    power_margin_percent: float
    total_cost_usd: float
    cost_margin_percent: float
    delta_v_mps: float
    delta_v_margin_percent: float
    assumptions: List[str]


class ComponentLedgerEntrySnapshot(BaseModel):
    id: Optional[str] = None
    name: str
    subsystem: str
    mass_kg: float
    power_draw_w: float
    cost_usd: float
    trl: Optional[int] = None
    flight_heritage: Optional[str] = None
    verification_status: str
    source_system: str
    field_provenance: Dict[str, Any] = Field(default_factory=dict)
    is_estimated: bool = False


class TrajectorySnapshot(BaseModel):
    origin_body: str
    target_body: str
    departure_epoch: Optional[str] = None
    arrival_epoch: Optional[str] = None
    time_of_flight_days: Optional[float] = None
    c3_km2_s2: Optional[float] = None
    total_delta_v_mps: Optional[float] = None
    arrival_v_inf_mps: Optional[float] = None
    solver_name: str
    ephemeris_source: str
    coordinate_frame: str
    time_scale: str
    status: str
    astrodynamics_disclaimer: str


class TelecomSnapshot(BaseModel):
    ground_network: str
    dsn_stations: List[str]
    carrier_frequency_band: str
    carrier_frequency_hz: float
    tx_power_w: float
    antenna_diameter_m: float
    distance_au: float
    space_loss_db: float
    received_power_dbm: float
    downlink_rate_bps: float
    link_margin_db: float
    dsn_feed_status: str


class DossierFrozenSnapshot(BaseModel):
    """
    Authoritative, mathematically reproducible frozen mission dossier snapshot.
    Guarantees that a later edit to the database never alters the historical report.
    """
    schema_version: str = "1.0.0"
    software_version: str
    snapshot_timestamp_utc: str
    canonical_hash_sha256: Optional[str] = None
    authoritative_disclaimer: str
    title: str = "Mission Concept Dossier"
    compiled_by_user: Optional[Dict[str, Any]] = None
    mission: MissionMetadataSnapshot
    design: SpacecraftDesignSnapshot
    swapc: SWaPCSnapshot
    components: List[ComponentLedgerEntrySnapshot]
    trajectory: TrajectorySnapshot
    telecommunications: TelecomSnapshot
    cdf: Dict[str, Any] = Field(default_factory=dict)
    fdir: Dict[str, Any] = Field(default_factory=dict)
    capcom: Dict[str, Any] = Field(default_factory=dict)
    editorial_disclosures: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
