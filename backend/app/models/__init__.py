"""
SQLAlchemy model exports — import all models so that Base.metadata
is fully populated before init_db() calls create_all().
"""

from backend.app.models.base import UUIDModelMixin, TimestampModelMixin
from backend.app.models.auth import User
from backend.app.models.component import (
    Component,
    SubsystemType,
    VerificationStatus,
)
from backend.app.models.mission import (
    Mission,
    SpacecraftDesign,
    MissionTarget,
    MissionClass,
)
from backend.app.models.techport import TechPortProject
from backend.app.models.trajectory import PorkchopJob, PorkchopJobStatus
from backend.app.models.cdf import (
    CDFRoom,
    CDFRoomParticipant,
    CDFDesignRevision,
    CDFEvent,
    CDFRole,
    CDFRoomStatus,
)
from backend.app.models.fdir import FDIRFindingLog
from backend.app.models.dossier import (
    DossierJob,
    DossierReport,
    DossierReportStatus,
    DossierFormat,
)

__all__ = [
    "UUIDModelMixin",
    "TimestampModelMixin",
    "User",
    "Component",
    "SubsystemType",
    "VerificationStatus",
    "Mission",
    "SpacecraftDesign",
    "MissionTarget",
    "MissionClass",
    "TechPortProject",
    "PorkchopJob",
    "PorkchopJobStatus",
    "CDFRoom",
    "CDFRoomParticipant",
    "CDFDesignRevision",
    "CDFEvent",
    "CDFRole",
    "CDFRoomStatus",
    "FDIRFindingLog",
    "DossierJob",
    "DossierReport",
    "DossierReportStatus",
    "DossierFormat",
]
