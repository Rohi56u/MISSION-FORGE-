"""
Pydantic Models for NASA TechPort Integration
Models official NASA Technology Port projects, programs, and TRL milestones.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.cache import CacheStatus


class TechPortProjectSummary(BaseModel):
    """Concise representation of a NASA TechPort project from listing/search."""
    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., description="NASA TechPort numeric project ID")
    title: str = Field(..., description="Project title")
    last_updated: Optional[str] = Field(
        default=None, description="Date string of last modification"
    )


class TechPortProjectDetail(BaseModel):
    """
    Detailed NASA TechPort project record.
    Captures NASA technology programs, lead centers, descriptions, and TRL progression.
    Note: TechPort records represent R&D initiatives, NOT hardware flight parts.
    """
    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., description="NASA TechPort numeric project ID")
    title: str = Field(..., description="Project title")
    status: Optional[str] = Field(
        default=None, description="Project lifecycle status (e.g. Active, Completed)"
    )
    description: Optional[str] = Field(
        default=None, description="Detailed technology description"
    )
    benefits: Optional[str] = Field(
        default=None, description="Anticipated aerospace mission benefits"
    )
    lead_organization: Optional[str] = Field(
        default=None, description="Lead NASA center or commercial entity"
    )
    program: Optional[str] = Field(
        default=None, description="Funding NASA directorate/program"
    )

    trl_begin: Optional[int] = Field(
        default=None, ge=1, le=9, description="Initial TRL level (1-9)"
    )
    trl_current: Optional[int] = Field(
        default=None, ge=1, le=9, description="Current assessed TRL level (1-9)"
    )
    trl_end: Optional[int] = Field(
        default=None, ge=1, le=9, description="Target completion TRL level (1-9)"
    )

    last_updated: Optional[str] = Field(default=None, description="Last update date")
    canonical_url: str = Field(..., description="Canonical NASA TechPort portal URL")
    primary_taxonomy: Optional[str] = Field(
        default=None, description="NASA Technology Taxonomy classification"
    )
    raw_payload: Dict[str, Any] = Field(
        default_factory=dict, description="Raw upstream JSON response"
    )
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_status: CacheStatus = CacheStatus.LIVE
    rate_limit: Optional[int] = Field(
        default=None, description="NASA API rate limit quota"
    )
    rate_limit_remaining: Optional[int] = Field(
        default=None, description="NASA API remaining quota"
    )


class TechPortListResponse(BaseModel):
    """Paginated list of NASA TechPort projects."""
    model_config = ConfigDict(extra="ignore")

    total_count: int = Field(..., description="Total matching projects in TechPort database")
    projects: List[TechPortProjectSummary] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_status: CacheStatus = CacheStatus.LIVE
    rate_limit: Optional[int] = Field(
        default=None, description="NASA API rate limit quota"
    )
    rate_limit_remaining: Optional[int] = Field(
        default=None, description="NASA API remaining quota"
    )
    source_url: str
