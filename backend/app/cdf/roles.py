"""
CDF Roles and Permission Governance
Mission Forge — Phase 4
"""

from enum import Enum
from typing import Dict, Set


class CDFRoleType(str, Enum):
    """The four official roles in the Concurrent Design Facility."""
    LEAD_SYSTEMS_ARCHITECT = "LEAD_SYSTEMS_ARCHITECT"
    PROPULSION_POWER_OFFICER = "PROPULSION_POWER_OFFICER"
    SCIENCE_OFFICER = "SCIENCE_OFFICER"
    FLIGHT_DYNAMICS_COMMS_OFFICER = "FLIGHT_DYNAMICS_COMMS_OFFICER"


class CDFMutationCategory(str, Enum):
    """Mutatable domains within the authoritative mission design state."""
    SYSTEM_CONSTRAINTS = "SYSTEM_CONSTRAINTS"
    PROPULSION_POWER = "PROPULSION_POWER"
    SCIENCE_PAYLOAD = "SCIENCE_PAYLOAD"
    FLIGHT_DYNAMICS_COMMS = "FLIGHT_DYNAMICS_COMMS"


# Explicit Role-to-Domain Permission Matrix
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    CDFRoleType.LEAD_SYSTEMS_ARCHITECT.value: {
        CDFMutationCategory.SYSTEM_CONSTRAINTS.value,
    },
    CDFRoleType.PROPULSION_POWER_OFFICER.value: {
        CDFMutationCategory.PROPULSION_POWER.value,
    },
    CDFRoleType.SCIENCE_OFFICER.value: {
        CDFMutationCategory.SCIENCE_PAYLOAD.value,
    },
    CDFRoleType.FLIGHT_DYNAMICS_COMMS_OFFICER.value: {
        CDFMutationCategory.FLIGHT_DYNAMICS_COMMS.value,
    },
}

ROLE_METADATA: Dict[str, Dict[str, str]] = {
    CDFRoleType.LEAD_SYSTEMS_ARCHITECT.value: {
        "title": "Lead Systems Architect",
        "scope": "Mission budget, system-level constraints, and margin governance.",
    },
    CDFRoleType.PROPULSION_POWER_OFFICER.value: {
        "title": "Propulsion & Power Officer",
        "scope": "Propulsion, power system, and related budgets.",
    },
    CDFRoleType.SCIENCE_OFFICER.value: {
        "title": "Science Officer",
        "scope": "Payload and instrument configuration.",
    },
    CDFRoleType.FLIGHT_DYNAMICS_COMMS_OFFICER.value: {
        "title": "Flight Dynamics & Comms Officer",
        "scope": "Trajectory inputs, communication assumptions, and link budget.",
    },
}


class CDFPermissionDeniedError(Exception):
    """Raised when a participant role attempts an unauthorized state mutation."""
    def __init__(self, role: str, category: str):
        super().__init__(
            f"Permission denied: Role '{role}' is not authorized to mutate "
            f"category '{category}'. Authorized roles: "
            f"{[r for r, perms in ROLE_PERMISSIONS.items() if category in perms]}"
        )
        self.role = role
        self.category = category


def check_role_permission(role: str, mutation_category: str) -> bool:
    """Verifies whether a role is authorized to perform mutations in a category."""
    allowed = ROLE_PERMISSIONS.get(role, set())
    return mutation_category in allowed


def assert_role_permission(role: str, mutation_category: str) -> None:
    """Enforces role permission, raising CDFPermissionDeniedError if unauthorized."""
    if not check_role_permission(role, mutation_category):
        raise CDFPermissionDeniedError(role, mutation_category)
