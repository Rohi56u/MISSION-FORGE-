"""
Exceptions for NASA Deep Space Network (DSN) Now Adapter
"""


class DSNError(Exception):
    """Base exception for NASA DSN operations."""
    pass


class DSNParseError(DSNError):
    """Raised when XML parsing fails or expected feed structure is invalid."""
    pass


class DSNUpstreamError(DSNError):
    """Raised when DSN feed connection fails or HTTP request errors."""
    pass
