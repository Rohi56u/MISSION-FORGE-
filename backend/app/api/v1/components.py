"""
Component Catalog API Endpoints
Provides persistent querying, filtering, pagination, and registration of
flight-proven aerospace components.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.app.catalog.sync import catalog_sync_service
from backend.app.core.auth import get_current_user_optional
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.models.auth import User
from backend.app.models.component import (
    Component,
    SubsystemType,
    VerificationStatus,
)
from backend.app.schemas.component import (
    CatalogStatusResponseSchema,
    CatalogSyncRequestSchema,
    CatalogSyncSummarySchema,
    ComponentCreateSchema,
    ComponentProvenanceResponseSchema,
    ComponentResponseSchema,
    ComponentListResponseSchema,
    SyncUpdatePolicy,
)

router = APIRouter(prefix="/components", tags=["Component Catalog"])


@router.get("", response_model=ComponentListResponseSchema, status_code=status.HTTP_200_OK)
async def list_components(
    subsystem: Optional[SubsystemType] = Query(
        default=None, description="Filter by subsystem"
    ),
    verification_status: Optional[VerificationStatus] = Query(
        default=None, description="Filter by verification confidence"
    ),
    min_trl: Optional[int] = Query(
        default=None, ge=1, le=9, description="Minimum TRL level (1-9)"
    ),
    search: Optional[str] = Query(
        default=None, max_length=64, description="Search by component name"
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves a paginated list of catalog components with validated filters.
    """
    stmt = select(Component).where(Component.is_active.is_(True))

    if subsystem:
        stmt = stmt.where(Component.subsystem == subsystem)
    if verification_status:
        stmt = stmt.where(Component.verification_status == verification_status)
    if min_trl is not None:
        stmt = stmt.where(Component.trl >= min_trl)
    if search:
        stmt = stmt.where(Component.name.ilike(f"%{search.strip()}%"))

    # Compute total count matching filters
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar() or 0

    # Retrieve paginated items
    paginated_stmt = stmt.order_by(
        Component.created_at.desc()
    ).offset(offset).limit(limit)
    items_result = await db.execute(paginated_stmt)
    db_items = items_result.scalars().all()
    items: List[ComponentResponseSchema] = [
        ComponentResponseSchema.model_validate(comp) for comp in db_items
    ]

    return ComponentListResponseSchema(
        total=total_count,
        items=items,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ComponentResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_component(
    payload: ComponentCreateSchema,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Registers a new flight hardware component in the persistent catalog.

    Security Boundary:
      Authenticated users are authorized to register components.
      In production or when ALLOW_CATALOG_MUTATION_WITHOUT_AUTH is disabled,
      unauthenticated modifications are rejected with 403 Forbidden.
    """
    if not current_user:
        if settings.ENVIRONMENT == "production" or not settings.ALLOW_CATALOG_MUTATION_WITHOUT_AUTH:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthenticated catalog additions are disabled in production environments.",
            )

    component_data = payload.model_dump()
    component = Component(**component_data)

    db.add(component)
    await db.commit()
    await db.refresh(component)
    return ComponentResponseSchema.model_validate(component)


@router.post(
    "/sync",
    response_model=CatalogSyncSummarySchema,
    status_code=status.HTTP_200_OK,
    summary="Synchronize Component Catalog with Conflict Resolution and Dry-Run",
)
async def sync_catalog_components(
    payload: CatalogSyncRequestSchema,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronizes a batch of components into the catalog.
    Supports dry-run preview, duplicate checking, and conflict resolution policies.

    Security Boundary:
      Authenticated users are authorized to synchronize catalog components.
      In production or when ALLOW_CATALOG_MUTATION_WITHOUT_AUTH is disabled,
      unauthenticated sync is rejected with 403 Forbidden.
    """
    if not current_user:
        if settings.ENVIRONMENT == "production" or not settings.ALLOW_CATALOG_MUTATION_WITHOUT_AUTH:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Unauthenticated catalog synchronization is "
                    "disabled in production environments."
                ),
            )

    return await catalog_sync_service.sync_components(db, payload)


