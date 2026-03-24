"""Models for extraction, resolution, and visualization artifacts."""

from .role import Role
from .action import Action
from .event import Event
from .location import Location
from .polity import Polity
from .school import School
from .organization import Organization
from .extraction import ExtractionResult, EntityRelationExtraction
from .unified import (
    UnifiedRole,
    UnifiedPolity,
    UnifiedSchool,
    UnifiedOrganization,
    UnifiedLocation,
    UnifiedEvent,
    UnifiedRelation,
    UnifiedKnowledgeBase,
    EntityOccurrence,
)

__all__ = [
    # Raw extraction models
    "Role",
    "Action",
    "Event",
    "Location",
    "Polity",
    "School",
    "Organization",
    "ExtractionResult",
    "EntityRelationExtraction",
    # Unified/resolved models
    "UnifiedRole",
    "UnifiedPolity",
    "UnifiedSchool",
    "UnifiedOrganization",
    "UnifiedLocation",
    "UnifiedEvent",
    "UnifiedRelation",
    "UnifiedKnowledgeBase",
    "EntityOccurrence",
]

