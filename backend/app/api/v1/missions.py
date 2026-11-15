"""
Mission and Spacecraft Design Lifecycle Endpoints
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.models.mission import (
    Mission,
    SpacecraftDesign,
    MissionTarget,
    MissionClass,
)
from backend.app.schemas.swapc import SWaPCAnalysisRequest, ComponentSpecSchema
from backend.app.physics.swapc import calculate_swapc

router = APIRouter(prefix="/missions", tags=["Missions & Spacecraft Designs"])


# --- Schemas ---
class MissionCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    description: Optional[str] = None
    target: MissionTarget
    mission_class: MissionClass = MissionClass.DISCOVERY
    budget_cap_usd: Optional[float] = None
    max_launch_mass_kg: Optional[float] = None
    min_delta_v_mps: Optional[float] = None


class MissionResponseSchema(BaseModel):
    id: str
    name: str
    description: Optional[str]
    target: MissionTarget
    mission_class: MissionClass
    budget_cap_usd: float
    max_launch_mass_kg: float
    min_delta_v_mps: float
    min_power_margin_percent: float

    model_config = ConfigDict(from_attributes=True)


class DesignCreateSchema(BaseModel):
    name: str = Field(default="Baseline Spacecraft", min_length=1, max_length=128)
    components: List[ComponentSpecSchema] = Field(default_factory=list)
    propellant_mass_kg: Optional[float] = None


class DesignResponseSchema(BaseModel):
    id: str
    mission_id: str
    name: str
    version: int
    dry_mass_kg: float
    wet_mass_kg: float
    propellant_mass_kg: float
    power_draw_w: float
    power_generation_w: float
    delta_v_mps: float
    total_cost_usd: float
    is_feasible: bool
    violations: List[dict]

    model_config = ConfigDict(from_attributes=True)


# --- Endpoints ---
@router.post("", response_model=MissionResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_mission(
    payload: MissionCreateSchema,
    db: AsyncSession = Depends(get_db),
):
    """Creates a new exploration mission with target engineering constraints."""
    budget_cap = payload.budget_cap_usd
    if not budget_cap:
        if payload.mission_class == MissionClass.DISCOVERY:
            budget_cap = 500_000_000.0
        elif payload.mission_class == MissionClass.NEW_FRONTIERS:
            budget_cap = 1_000_000_000.0
        else:
            budget_cap = 3_200_000_000.0

    mission = Mission(
        name=payload.name,
        description=payload.description,
        target=payload.target,
        mission_class=payload.mission_class,
        budget_cap_usd=budget_cap,
        max_launch_mass_kg=payload.max_launch_mass_kg or 1800.0,
        min_delta_v_mps=payload.min_delta_v_mps or 3800.0,
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return mission


@router.get("", response_model=List[MissionResponseSchema])
async def list_missions(db: AsyncSession = Depends(get_db)):
    """Lists all active space exploration missions."""
    result = await db.execute(select(Mission).order_by(Mission.created_at.desc()))
    return result.scalars().all()


@router.get("/{mission_id}", response_model=MissionResponseSchema)
async def get_mission(mission_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves full specification of a single mission."""
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found.")
    return mission


@router.post(
    "/{mission_id}/designs",
    response_model=DesignResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_spacecraft_design(
    mission_id: str,
    payload: DesignCreateSchema,
    db: AsyncSession = Depends(get_db),
):
    """
    Saves a versioned spacecraft configuration for a mission and automatically
    runs the deterministic SWaP-C engine to record mass, power, and feasibility.
    """
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found.")

    # Execute deterministic SWaP-C calculation
    swapc_req = SWaPCAnalysisRequest(
        target=mission.target,
        mission_class=mission.mission_class,
        components=payload.components,
        propellant_mass_kg=payload.propellant_mass_kg,
        required_delta_v_mps=mission.min_delta_v_mps,
        custom_budget_cap_usd=mission.budget_cap_usd,
        custom_max_mass_kg=mission.max_launch_mass_kg,
        min_power_margin_percent=mission.min_power_margin_percent,
    )
    analysis = calculate_swapc(swapc_req)

    # Persist design record
    design = SpacecraftDesign(
        mission_id=mission.id,
        name=payload.name,
        component_ids=[c.id for c in payload.components if c.id],
        propellant_mass_kg=analysis.propellant_mass_kg,
        dry_mass_kg=analysis.dry_mass_kg,
        wet_mass_kg=analysis.wet_mass_kg,
        power_draw_w=analysis.total_power_draw_w,
        power_generation_w=analysis.total_power_generated_w,
        delta_v_mps=analysis.available_delta_v_mps,
        total_cost_usd=analysis.total_mission_cost_usd,
        is_feasible=analysis.is_feasible,
        violations=[v.model_dump() for v in analysis.violations],
    )
    db.add(design)
    await db.commit()
    await db.refresh(design)
    return design


@router.get("/{mission_id}/designs", response_model=List[DesignResponseSchema])
async def list_mission_designs(mission_id: str, db: AsyncSession = Depends(get_db)):
    """Lists all saved spacecraft designs for a mission."""
    result = await db.execute(
        select(SpacecraftDesign)
        .where(SpacecraftDesign.mission_id == mission_id)
        .order_by(SpacecraftDesign.created_at.desc())
    )
    return result.scalars().all()
