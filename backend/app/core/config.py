"""
Mission Forge Core Configuration
Provides type-safe environment configuration using Pydantic Settings.
"""

from typing import List, Optional, Union
import json
from urllib.parse import urlparse
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable fallbacks."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Mission Forge Aerospace API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment: development, test, production",
    )
    DEBUG: bool = Field(default=True, description="Debug mode")

    # Security & CORS
    SECRET_KEY: str = Field(
        default="mission-forge-dev-secret-key-change-in-production-2026",
        description="JWT secret key",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Explicit allowlist of allowed CORS origins (Wildcard '*' is forbidden with credentials)
    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        description="Explicit allowed CORS origins",
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = [
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "OPTIONS",
        "HEAD",
    ]
    CORS_ALLOW_HEADERS: List[str] = [
        "Content-Type",
        "Authorization",
        "Accept",
        "X-Requested-With",
    ]
    CORS_EXPOSE_HEADERS: List[str] = ["Content-Length"]
    CORS_MAX_AGE: int = 600

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """
        Parses, normalizes, and validates CORS origins.
        Enforces:
          - Rejects wildcard '*' when credentials are enabled.
          - Rejects 'null' origin when credentials are enabled.
          - Normalizes origins by removing trailing slashes (RFC 6454).
          - Validates that each entry is an explicit HTTP/HTTPS origin.
        """
        raw_origins: List[str] = []
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                try:
                    parsed = json.loads(v_stripped)
                    if isinstance(parsed, list):
                        raw_origins = [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    raw_origins = [item.strip() for item in v.split(",") if item.strip()]
            else:
                raw_origins = [item.strip() for item in v.split(",") if item.strip()]
        elif isinstance(v, list):
            raw_origins = [str(item).strip() for item in v if str(item).strip()]
        else:
            raw_origins = []

        # Reject dangerous origins
        for item in raw_origins:
            if item == "*":
                raise ValueError(
                    "Insecure CORS configuration: Wildcard '*' cannot be used as an origin "
                    "when credentials are enabled. Configure explicit trusted origins."
                )
            if item.lower() == "null":
                raise ValueError(
                    "Insecure CORS configuration: 'null' cannot be used as an allowed origin "
                    "when credentials are enabled."
                )

        normalized_origins: List[str] = []
        for origin in raw_origins:
            # Strip trailing slashes to adhere to browser Origin header format
            cleaned = origin.rstrip("/")
            parsed = urlparse(cleaned)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(
                    f"Malformed CORS origin '{origin}': must be a valid absolute URI "
                    "with http or https scheme and host (e.g. 'http://localhost:3000')."
                )
            # Reconstruct origin without path, query, or fragment
            clean_origin = f"{parsed.scheme}://{parsed.netloc}"
            if clean_origin not in normalized_origins:
                normalized_origins.append(clean_origin)

        if not normalized_origins:
            # Safe default fallback for development
            normalized_origins = [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]

        return normalized_origins

    # Catalog & Security Boundaries
    ALLOW_CATALOG_MUTATION_WITHOUT_AUTH: bool = Field(
        default=True,
        description=(
            "Allow unauthenticated catalog additions in development/test. "
            "Must be False in production."
        ),
    )

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./mission_forge.db",
        description="Async SQLAlchemy database URL (SQLite for local/CI, PostgreSQL for prod)",
    )
    DATABASE_ECHO: bool = False

    # External APIs & Adapters (Phase 2)
    NASA_API_KEY: str = Field(default="DEMO_KEY", description="NASA Open API Key")
    NASA_API_BASE_URL: str = Field(
        default="https://api.nasa.gov",
        description="Official NASA Open API gateway base URL",
    )
    HORIZONS_API_BASE_URL: str = Field(
        default="https://ssd.jpl.nasa.gov/api/horizons.api",
        description="Official JPL SSD Horizons API endpoint",
    )
    DSN_FEED_URL: str = Field(
        default="https://eyes.nasa.gov/dsn/data/dsn.xml",
        description="Official NASA DSN Now live XML feed",
    )
    TECHPORT_API_BASE_URL: str = Field(
        default="https://techport.nasa.gov/api",
        description="NASA TechPort official REST API base URL",
    )
    EXTERNAL_API_TIMEOUT_SECONDS: float = Field(
        default=15.0, description="HTTP client total timeout in seconds"
    )
    EXTERNAL_API_MAX_RETRIES: int = Field(
        default=3, description="Maximum bounded retries for transient HTTP errors"
    )
    EXTERNAL_API_BACKOFF_FACTOR: float = Field(
        default=0.5, description="Exponential backoff factor in seconds"
    )
    HORIZONS_CACHE_TTL_SECONDS: int = Field(
        default=86400, description="JPL Horizons ephemeris cache TTL (24 hours)"
    )
    DSN_CACHE_TTL_SECONDS: int = Field(
        default=15, description="DSN Now feed cache TTL (15 seconds)"
    )
    TECHPORT_CACHE_TTL_SECONDS: int = Field(
        default=3600, description="NASA TechPort cache TTL (1 hour)"
    )
    HTTP_USER_AGENT: str = Field(
        default=(
            "MissionForge/1.0 "
            "(+https://github.com/nasa-space-apps-2026/mission-forge; "
            "contact: team@missionforge.org)"
        ),
        description="User-Agent header for external aerospace APIs",
    )

    GEMINI_API_KEY: Optional[str] = Field(
        default=None, description="Google Gemini API Key for CAPCOM AI"
    )
    GEMINI_MODEL: str = Field(
        default="gemini-3.5-flash-lite", description="Gemini model identifier"
    )

    # Distributed Pub/Sub Broker (Redis)
    REDIS_URL: Optional[str] = Field(
        default=None,
        description="Redis URL for distributed pub/sub broker (e.g. redis://localhost:6379/0)",
    )

    # Trajectory & Solver Defaults
    LAMBERT_MAX_ITERATIONS: int = 100
    LAMBERT_TOLERANCE: float = 1e-6
    PORKCHOP_DEFAULT_GRID_SIZE: int = 30

    # Phase 6: Mission Dossier & Artifact Storage
    DOSSIER_STORAGE_DIR: str = Field(
        default="artifacts/dossiers",
        description="Persistent directory path for mission dossier artifacts (PDF, JSON)",
    )
    DOSSIER_MAX_CONCURRENT_JOBS: int = Field(
        default=2,
        description="Bounded concurrency limit for asynchronous dossier generation jobs",
    )
    DOSSIER_RETENTION_DAYS: int = Field(
        default=30,
        description="Retention window in days for generated dossier artifacts",
    )
    DOSSIER_MAX_TITLE_LENGTH: int = Field(
        default=128,
        description="Maximum character length for custom mission dossier title",
    )
    MAX_REQUEST_BODY_BYTES: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum request body size in bytes (10 MB) to prevent denial-of-service",
    )
    MAX_DOSSIER_DOWNLOAD_BYTES: int = Field(
        default=50 * 1024 * 1024,
        description="Maximum allowable download size in bytes for dossier artifacts (50 MB)",
    )
    DOSSIER_RATE_LIMIT_GENERATE_PER_MINUTE: int = Field(
        default=10,
        description="Maximum dossier generation requests allowed per minute per user",
    )
    DOSSIER_RATE_LIMIT_DOWNLOAD_PER_MINUTE: int = Field(
        default=30,
        description="Maximum dossier download requests allowed per minute per user",
    )

    # Mandatory Firebase Authentication Integration
    FIREBASE_PROJECT_ID: Optional[str] = Field(
        default=None,
        description="Firebase Project ID for token verification (e.g. mission-forge-2026)",
    )
    FIREBASE_CREDENTIALS_PATH: Optional[str] = Field(
        default=None,
        description="Optional path to Firebase service account JSON key file",
    )
    FIREBASE_CLIENT_EMAIL: Optional[str] = Field(
        default=None,
        description="Firebase service account client email",
    )
    FIREBASE_PRIVATE_KEY: Optional[str] = Field(
        default=None,
        description="Firebase service account private key (PEM format)",
    )

    # Mandatory Supabase Integration (PostgreSQL & Object Storage)
    SUPABASE_URL: Optional[str] = Field(
        default=None,
        description="Supabase project URL (e.g. https://xyz.supabase.co)",
    )
    SUPABASE_KEY: Optional[str] = Field(
        default=None,
        description="Supabase anon or service-role key (server-side only)",
    )
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = Field(
        default=None,
        description="Supabase service role key for administrative storage operations",
    )
    SUPABASE_STORAGE_BUCKET: str = Field(
        default="dossiers",
        description="Supabase Storage private bucket for mission dossier artifacts",
    )
    SUPABASE_STORAGE_EXPIRING_URL_SECONDS: int = Field(
        default=3600,
        description="Expiration time in seconds for signed dossier download URLs (default 1 hour)",
    )

    @model_validator(mode="after")
    def enforce_production_security(self) -> "Settings":
        """
        Guarantees that production environments cannot bypass catalog mutation security.
        Forces ALLOW_CATALOG_MUTATION_WITHOUT_AUTH to False if ENVIRONMENT is production.
        """
        if self.ENVIRONMENT == "production":
            self.ALLOW_CATALOG_MUTATION_WITHOUT_AUTH = False
        return self


settings = Settings()