@router.post(
    "/import/techport/{project_id}",
    response_model=CatalogSyncSummarySchema,
    status_code=status.HTTP_200_OK,
    summary="Import NASA TechPort Project into Component Catalog",
)
async def import_techport_into_catalog(
    project_id: int,
    dry_run: bool = Query(default=False, description="Preview import without persisting"),
    update_policy: SyncUpdatePolicy = Query(
        default=SyncUpdatePolicy.PRESERVE_CURATED,
        description="Policy when matching component already exists",
    ),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches an official NASA TechPort project and imports it into the component catalog
    with explicit field-level provenance distinguishing NASA programmatic data from hardware specs.
    """
    if not current_user:
        if settings.ENVIRONMENT == "production" or not settings.ALLOW_CATALOG_MUTATION_WITHOUT_AUTH:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthenticated TechPort imports are disabled in production environments.",
            )

    _, summary = await catalog_sync_service.import_from_techport(
        db, project_id=project_id, dry_run=dry_run, update_policy=update_policy
    )
    return summary


@router.get(
    "/provenance/{component_id}",
    response_model=ComponentProvenanceResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Field-Level Source Provenance Audit",
)
async def get_component_provenance(
    component_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves full field-level provenance records and citations for each specification
    of a catalog component.
    """
    stmt = select(Component).where(Component.id == component_id)
    result = await db.execute(stmt)
    component = result.scalar_one_or_none()

    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' not found in catalog.",
        )

    return ComponentProvenanceResponseSchema(
        component_id=component.id,
        component_name=component.name,
        subsystem=component.subsystem,
        verification_status=component.verification_status,
        source_system=component.source_system,
        source_url=component.source_url,
        techport_id=component.techport_id,
        raw_source_hash=component.raw_source_hash,
        last_synced_at=component.last_synced_at,
        field_provenance=component.field_provenance or {},
    )


@router.get(
    "/catalog/status",
    response_model=CatalogStatusResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get Component Catalog Freshness and Provenance Status",
)
@router.get(
    "/status",
    response_model=CatalogStatusResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get Component Catalog Freshness and Provenance Status (Alias)",
)
async def get_catalog_status(
    db: AsyncSession = Depends(get_db),
) -> CatalogStatusResponseSchema:
    """
    Returns catalog-wide metrics: total components, counts by subsystem and verification
    status, field-level provenance coverage percentage, recorded source systems,
    and last sync timestamp.
    """
    stmt = select(Component).where(Component.is_active.is_(True))
    result = await db.execute(stmt)
    components = result.scalars().all()

    total = len(components)
    subsystems_breakdown: dict[str, int] = {}
    verification_breakdown: dict[str, int] = {}
    with_prov_count = 0
    source_systems_set: set[str] = set()
    latest_sync = None

    for comp in components:
        # Subsystem count
        sub_key = comp.subsystem.value if hasattr(comp.subsystem, "value") else str(comp.subsystem)
        subsystems_breakdown[sub_key] = subsystems_breakdown.get(sub_key, 0) + 1

        # Verification status count
        ver_key = (
            comp.verification_status.value
            if hasattr(comp.verification_status, "value")
            else str(comp.verification_status)
        )
        verification_breakdown[ver_key] = verification_breakdown.get(ver_key, 0) + 1

        # Field provenance check
        if comp.field_provenance and len(comp.field_provenance) > 0:
            with_prov_count += 1

        if comp.source_system:
            source_systems_set.add(comp.source_system)

        if comp.last_synced_at:
            if latest_sync is None or comp.last_synced_at > latest_sync:
                latest_sync = comp.last_synced_at

    cov_pct = (with_prov_count / total * 100.0) if total > 0 else 0.0

    return CatalogStatusResponseSchema(
        total_components=total,
        subsystems_breakdown=subsystems_breakdown,
        verification_status_breakdown=verification_breakdown,
        components_with_provenance=with_prov_count,
        provenance_coverage_percent=round(cov_pct, 2),
        source_systems=sorted(list(source_systems_set)),
        last_synced_at=latest_sync,
    )


@router.get(
    "/{component_id}",
    response_model=ComponentResponseSchema,
    status_code=status.HTTP_200_OK,
)
async def get_component(
    component_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves detailed specifications and provenance of a single catalog component.
    """
    stmt = select(Component).where(Component.id == component_id)
    result = await db.execute(stmt)
    component = result.scalar_one_or_none()

    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' not found in catalog.",
        )
    return ComponentResponseSchema.model_validate(component)
