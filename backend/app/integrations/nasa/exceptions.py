"""
Exceptions for NASA Open API Gateway Integration.
"""


class NasaApiError(Exception):
    """Base exception for NASA Open API client errors."""
    pass


class NasaApiAuthError(NasaApiError):
    """Raised when NASA API returns 401 Unauthorized or 403 Forbidden (invalid API key)."""
    pass


class NasaApiRateLimitError(NasaApiError):
    """Raised when NASA API returns 429 Too Many Requests (rate limit exhausted)."""
    pass


class NasaApiNotFoundError(NasaApiError):
    """Raised when requested NASA resource returns 404 Not Found."""
    pass


class NasaApiUpstreamError(NasaApiError):
    """Raised when NASA API returns 5xx server error or network connectivity fails."""
    pass
