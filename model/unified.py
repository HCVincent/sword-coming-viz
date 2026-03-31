"""
Unified Entity Models: Canonical representations that merge multiple occurrences.

These models aggregate information from multiple extractions across the book,
providing a single source of truth for each entity, location, and event.
"""

from typing import List, Dict, Set, Optional
from pydantic import BaseModel, Field, computed_field
from datetime import datetime


class EntityOccurrence(BaseModel):
    """Record of where an entity was mentioned."""
    juan_index: int
    segment_index: int
    chunk_index: int
    sentence_indexes: List[int] = Field(default_factory=list)
    original_description: str = ""
    source_sentence: str = ""


class UnifiedRole(BaseModel):
    """
    Canonical entity that merges all occurrences of the same person/organization.
    
    This is the "resolved" version of Role, aggregating information from
    multiple extractions across the entire source text.
    """
    
    # Unique identifier (canonical name)
    id: str = Field(description="Unique identifier, typically the most common name")
    
    # Names and aliases
    canonical_name: str = Field(description="The authoritative name for this entity")
    all_names: Set[str] = Field(
        default_factory=set,
        description="All names and aliases found across all occurrences"
    )
    
    # Merged description (best quality)
    description: str = Field(
        default="",
        description="Best description, selected from the most detailed occurrence"
    )

    # AI-generated display summary (post-resolve, tri-season overview)
    display_summary: str = Field(
        default="",
        description="AI-generated 2-4 sentence display summary, 100-220 chars"
    )
    identity_summary: str = Field(
        default="",
        description="One-sentence identity definition, 40-90 chars"
    )
    long_description: str = Field(
        default="",
        description="Full prose character/location introduction, 2-4 paragraphs, 180-420 chars"
    )
    summary_source: str = Field(
        default="",
        description="Summary generator source, e.g. local-agent-reviewed"
    )
    summary_version: str = Field(
        default="",
        description="Summary schema/version marker"
    )
    profile_version: str = Field(
        default="",
        description="Entity profile schema/version marker"
    )
    
    # All original descriptions for reference
    original_descriptions: List[str] = Field(
        default_factory=list,
        description="All unique original descriptions from the book"
    )
    
    # Power/faction affiliations (may change over time)
    powers: List[str] = Field(
        default_factory=list,
        description="All power affiliations, in chronological order if known"
    )
    primary_power: Optional[str] = Field(
        default=None,
        description="Most common or significant power affiliation"
    )
    
    # Temporal information
    first_appearance_juan: int = Field(default=0)
    last_appearance_juan: int = Field(default=0)
    active_period: Optional[str] = Field(
        default=None,
        description="Time period when this entity was active, e.g., '前453年-前403年'"
    )
    
    # Occurrence tracking
    occurrences: List[EntityOccurrence] = Field(
        default_factory=list,
        description="All places where this entity was mentioned"
    )
    
    # Statistics
    total_mentions: int = Field(default=0)
    juans_appeared: Set[int] = Field(default_factory=set)
    units_appeared: Set[int] = Field(default_factory=set)
    
    # Relationships summary
    related_entities: Set[str] = Field(
        default_factory=set,
        description="Other entities this one has relationships with"
    )
    
    # Metadata
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    @computed_field
    @property
    def appearance_count(self) -> int:
        return len(self.occurrences)
    
    @computed_field
    @property
    def juan_span(self) -> int:
        """How many 卷s this entity spans."""
        return len(self.juans_appeared)
    
    class Config:
        # Allow set serialization
        json_encoders = {
            set: list
        }


class UnifiedPolity(BaseModel):
    """Canonical non-human entity (state/dynasty/polity) merged across occurrences."""

    id: str
    canonical_name: str
    all_names: Set[str] = Field(default_factory=set)

    description: str = Field(default="")
    original_descriptions: List[str] = Field(default_factory=list)

    occurrences: List[EntityOccurrence] = Field(default_factory=list)
    total_mentions: int = Field(default=0)
    juans_appeared: Set[int] = Field(default_factory=set)

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    class Config:
        json_encoders = {set: list}


