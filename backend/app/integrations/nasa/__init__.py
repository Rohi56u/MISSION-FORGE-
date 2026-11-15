"""
NASA Open API Integration Package.
Provides unified clients, models, and error definitions for official NASA Open APIs.
"""

from backend.app.integrations.nasa.client import NasaApiClient, nasa_api_client
from backend.app.integrations.nasa.exceptions import (
    NasaApiAuthError,
    NasaApiError,
    NasaApiNotFoundError,
    NasaApiRateLimitError,
    NasaApiUpstreamError,
)
from backend.app.integrations.nasa.models import (
    ApodItem,
    CoronalMassEjection,
    DonkiCmeResponse,
    NasaKeyVerificationResult,
    NasaRateLimitInfo,
    NearEarthObject,
    NeoFeedResponse,
)

__all__ = [
    "NasaApiClient",
    "nasa_api_client",
    "NasaApiError",
    "NasaApiAuthError",
    "NasaApiNotFoundError",
    "NasaApiRateLimitError",
    "NasaApiUpstreamError",
    "ApodItem",
    "NearEarthObject",
    "NeoFeedResponse",
    "CoronalMassEjection",
    "DonkiCmeResponse",
    "NasaRateLimitInfo",
    "NasaKeyVerificationResult",
]
