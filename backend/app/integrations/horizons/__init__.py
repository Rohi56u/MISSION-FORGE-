"""
NASA/JPL Horizons Ephemeris Integration Package
"""

from backend.app.integrations.horizons.client import HorizonsClient, horizons_client
from backend.app.integrations.horizons.exceptions import (
    HorizonsAmbiguousTargetError,
    HorizonsError,
    HorizonsParseError,
    HorizonsTargetNotFoundError,
    HorizonsUpstreamError,
    HorizonsValidationError,
)
from backend.app.integrations.horizons.models import (
    HorizonsElementEntry,
    HorizonsEphemType,
    HorizonsQueryRequest,
    HorizonsQueryResponse,
    HorizonsRefPlane,
    HorizonsRefSystem,
    HorizonsTargetCandidate,
    HorizonsTimeScale,
    HorizonsVectorEntry,
    Vector3D,
)
from backend.app.integrations.horizons.parser import (
    parse_ambiguous_targets,
    parse_horizons_response,
)

__all__ = [
    "HorizonsClient",
    "horizons_client",
    "HorizonsError",
    "HorizonsValidationError",
    "HorizonsTargetNotFoundError",
    "HorizonsAmbiguousTargetError",
    "HorizonsParseError",
    "HorizonsUpstreamError",
    "HorizonsQueryRequest",
    "HorizonsQueryResponse",
    "HorizonsEphemType",
    "HorizonsRefPlane",
    "HorizonsRefSystem",
    "HorizonsTimeScale",
    "Vector3D",
    "HorizonsVectorEntry",
    "HorizonsElementEntry",
    "HorizonsTargetCandidate",
    "parse_horizons_response",
    "parse_ambiguous_targets",
]