class UnifiedSchool(BaseModel):
    """Canonical school/ideology entity (e.g. 儒家/法家) merged across occurrences."""

    id: str
    canonical_name: str
    all_names: Set[str] = Field(default_factory=set)

    description: str = Field(default="")
    original_descriptions: List[str] = Field(default_factory=list)

    occurrences: List[EntityOccurrence] = Field(default_factory=list)
    total_mentions: int = Field(default=0)
    juans_appeared: Set[int] = Field(default_factory=set)

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    class Config:
        json_encoders = {set: list}


class UnifiedOrganization(BaseModel):
    """Canonical organization/official-title/group entity merged across occurrences."""

    id: str
    canonical_name: str
    all_names: Set[str] = Field(default_factory=set)

    description: str = Field(default="")
    original_descriptions: List[str] = Field(default_factory=list)

    occurrences: List[EntityOccurrence] = Field(default_factory=list)
    total_mentions: int = Field(default=0)
    juans_appeared: Set[int] = Field(default_factory=set)

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    class Config:
        json_encoders = {set: list}


class UnifiedLocation(BaseModel):
    """
    Canonical location that merges all occurrences of the same place.
    """
    
    id: str
    canonical_name: str
    all_names: Set[str] = Field(default_factory=set)
    
    location_type: str = Field(default="", description="国家、城市、地区、山川等")
    description: str = ""
    display_summary: str = Field(
        default="",
        description="AI-generated 2-4 sentence display summary, 100-220 chars"
    )
    identity_summary: str = Field(
        default="",
        description="One-sentence identity definition, 40-90 chars"
    )
    long_description: str = Field(
        default="",
        description="Full prose location introduction, 2-4 paragraphs, 180-420 chars"
    )
    summary_source: str = Field(
        default="",
        description="Summary generator source, e.g. local-agent-reviewed"
    )
    summary_version: str = Field(
        default="",
        description="Summary schema/version marker"
    )
    profile_version: str = Field(
        default="",
        description="Entity profile schema/version marker"
    )
    original_descriptions: List[str] = Field(
        default_factory=list,
        description="All unique original descriptions from the book"
    )
    modern_name: str = ""
    coordinates: Optional[tuple[float, float]] = None
    
    # Related entities that were associated with this location
    associated_entities: Set[str] = Field(default_factory=set)
    
    # Events that occurred at this location
    associated_events: List[str] = Field(default_factory=list)
    
    occurrences: List[EntityOccurrence] = Field(default_factory=list)
    total_mentions: int = Field(default=0)
    juans_appeared: Set[int] = Field(default_factory=set)
    units_appeared: Set[int] = Field(default_factory=set)
    
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        json_encoders = {set: list}


