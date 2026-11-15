"""
Unit and Integration Tests for NASA TechPort Adapter and API
Tests project listing, search, project details, TRL milestones,
caching, error handling, and FastAPI endpoints.
"""

import json
from pathlib import Path
import pytest
from httpx import AsyncClient, MockTransport, Response

from backend.app.core.cache import CacheStatus
from backend.app.integrations.techport import (
    TechPortClient,
    TechPortListResponse,
    TechPortNotFoundError,
    TechPortProjectDetail,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def techport_detail_fixture() -> dict:
    with open(FIXTURES_DIR / "techport_project_10024.json", encoding="utf-8") as f:
        return json.load(f)


# =========================================================================
# 1. CLIENT TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_techport_get_project_detail(techport_detail_fixture):
    """Retrieves and parses detailed TechPort project specifications."""
    def handler(request):
        return Response(200, json=techport_detail_fixture)

    client = TechPortClient(transport=MockTransport(handler))
    try:
        project = await client.get_project(10024)
        assert isinstance(project, TechPortProjectDetail)
        assert project.id == 10024
        assert "Antenna Arrays" in project.title
        assert project.lead_organization == "Glenn Research Center"
        assert "Small Business Innovation" in (project.program or "")
        assert project.canonical_url == "https://techport.nasa.gov/view/10024"
        assert project.cache_status == CacheStatus.LIVE
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_techport_project_not_found():
    """Requesting non-existent project raises TechPortNotFoundError."""
    def handler(request):
        return Response(404, json={"error": "Not Found"})

    client = TechPortClient(transport=MockTransport(handler))
    try:
        with pytest.raises(TechPortNotFoundError):
            await client.get_project(999999)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_techport_client_caching(techport_detail_fixture):
    """Subsequent requests within TTL are served from cache."""
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return Response(200, json=techport_detail_fixture)

    client = TechPortClient(
        transport=MockTransport(handler),
        cache_ttl_seconds=300.0,
    )
    try:
        p1 = await client.get_project(10024)
        assert p1.cache_status == CacheStatus.LIVE
        assert calls == 1

        p2 = await client.get_project(10024)
        assert p2.cache_status == CacheStatus.CACHED
        assert calls == 1  # Served from cache without network hit
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_techport_search_projects():
    """Searches TechPort projects by keyword."""
    def handler(request):
        return Response(
            200,
            json={
                "projects": [
                    {"id": 10024, "title": "Flexible Radar Antenna Arrays"},
                    {"id": 17793, "title": "NEXT-C Flight Demonstration"},
                ],
                "totalCount": 2,
            },
        )

    client = TechPortClient(transport=MockTransport(handler))
    try:
        result = await client.search_projects("NEXT-C")
        assert isinstance(result, TechPortListResponse)
        assert result.total_count == 2
        assert len(result.projects) == 2
        assert result.projects[0].id == 10024
    finally:
        await client.aclose()


# =========================================================================
# 2. FASTAPI ROUTE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_api_techport_get_project(
    async_client: AsyncClient,
    techport_detail_fixture,
    monkeypatch,
):
    """GET /api/v1/techport/projects/{id} returns 200 with project metadata."""
    from backend.app.api.v1.techport import techport_client

    async def mock_get(pid, allow_stale=True):
        return TechPortProjectDetail(
            id=pid,
            title="Flexible Radar Antenna Arrays",
            lead_organization="Glenn Research Center",
            canonical_url=f"https://techport.nasa.gov/view/{pid}",
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(techport_client, "get_project", mock_get)

    response = await async_client.get("/api/v1/techport/projects/10024")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 10024
    assert data["lead_organization"] == "Glenn Research Center"


@pytest.mark.asyncio
async def test_api_techport_project_not_found(
    async_client: AsyncClient,
    monkeypatch,
):
    """Non-existent project ID returns 404 Not Found."""
    from backend.app.api.v1.techport import techport_client

    async def mock_not_found(pid, allow_stale=True):
        raise TechPortNotFoundError(f"Project '{pid}' not found")

    monkeypatch.setattr(techport_client, "get_project", mock_not_found)

    response = await async_client.get("/api/v1/techport/projects/999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_techport_list_and_search(
    async_client: AsyncClient,
    monkeypatch,
):
    """GET /api/v1/techport/projects with search query returns matching list."""
    from backend.app.api.v1.techport import techport_client
    from backend.app.integrations.techport.models import TechPortProjectSummary

    async def mock_search(q, allow_stale=True):
        return TechPortListResponse(
            total_count=1,
            projects=[TechPortProjectSummary(id=17793, title="NEXT-C Demonstration")],
            source_url="http://mock-techport",
            cache_status=CacheStatus.LIVE,
        )

    monkeypatch.setattr(techport_client, "search_projects", mock_search)

    response = await async_client.get("/api/v1/techport/projects?search=NEXT-C")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["projects"][0]["id"] == 17793
