"""
Pydantic Models for NASA Open API Gateway Integration.
Includes Astronomy Picture of the Day (APOD), Near-Earth Objects (NEOWs),
Space Weather (DONKI CME), and Rate Limit Telemetry.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.cache import CacheStatus


class NasaRateLimitInfo(BaseModel):
    """NASA API Gateway rate limit status and quota tracking."""
    model_config = ConfigDict(extra="ignore")

    limit: Optional[int] = Field(
        default=None, description="Hourly request quota allocated to key"
    )
    remaining: Optional[int] = Field(
        default=None, description="Remaining requests in current hourly window"
    )
    last_checked: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApodItem(BaseModel):
    """NASA Astronomy Picture of the Day (APOD) metadata."""
    model_config = ConfigDict(extra="ignore")

    date: str = Field(..., description="Date of the imagery (YYYY-MM-DD)")
    title: str = Field(..., description="Title of the astronomical feature")
    explanation: str = Field(..., description="Professional narrative explanation")
    url: str = Field(..., description="URL of the standard resolution image or video")
    hdurl: Optional[str] = Field(
        default=None, description="URL of high-definition imagery if available"
    )
    media_type: str = Field(default="image", description="Media type: image, video, etc.")
    service_version: Optional[str] = Field(
        default=None, description="NASA APOD API service version"
    )
    copyright: Optional[str] = Field(default=None, description="Copyright holder if applicable")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_status: CacheStatus = CacheStatus.LIVE


class NearEarthObject(BaseModel):
    """Near-Earth Asteroid / Comet tracking data from NASA NeoWS."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="NASA JPL NEO identifier")
    name: str = Field(..., description="Designation name of the celestial body")
    absolute_magnitude_h: Optional[float] = Field(
        default=None, description="Absolute visual magnitude H"
    )
    estimated_diameter_min_km: Optional[float] = Field(
        default=None, description="Estimated min diameter in km"
    )
    estimated_diameter_max_km: Optional[float] = Field(
        default=None, description="Estimated max diameter in km"
    )
    is_potentially_hazardous: bool = Field(
        default=False, description="Whether designated potentially hazardous asteroid (PHA)"
    )
    close_approach_date: Optional[str] = Field(
        default=None, description="Close approach epoch date (YYYY-MM-DD)"
    )
    miss_distance_km: Optional[float] = Field(
        default=None, description="Miss distance from Earth in kilometers"
    )
    relative_velocity_km_s: Optional[float] = Field(
        default=None, description="Relative velocity in km/s"
    )


class NeoFeedResponse(BaseModel):
    """Aggregated Near-Earth Object feed across an observational window."""
    model_config = ConfigDict(extra="ignore")

    element_count: int = Field(..., description="Total celestial objects tracked in interval")
    near_earth_objects: List[NearEarthObject] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_status: CacheStatus = CacheStatus.LIVE


class CoronalMassEjection(BaseModel):
    """NASA DONKI Coronal Mass Ejection (CME) solar event."""
    model_config = ConfigDict(extra="ignore")

    activity_id: str = Field(..., description="DONKI CME activity ID")
    catalog: Optional[str] = Field(default=None, description="Catalog classification")
    start_time: str = Field(..., description="Start epoch of the solar event")
    source_location: Optional[str] = Field(
        default=None, description="Solar heliographic coordinates"
    )
    note: Optional[str] = Field(default=None, description="Scientific notes on the eruption")
    instruments: List[str] = Field(
        default_factory=list, description="Observational instruments detecting event"
    )


class DonkiCmeResponse(BaseModel):
    """NASA Space Weather DONKI CME event summary."""
    model_config = ConfigDict(extra="ignore")

    count: int = Field(..., description="Total CME events in date range")
    events: List[CoronalMassEjection] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_status: CacheStatus = CacheStatus.LIVE


class NasaKeyVerificationResult(BaseModel):
    """Comprehensive diagnostic result of live NASA API key validation."""
    model_config = ConfigDict(extra="ignore")

    valid: bool = Field(..., description="Whether API key passed live authentication")
    api_key_masked: str = Field(..., description="Masked key string for secure logging")
    rate_limit: Optional[int] = Field(default=None, description="Confirmed hourly request limit")
    rate_limit_remaining: Optional[int] = Field(
        default=None, description="Confirmed remaining quota"
    )
    status_code: int = Field(..., description="HTTP response status code")
    message: str = Field(..., description="Diagnostic assessment")
    endpoints_verified: List[str] = Field(
        default_factory=list, description="List of NASA API endpoints validated"
    )
    tested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_sample: Optional[Dict[str, Any]] = Field(
        default=None, description="Sample verified payload"
    )
