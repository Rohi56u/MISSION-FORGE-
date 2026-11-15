"""
NASA TechPort API Endpoints
Provides searchable access to NASA Space Technology Mission Directorate project records and TRLs.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.integrations.techport import (
    TechPortListResponse,
    TechPortNotFoundError,
    TechPortProjectDetail,
    TechPortUpstreamError,
    techport_client,
)

router = APIRouter(prefix="/techport", tags=["NASA TechPort Projects"])


@router.get(
    "/projects",
    response_model=TechPortListResponse,
    status_code=status.HTTP_200_OK,
    summary="List or Search NASA TechPort Projects",
)
async def list_techport_projects(
    search: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=128,
        description="Search keyword in project titles and descriptions",
    ),
    updated_since: Optional[str] = Query(
        default=None,
        description="Filter projects updated since date (YYYY-MM-DD)",
    ),
    allow_stale: bool = Query(default=True),
) -> TechPortListResponse:
    """
    Lists NASA Space Technology Mission Directorate research projects.
    Returns project identifiers, titles, and modification dates.
    """
    try:
        if search:
            return await techport_client.search_projects(search, allow_stale=allow_stale)
        return await techport_client.list_projects(
            updated_since=updated_since, allow_stale=allow_stale
        )
    except TechPortUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NASA TechPort API unavailable: {exc}",
        ) from exc


@router.get(
    "/projects/{project_id}",
    response_model=TechPortProjectDetail,
    status_code=status.HTTP_200_OK,
    summary="Get NASA TechPort Project Details and TRL",
)
async def get_techport_project(
    project_id: int,
    allow_stale: bool = Query(default=True),
) -> TechPortProjectDetail:
    """
    Retrieves detailed NASA TechPort project description, lead center, program, and TRL milestones.
    """
    try:
        return await techport_client.get_project(project_id, allow_stale=allow_stale)
    except TechPortNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TechPortUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NASA TechPort API unavailable: {exc}",
        ) from exc