class UnifiedEvent(BaseModel):
    """
    Canonical event that may span multiple segments/chunks.
    """
    
    id: str
    name: str

    # --- Display-title layer (pattern_key / display_name split) ---
    pattern_key: str = Field(
        default="",
        description="Rule-label or recurring-pattern name, e.g. '墙头对话'. Used for dedup/clustering, never shown on UI."
    )
    display_name: str = Field(
        default="",
        description="Grounded, human-readable event title shown on UI and in summaries. Falls back to `name` when empty."
    )
    title_source: str = Field(
        default="",
        description="How display_name was determined: 'catalog' | 'unique' | 'legacy'"
    )
    grounding_excerpt_ids: List[str] = Field(
        default_factory=list,
        description="Excerpt IDs that ground the display_name back to source text."
    )
    
    time: Optional[str] = None
    time_text: Optional[str] = Field(
        default=None,
        description="Original time text when present; kept for display even when not numeric."
    )
    time_start: Optional[int] = Field(default=None, description="Numeric year, negative for BC")
    time_end: Optional[int] = Field(default=None, description="Numeric year, negative for BC")
    progress_start: Optional[int] = Field(
        default=None,
        description="Narrative progress start index for generic, non-year timelines."
    )
    progress_end: Optional[int] = Field(
        default=None,
        description="Narrative progress end index for generic, non-year timelines."
    )
    progress_label: Optional[str] = Field(
        default=None,
        description="Human-readable label for the narrative progress span."
    )

    # Derived from reading context / segment-year index when time_start is missing
    imputed_time_start: Optional[int] = Field(
        default=None,
        description="Imputed numeric year (earliest), derived from segment-year index"
    )
    imputed_time_end: Optional[int] = Field(
        default=None,
        description="Imputed numeric year (latest), derived from segment-year index"
    )
    
    location: Optional[str] = None
    
    # All participants across all mentions
    participants: Set[str] = Field(default_factory=set)
    
    description: str = ""
    background: str = ""
    significance: str = ""
    
    # Source tracking
    source_juans: Set[int] = Field(default_factory=set)
    source_units: Set[int] = Field(default_factory=set)
    source_segments: List[str] = Field(
        default_factory=list,
        description="List of 'juan-segment' keys"
    )
    
    # Related actions that compose this event
    action_count: int = Field(default=0)

    # Provenance – carried from the extraction-time rule match
    evidence_excerpt: str = Field(
        default="",
        description="Short excerpt from the source text that evidences this event."
    )
    matched_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords that triggered the event rule match."
    )
    matched_rule_name: str = Field(
        default="",
        description="Name of the event rule that fired, if any."
    )
    evidence_sentence_indexes: List[int] = Field(
        default_factory=list,
        description="Sentence indexes in the source segment that evidence this event."
    )

    # Whole-book frequency metadata (set during knowledge-base build)
    name_occurrence_count: int = Field(
        default=1,
        description="Number of distinct event_ids sharing this event name across the entire book."
    )
    first_occurrence_unit: Optional[int] = Field(
        default=None,
        description="Earliest unit index where an event with this name appears."
    )
    is_first_occurrence: bool = Field(
        default=True,
        description="Whether this is the first event_id for this name by unit order."
    )

    # --- Dossier fields (populated by event dossier pipeline, Top 500 only) ---
    identity_summary: str = Field(
        default="",
        description="One-sentence event identity, 40-120 chars"
    )
    display_summary_dossier: str = Field(
        default="",
        description="2-3 sentence reader-facing event summary, 120-300 chars"
    )
    long_description: str = Field(
        default="",
        description="3-5 paragraph event essay, 250-600 chars"
    )
    story_function: str = Field(
        default="",
        description="Narrative function of this event, 50-140 chars"
    )
    relationship_impact: str = Field(
        default="",
        description="Impact on participant relationships, 60-180 chars"
    )
    dossier_source: str = Field(default="", description="Dossier generator source")
    dossier_version: str = Field(default="", description="Dossier schema/version marker")
    
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        json_encoders = {set: list}


class UnifiedRelation(BaseModel):
    """
    Aggregated relationship between two entities.
    
    Combines all interactions between a pair of entities across the entire text.
    """
    
    id: str = Field(description="Format: 'from_entity->to_entity'")
    
    from_entity: str
    to_entity: str
    
    # All action types between these entities
    action_types: List[str] = Field(default_factory=list)
    primary_action: str = Field(default="", description="Most common action type")
    
    # Interaction count
    interaction_count: int = Field(default=0)
    
    # Time span of interactions
    first_interaction_time: Optional[str] = None
    last_interaction_time: Optional[str] = None
    first_interaction_text: Optional[str] = Field(
        default=None,
        description="Original text for the earliest interaction when available."
    )
    last_interaction_text: Optional[str] = Field(
        default=None,
        description="Original text for the latest interaction when available."
    )
    progress_start: Optional[int] = Field(
        default=None,
        description="Narrative progress start index for generic timelines."
    )
    progress_end: Optional[int] = Field(
        default=None,
        description="Narrative progress end index for generic timelines."
    )
    progress_label: Optional[str] = Field(
        default=None,
        description="Human-readable label for the interaction's narrative progress span."
    )

    # Numeric year span of interactions (year-based; negative for BCE)
    first_interaction_year: Optional[int] = Field(
        default=None,
        description="Earliest interaction year (numeric), negative for BCE"
    )
    last_interaction_year: Optional[int] = Field(
        default=None,
        description="Latest interaction year (numeric), negative for BCE"
    )
    
    # Contexts from each interaction
    contexts: List[str] = Field(default_factory=list)
    
    # Source tracking
    source_juans: Set[int] = Field(default_factory=set)
    source_units: Set[int] = Field(default_factory=set)

    # --- Dossier fields (populated by relation profile pipeline) ---
    identity_summary: str = Field(
        default="",
        description="One-sentence relation identity, 60-140 chars"
    )
    display_summary: str = Field(
        default="",
        description="2-3 sentence reader-facing relation summary, 160-360 chars"
    )
    long_description: str = Field(
        default="",
        description="3-5 paragraph relation essay, 300-700 chars"
    )
    story_function: str = Field(
        default="",
        description="Narrative function of this relation, 60-160 chars"
    )
    phase_arc: str = Field(
        default="",
        description="Phase progression and key turning points, 100-220 chars"
    )
    interaction_patterns: List[str] = Field(
        default_factory=list,
        description="2-4 归纳 sentences on interaction patterns, each 30-80 chars"
    )
    summary_source: str = Field(default="", description="Dossier generator source")
    profile_version: str = Field(default="", description="Dossier schema/version marker")
    
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        json_encoders = {set: list}


