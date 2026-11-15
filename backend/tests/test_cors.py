"""
CORS Security Configuration Tests
Verifies origin allowlist enforcement, credential handling, and preflight behavior.
"""

import pytest
from httpx import AsyncClient
from backend.app.core.config import Settings


@pytest.mark.asyncio
async def test_cors_allowed_origin_regular_request(async_client: AsyncClient):
    """Requests from an allowed origin receive matching Access-Control headers."""
    allowed_origin = "http://localhost:3000"
    response = await async_client.get(
        "/health",
        headers={"Origin": allowed_origin},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_allowed_origin_preflight(async_client: AsyncClient):
    """Preflight OPTIONS request from allowed origin returns permitted methods."""
    allowed_origin = "http://localhost:5173"
    response = await async_client.options(
        "/api/v1/physics/tsiolkovsky",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin
    assert response.headers.get("access-control-allow-credentials") == "true"
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods


@pytest.mark.asyncio
async def test_cors_untrusted_origin_rejected(async_client: AsyncClient):
    """Requests from untrusted origins MUST NOT receive Access-Control headers."""
    untrusted_origin = "http://evil-attacker.com"
    response = await async_client.get(
        "/health",
        headers={"Origin": untrusted_origin},
    )
    assert response.status_code == 200
    # Must NOT reflect the untrusted origin
    assert response.headers.get("access-control-allow-origin") != untrusted_origin
    assert response.headers.get("access-control-allow-origin") is None


@pytest.mark.asyncio
async def test_cors_untrusted_origin_preflight_rejected(async_client: AsyncClient):
    """Preflight OPTIONS from untrusted origin does NOT grant CORS access."""
    untrusted_origin = "http://malicious-site.org"
    response = await async_client.options(
        "/api/v1/physics/tsiolkovsky",
        headers={
            "Origin": untrusted_origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_settings_rejects_wildcard_with_credentials():
    """Settings validator must reject '*' in CORS_ORIGINS when credentials enabled."""
    with pytest.raises(ValueError, match="Insecure CORS configuration.*Wildcard '\\*'"):
        Settings(CORS_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=True)


def test_cors_settings_parses_comma_separated_env_string():
    """Settings must properly parse comma-separated origin strings."""
    s = Settings(CORS_ORIGINS="http://site1.com, http://site2.com")
    assert s.CORS_ORIGINS == ["http://site1.com", "http://site2.com"]


def test_cors_settings_strips_trailing_slashes():
    """Origins with trailing slashes must be normalized to prevent browser mismatch."""
    s = Settings(CORS_ORIGINS="http://localhost:3000/, https://app.example.com/")
    assert s.CORS_ORIGINS == ["http://localhost:3000", "https://app.example.com"]


def test_cors_settings_rejects_null_origin():
    """Origins list containing 'null' must be rejected when credentials are enabled."""
    with pytest.raises(ValueError, match="Insecure CORS configuration.*'null'"):
        Settings(CORS_ORIGINS=["null"], CORS_ALLOW_CREDENTIALS=True)


def test_cors_settings_rejects_malformed_origin():
    """Malformed origins without scheme or netloc must raise ValueError."""
    with pytest.raises(ValueError, match="Malformed CORS origin"):
        Settings(CORS_ORIGINS=["not-a-valid-url"])
    with pytest.raises(ValueError, match="Malformed CORS origin"):
        Settings(CORS_ORIGINS=["ftp://invalid-scheme.com"])
