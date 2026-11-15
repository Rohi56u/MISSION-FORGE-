"""
Exceptions for NASA TechPort Client
"""


class TechPortError(Exception):
    """Base exception for NASA TechPort operations."""
    pass


class TechPortNotFoundError(TechPortError):
    """Raised when requested TechPort project ID is not found."""
    pass


class TechPortUpstreamError(TechPortError):
    """Raised on upstream TechPort connection or 5xx server failure."""
    pass