class UnifiedKnowledgeBase(BaseModel):
    """
    The complete unified knowledge base for a book visualization project.
    
    This is the "gold standard" data structure that visualization
    and search should use.
    """
    
    book_id: str = Field(default="swordcoming")
    unit_label: str = Field(default="章节")
    progress_label: str = Field(default="叙事进度")

    # Entity registries
    roles: Dict[str, UnifiedRole] = Field(default_factory=dict)
    polities: Dict[str, UnifiedPolity] = Field(default_factory=dict)
    schools: Dict[str, UnifiedSchool] = Field(default_factory=dict)
    organizations: Dict[str, UnifiedOrganization] = Field(default_factory=dict)
    locations: Dict[str, UnifiedLocation] = Field(default_factory=dict)
    events: Dict[str, UnifiedEvent] = Field(default_factory=dict)
    relations: Dict[str, UnifiedRelation] = Field(default_factory=dict)
    
    # Name resolution index: maps any name/alias to canonical ID
    name_to_role_id: Dict[str, str] = Field(default_factory=dict)
    name_to_polity_id: Dict[str, str] = Field(default_factory=dict)
    name_to_school_id: Dict[str, str] = Field(default_factory=dict)
    name_to_organization_id: Dict[str, str] = Field(default_factory=dict)
    name_to_location_id: Dict[str, str] = Field(default_factory=dict)
    
    # Power/faction index
    power_to_roles: Dict[str, List[str]] = Field(default_factory=dict)
    
    # Temporal index (juan -> entities active in that juan)
    juan_to_roles: Dict[int, List[str]] = Field(default_factory=dict)
    juan_to_polities: Dict[int, List[str]] = Field(default_factory=dict)
    juan_to_schools: Dict[int, List[str]] = Field(default_factory=dict)
    juan_to_organizations: Dict[int, List[str]] = Field(default_factory=dict)
    juan_to_events: Dict[int, List[str]] = Field(default_factory=dict)
    unit_to_roles: Dict[int, List[str]] = Field(default_factory=dict)
    unit_to_polities: Dict[int, List[str]] = Field(default_factory=dict)
    unit_to_schools: Dict[int, List[str]] = Field(default_factory=dict)
    unit_to_organizations: Dict[int, List[str]] = Field(default_factory=dict)
    unit_to_events: Dict[int, List[str]] = Field(default_factory=dict)
    
    # Statistics
    total_roles: int = Field(default=0)
    total_polities: int = Field(default=0)
    total_schools: int = Field(default=0)
    total_organizations: int = Field(default=0)
    total_locations: int = Field(default=0)
    total_events: int = Field(default=0)
    total_relations: int = Field(default=0)
    
    juans_processed: List[int] = Field(default_factory=list)
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        json_encoders = {set: list}
