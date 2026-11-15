"""
Exceptions for NASA/JPL Horizons Client & Parser
"""

from typing import List, Optional
from backend.app.integrations.horizons.models import HorizonsTargetCandidate


class HorizonsError(Exception):
    """Base exception for all JPL Horizons operations."""
    pass


class HorizonsValidationError(HorizonsError):
    """Raised when query parameters are rejected by client or upstream validation."""
    pass


class HorizonsTargetNotFoundError(HorizonsError):
    """Raised when Horizons reports no matching celestial body or spacecraft."""
    pass


class HorizonsAmbiguousTargetError(HorizonsError):
    """
    Raised when a target identifier matches multiple bodies in the Horizons catalog.
    Provides structured candidates with IDs and designations.
    """

    def __init__(
        self,
        message: str,
        candidates: Optional[List[HorizonsTargetCandidate]] = None,
    ) -> None:
        super().__init__(message)
        self.candidates = candidates or []


class HorizonsParseError(HorizonsError):
    """Raised when upstream Horizons response cannot be parsed."""
    pass


class HorizonsUpstreamError(HorizonsError):
    """Raised on upstream connection failure, 5xx error, or retry exhaustion."""
    pass
