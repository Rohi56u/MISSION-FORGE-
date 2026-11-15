"""
Pydantic Models for NASA Deep Space Network (DSN) Now Real-Time Feed
Models antenna dish tracking, station complexes, carrier signals, and telemetry targets.
"""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.cache import CacheStatus


class DSNSignal(BaseModel):
    """Deep space radio frequency carrier or data signal (uplink/downlink)."""
    model_config = ConfigDict(extra="ignore")

    active: bool = Field(default=False, description="Whether signal carrier is actively tracked")
    signal_type: Optional[str] = Field(default=None, description="Signal type: data, carrier, none")
    data_rate_bps: Optional[float] = Field(default=None, description="Data rate in bits per second")
    frequency_hz: Optional[float] = Field(default=None, description="RF carrier frequency in Hertz")
    band: Optional[str] = Field(default=None, description="RF Band: X, S, Ka, etc.")
    power_dbm_or_kw: Optional[float] = Field(
        default=None,
        description="Received power (dBm) for downSignal or Tx power (kW) for upSignal",
    )
    spacecraft: Optional[str] = Field(default=None, description="Spacecraft mission callsign/code")
    spacecraft_id: Optional[str] = Field(default=None, description="NASA DSN spacecraft identifier")


class DSNTarget(BaseModel):
    """Spacecraft or celestial target currently being tracked by a DSN antenna."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Target name or spacecraft code (e.g. M01O, JWST, PER)")
    target_id: Optional[str] = Field(default=None, description="DSN target numeric identifier")
    upleg_range_km: Optional[float] = Field(
        default=None, description="Uplink range distance from station in kilometers"
    )
    downleg_range_km: Optional[float] = Field(
        default=None, description="Downlink range distance to station in kilometers"
    )
    rtlt_seconds: Optional[float] = Field(
        default=None, description="Round-Trip Light Time in seconds"
    )


class DSNDish(BaseModel):
    """Individual deep-space ground station parabolic dish antenna."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Dish identifier (e.g. DSS14, DSS25, DSS43, DSS65)")
    azimuth_deg: Optional[float] = Field(
        default=None, description="Antenna azimuth pointing angle in degrees (0-360)"
    )
    elevation_deg: Optional[float] = Field(
        default=None, description="Antenna elevation pointing angle in degrees (0-90)"
    )
    wind_speed_kmh: Optional[float] = Field(
        default=None, description="Local ground wind speed in km/h at antenna site"
    )
    is_mspa: bool = Field(
        default=False, description="Multiple Spacecraft Per Aperture tracking active"
    )
    is_array: bool = Field(
        default=False, description="Whether antenna is arrayed with other dishes"
    )
    is_ddor: bool = Field(
        default=False, description="Delta Differential One-Way Ranging active"
    )
    activity: Optional[str] = Field(
        default=None, description="Operational activity description"
    )
    targets: List[DSNTarget] = Field(default_factory=list)
    up_signals: List[DSNSignal] = Field(default_factory=list)
    down_signals: List[DSNSignal] = Field(default_factory=list)


class DSNStation(BaseModel):
    """Deep Space Communications Complex (Goldstone, Madrid, or Canberra)."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Complex code: gdscc, mdscc, cdscc")
    friendly_name: str = Field(..., description="Full facility name: Goldstone, Madrid, Canberra")
    time_utc: int = Field(..., description="Site time in UTC milliseconds")
    time_zone_offset_ms: float = Field(..., description="Timezone offset in milliseconds")
    dishes: List[DSNDish] = Field(default_factory=list)


class DSNFeedResponse(BaseModel):
    """Normalized response from NASA DSN Now official feed."""
    model_config = ConfigDict(extra="ignore")

    stations: List[DSNStation] = Field(default_factory=list)
    timestamp_ms: Optional[int] = Field(default=None, description="Feed generation timestamp")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_timestamp: Optional[datetime] = Field(
        default=None, description="Timestamp extracted directly from feed metadata"
    )
    cache_status: CacheStatus = CacheStatus.LIVE
    source_url: str
    active_tracking_count: int = Field(
        default=0, description="Total number of dishes currently tracking active missions"
    )
    tracked_spacecraft: List[str] = Field(
        default_factory=list, description="Unique list of spacecraft codes currently tracked"
    )


class DSNSpacecraftContact(BaseModel):
    """Active contact details between a specific DSN ground dish and a spacecraft."""
    model_config = ConfigDict(extra="ignore")

    station_name: str = Field(..., description="Station complex code (gdscc, mdscc, cdscc)")
    station_friendly_name: str = Field(..., description="Full station complex facility name")
    dish_name: str = Field(..., description="Antenna dish identifier (e.g. DSS14, DSS43)")
    activity: Optional[str] = Field(default=None, description="Operational activity description")
    azimuth_deg: Optional[float] = Field(
        default=None, description="Antenna azimuth pointing angle in degrees"
    )
    elevation_deg: Optional[float] = Field(
        default=None, description="Antenna elevation pointing angle in degrees"
    )
    wind_speed_kmh: Optional[float] = Field(
        default=None, description="Wind speed at dish (km/h)"
    )
    is_mspa: bool = False
    is_array: bool = False
    is_ddor: bool = False
    target: Optional[DSNTarget] = None
    up_signals: List[DSNSignal] = Field(default_factory=list)
    down_signals: List[DSNSignal] = Field(default_factory=list)


class DSNSpacecraftTrackingResponse(BaseModel):
    """Spacecraft-specific tracking status filtered across all DSN ground stations."""
    model_config = ConfigDict(extra="ignore")

    spacecraft: str = Field(..., description="Spacecraft code (e.g. M01O, MRO, JWST, VGR1)")
    is_actively_tracked: bool = Field(
        ..., description="Whether currently tracked by at least one antenna dish"
    )
    contacts: List[DSNSpacecraftContact] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_timestamp: Optional[datetime] = None
    cache_status: CacheStatus = CacheStatus.LIVE
    source_url: str
