"""
Catalog Synchronization & Import Engine
Provides safe, idempotent synchronization, dry-run previews, conflict resolution,
and TechPort project mapping with field-level provenance preservation.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.provenance import FieldProvenanceRecord, compute_payload_hash
from backend.app.integrations.techport import techport_client
from backend.app.models.component import (
    Component,
    SubsystemType,
    VerificationStatus,
)
from backend.app.models.techport import TechPortProject
from backend.app.schemas.component import (
    CatalogSyncRequestSchema,
    CatalogSyncSummarySchema,
    ComponentCreateSchema,
    SyncUpdatePolicy,
)

logger = logging.getLogger(__name__)


def infer_subsystem_from_techport(title: str, description: Optional[str]) -> SubsystemType:
    """Infers spacecraft subsystem category from TechPort title and description text."""
    combined = f"{title} {description or ''}".lower()
    if any(k in combined for k in (
        "propulsion", "thruster", "engine", "propellant", "ion beam"
    )):
        return SubsystemType.PROPULSION
    if any(k in combined for k in (
        "solar", "battery", "power system", "rtg", "thermoelectric", "fuel cell"
    )):
        return SubsystemType.POWER
    if any(k in combined for k in (
        "antenna", "telecom", "transponder", "rf", "optical communication", "transmitter"
    )):
        return SubsystemType.TELECOM
    if any(k in combined for k in ("thermal", "radiator", "heat pipe", "cryogenic", "insulation")):
        return SubsystemType.THERMAL
    if any(k in combined for k in (
        "attitude", "star tracker", "reaction wheel", "gyroscope", "adcs"
    )):
        return SubsystemType.ADCS
    if any(k in combined for k in ("spectrometer", "camera", "magnetometer", "payload", "sensor")):
        return SubsystemType.SCIENCE
    if any(k in combined for k in ("structure", "composite", "deployable boom", "truss")):
        return SubsystemType.STRUCTURE
    return SubsystemType.PAYLOAD_SUPPORT


class CatalogSyncService:
    """
    Manages safe, idempotent catalog synchronization and import workflows.
    Protects curated human/flight-tested data and maintains field-level provenance.
    """

    async def sync_components(
        self,
        session: AsyncSession,
        payload: CatalogSyncRequestSchema,
    ) -> CatalogSyncSummarySchema:
        """
        Executes synchronization of component batches according to configured update policy.
        Can run in dry-run mode to audit proposed modifications without writing to database.
        """
        now = datetime.now(timezone.utc)
        created_count = 0
        updated_count = 0
        skipped_count = 0
        conflicts: List[Dict[str, Any]] = []
        created_ids: List[str] = []
        updated_ids: List[str] = []
        errors: List[str] = []

        seen_batch_names: set[str] = set()

        for item in payload.items:
            name = item.name.strip()
            if name.lower() in seen_batch_names:
                errors.append(f"Duplicate component name '{name}' within submitted batch.")
                continue
            seen_batch_names.add(name.lower())

            try:
                # 1. Lookup existing record by exact name or techport_id
                stmt = select(Component).where(Component.name == name)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing and item.techport_id:
                    stmt_tp = select(Component).where(Component.techport_id == item.techport_id)
                    result_tp = await session.execute(stmt_tp)
                    existing = result_tp.scalar_one_or_none()

                item_data = item.model_dump()
                item_hash = compute_payload_hash(item_data)
                source_sys = item.source_system or payload.source_system or "CATALOG_SYNC"

                if existing is None:
                    # New component to insert
                    created_count += 1
                    if not payload.dry_run:
                        item_data["source_system"] = source_sys
                        item_data["raw_source_hash"] = item_hash
                        item_data["last_synced_at"] = now
                        new_comp = Component(**item_data)
                        session.add(new_comp)
                        await session.flush()
                        created_ids.append(new_comp.id)
                    else:
                        created_ids.append(f"dry-run-new-{name}")

                else:
                    # Existing record found; evaluate conflict and update policy
                    is_updated = False
                    comp_conflicts = self._detect_conflicts(existing, item)

                    if comp_conflicts:
                        conflicts.extend(comp_conflicts)

                    if payload.update_policy == SyncUpdatePolicy.PRESERVE_CURATED:
                        # Only update fields that are currently None or unverified
                        is_updated = self._apply_preserve_curated_update(
                            existing, item, source_sys, item_hash, now, payload.dry_run
                        )

                    elif payload.update_policy == SyncUpdatePolicy.OVERWRITE_ALL:
                        is_updated = self._apply_overwrite_update(
                            existing, item, source_sys, item_hash, now, payload.dry_run
                        )

                    elif payload.update_policy == SyncUpdatePolicy.UPDATE_MISSING_ONLY:
                        is_updated = self._apply_missing_only_update(
                            existing, item, source_sys, item_hash, now, payload.dry_run
                        )

                    if is_updated:
                        updated_count += 1
                        updated_ids.append(existing.id)
                    else:
                        skipped_count += 1

            except Exception as item_err:
                logger.error("Error processing sync item '%s': %s", name, item_err)
                errors.append(f"Component '{name}': {item_err}")

        # Finalize database transaction
        if not payload.dry_run:
            if errors:
                await session.rollback()
                logger.warning("Sync failed with errors; rolled back entire transaction.")
            else:
                await session.commit()
                logger.info(
                    "Sync committed: created=%d, updated=%d, skipped=%d",
                    created_count,
                    updated_count,
                    skipped_count,
                )

        return CatalogSyncSummarySchema(
            dry_run=payload.dry_run,
            update_policy=payload.update_policy,
            total_submitted=len(payload.items),
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            conflict_count=len(conflicts),
            conflicts=conflicts,
            created_ids=created_ids,
            updated_ids=updated_ids,
            errors=errors,
        )

    def _detect_conflicts(
        self, existing: Component, incoming: ComponentCreateSchema
    ) -> List[Dict[str, Any]]:
        """Compares critical technical specifications to detect discrepancies."""
        conflicts: List[Dict[str, Any]] = []
        check_fields = [
            "subsystem",
            "mass_kg",
            "isp_seconds",
            "thrust_newtons",
            "power_draw_w",
            "power_generation_w",
            "trl",
        ]
        for field in check_fields:
            exist_val = getattr(existing, field, None)
            in_val = getattr(incoming, field, None)
            if exist_val is not None and in_val is not None and exist_val != in_val:
                conflicts.append(
                    {
                        "component_name": existing.name,
                        "field": field,
                        "existing_value": exist_val,
                        "incoming_value": in_val,
                    }
                )
        return conflicts

    def _apply_preserve_curated_update(
        self,
        existing: Component,
        incoming: ComponentCreateSchema,
        source_sys: str,
        item_hash: str,
        now: datetime,
        dry_run: bool,
    ) -> bool:
        """
        Updates missing or unpopulated fields without modifying existing authoritative values.
        """
        modified = False
        in_dict = incoming.model_dump()

        for field, in_val in in_dict.items():
            if field in ("name", "id", "created_at", "updated_at", "field_provenance"):
                continue
            exist_val = getattr(existing, field, None)

            # If existing is empty/None/zero and incoming has a real value, populate it,
            # UNLESS the field is an authoritative curated specification in field_provenance.
            if in_val is not None:
                should_update = False
                has_curated_provenance = (
                    existing.field_provenance is not None
                    and field in existing.field_provenance
                )
                if not has_curated_provenance:
                    if exist_val is None:
                        should_update = True
                    elif isinstance(exist_val, (int, float)) and exist_val == 0.0 and in_val > 0.0:
                        should_update = True

                if should_update:
                    if not dry_run:
                        setattr(existing, field, in_val)
                    modified = True

        # Merge field_provenance for any newly added fields
        if not dry_run and modified:
            prov = dict(existing.field_provenance or {})
            for f_name, p_rec in (incoming.field_provenance or {}).items():
                if f_name not in prov:
                    prov[f_name] = p_rec
            existing.field_provenance = prov
            existing.last_synced_at = now
            existing.raw_source_hash = item_hash

        return modified

    def _apply_overwrite_update(
        self,
        existing: Component,
        incoming: ComponentCreateSchema,
        source_sys: str,
        item_hash: str,
        now: datetime,
        dry_run: bool,
    ) -> bool:
        """Overwrites all fields on existing component."""
        if dry_run:
            return True

        in_dict = incoming.model_dump()
        for field, in_val in in_dict.items():
            if field in ("id", "created_at", "updated_at"):
                continue
            setattr(existing, field, in_val)

        existing.source_system = source_sys
        existing.raw_source_hash = item_hash
        existing.last_synced_at = now
        return True

    def _apply_missing_only_update(
        self,
        existing: Component,
        incoming: ComponentCreateSchema,
        source_sys: str,
        item_hash: str,
        now: datetime,
        dry_run: bool,
    ) -> bool:
        """Only updates fields where existing value is explicitly None."""
        modified = False
        in_dict = incoming.model_dump()

        for field, in_val in in_dict.items():
            if field in ("name", "id", "created_at", "updated_at", "field_provenance"):
                continue
            exist_val = getattr(existing, field, None)
            if exist_val is None and in_val is not None:
                if not dry_run:
                    setattr(existing, field, in_val)
                modified = True

        if not dry_run and modified:
            existing.last_synced_at = now
        return modified

    async def import_from_techport(
        self,
        session: AsyncSession,
        project_id: int,
        dry_run: bool = False,
        update_policy: SyncUpdatePolicy = SyncUpdatePolicy.PRESERVE_CURATED,
    ) -> Tuple[TechPortProject, CatalogSyncSummarySchema]:
        """
        Fetches an official NASA TechPort project, persists it in the techport_projects table,
        and synchronizes it into the component catalog with explicit field-level provenance.
        """
        project_detail = await techport_client.get_project(project_id)
        now = datetime.now(timezone.utc)

        # 1. Persist to techport_projects table
        stmt = select(TechPortProject).where(TechPortProject.techport_id == str(project_id))
        res = await session.execute(stmt)
        tp_row = res.scalar_one_or_none()

        if tp_row is None:
            tp_row = TechPortProject(
                techport_id=str(project_id),
                title=project_detail.title,
                status=project_detail.status,
                description=project_detail.description,
                benefits=project_detail.benefits,
                lead_organization=project_detail.lead_organization,
                program=project_detail.program,
                trl_begin=project_detail.trl_begin,
                trl_current=project_detail.trl_current,
                trl_end=project_detail.trl_end,
                last_updated_date=project_detail.last_updated,
                canonical_url=project_detail.canonical_url,
                raw_payload=project_detail.raw_payload,
                retrieved_at=now,
            )
            if not dry_run:
                session.add(tp_row)
        else:
            if not dry_run:
                tp_row.title = project_detail.title
                tp_row.status = project_detail.status
                tp_row.description = project_detail.description
                tp_row.benefits = project_detail.benefits
                tp_row.lead_organization = project_detail.lead_organization
                tp_row.program = project_detail.program
                tp_row.trl_begin = project_detail.trl_begin
                tp_row.trl_current = project_detail.trl_current
                tp_row.trl_end = project_detail.trl_end
                tp_row.last_updated_date = project_detail.last_updated
                tp_row.raw_payload = project_detail.raw_payload
                tp_row.retrieved_at = now

        # 2. Map TechPort record to ComponentCreateSchema with field-level provenance
        subsystem = infer_subsystem_from_techport(
            project_detail.title, project_detail.description
        )
        current_trl = (
            project_detail.trl_current
            or project_detail.trl_end
            or project_detail.trl_begin
            or 1
        )

        # Build field-level provenance: clearly distinguish TechPort data from hardware specs
        is_flight_trl = current_trl >= 7
        trl_status = (
            VerificationStatus.DERIVED_FROM_FLIGHT_DATA
            if is_flight_trl
            else VerificationStatus.UNVERIFIED
        )
        trl_notes = (
            f"NASA STMD assessed TRL current={project_detail.trl_current}, "
            f"target={project_detail.trl_end}"
        )
        spec_notes = (
            "Physical parameters (mass, power, thrust, RF) are not "
            "published in TechPort project records"
        )

        field_prov: Dict[str, Any] = {
            "name": FieldProvenanceRecord(
                source_system="NASA_TECHPORT",
                citation=f"NASA TechPort Project {project_id}",
                canonical_url=project_detail.canonical_url,
                verification_status=VerificationStatus.VERIFIED_AUTHORITATIVE,
                notes="Project title directly retrieved from official TechPort API",
            ).model_dump(),
            "description": FieldProvenanceRecord(
                source_system="NASA_TECHPORT",
                citation=f"NASA TechPort Project {project_id}",
                canonical_url=project_detail.canonical_url,
                verification_status=VerificationStatus.VERIFIED_AUTHORITATIVE,
                notes="Technology description directly retrieved from official TechPort API",
            ).model_dump(),
            "trl": FieldProvenanceRecord(
                source_system="NASA_TECHPORT",
                citation=f"NASA TechPort Project {project_id}",
                canonical_url=project_detail.canonical_url,
                verification_status=trl_status,
                notes=trl_notes,
            ).model_dump(),
            "physical_specifications": FieldProvenanceRecord(
                source_system="NASA_TECHPORT",
                citation=f"NASA TechPort Project {project_id}",
                canonical_url=project_detail.canonical_url,
                verification_status=VerificationStatus.UNVERIFIED,
                notes=spec_notes,
            ).model_dump(),
        }

        # Truncate title to 128 characters if needed for db schema
        comp_name = project_detail.title[:128]
        desc = project_detail.description[:1024] if project_detail.description else None
        heritage = (
            f"NASA STMD {project_detail.program}" if project_detail.program else None
        )

        component_schema = ComponentCreateSchema(
            name=comp_name,
            subsystem=subsystem,
            description=desc,
            mass_kg=0.0,
            power_draw_w=0.0,
            power_generation_w=0.0,
            cost_usd=0.0,
            trl=current_trl,
            flight_heritage=heritage,
            techport_id=str(project_id),
            source_url=project_detail.canonical_url,
            source_system="NASA_TECHPORT",
            verification_status=trl_status,
            field_provenance=field_prov,
            specifications={
                "lead_organization": project_detail.lead_organization,
                "program": project_detail.program,
                "status": project_detail.status,
                "primary_taxonomy": project_detail.primary_taxonomy,
            },
            is_active=True,
        )

        # 3. Synchronize component into catalog
        sync_req = CatalogSyncRequestSchema(
            items=[component_schema],
            update_policy=update_policy,
            dry_run=dry_run,
            source_system="NASA_TECHPORT",
        )
        sync_summary = await self.sync_components(session, sync_req)
        return tp_row, sync_summary


# Global singleton service
catalog_sync_service = CatalogSyncService()
