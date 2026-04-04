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
from .visual_profile import (
    AppearanceDetails,
    AppearanceTimelineEntry,
    CharacterVisualProfile,
    CharacterVisualProfilesPayload,
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
    # Visual profile models
    "AppearanceDetails",
    "AppearanceTimelineEntry",
    "CharacterVisualProfile",
    "CharacterVisualProfilesPayload",
]

