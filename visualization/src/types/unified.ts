// Unified Knowledge Base Types
// These types mirror the Python unified models for the resolved/merged entities

export interface EntityOccurrence {
  juan_index: number;
  segment_index: number;
  chunk_index: number;
  sentence_indexes: number[];
  original_description: string;
  source_sentence: string;
}

export interface UnifiedRole {
  id: string;
  canonical_name: string;
  all_names: string[];
  description: string;
  display_summary?: string;
  identity_summary?: string;
  long_description?: string;
  profile_version?: string;
  original_descriptions: string[];
  powers: string[];
  primary_power: string | null;
  first_appearance_juan: number;
  last_appearance_juan: number;
  active_period: string | null;
  occurrences: EntityOccurrence[];
  total_mentions: number;
  juans_appeared: number[];
  units_appeared?: number[];
  related_entities: string[];
  created_at: string;
  updated_at: string;
}

export interface UnifiedLocation {
  id: string;
  canonical_name: string;
  all_names: string[];
  location_type: string;
  description: string;
  display_summary?: string;
  identity_summary?: string;
  long_description?: string;
  profile_version?: string;
  original_descriptions?: string[];
  modern_name: string;
  coordinates: [number, number] | null;
  associated_entities: string[];
  associated_events: string[];
  occurrences: EntityOccurrence[];
  total_mentions: number;
  juans_appeared: number[];
  units_appeared?: number[];
  created_at: string;
  updated_at: string;
}

export interface UnifiedEvent {
  id: string;
  name: string;
  pattern_key?: string;
  display_name?: string;
  title_source?: string;
  grounding_excerpt_ids?: string[];
  time: string | null;
  time_text?: string | null;
  time_start: number | null;
  time_end: number | null;
  progress_start?: number | null;
  progress_end?: number | null;
  progress_label?: string | null;
  imputed_time_start: number | null;
  imputed_time_end: number | null;
  location: string | null;
  participants: string[];
  description: string;
  background: string;
  significance: string;
  source_juans: number[];
  source_units?: number[];
  source_segments: string[];
  action_count: number;
  // Dossier fields (Top 500 events only)
  identity_summary?: string;
  display_summary_dossier?: string;
  long_description?: string;
  story_function?: string;
  relationship_impact?: string;
  dossier_source?: string;
  dossier_version?: string;
  created_at: string;
  updated_at: string;
}

export interface UnifiedRelation {
  id: string;
  from_entity: string;
  to_entity: string;
  action_types: string[];
  primary_action: string;
  interaction_count: number;
  first_interaction_time: string | null;
  last_interaction_time: string | null;
  first_interaction_text?: string | null;
  last_interaction_text?: string | null;
  progress_start?: number | null;
  progress_end?: number | null;
  progress_label?: string | null;
  first_interaction_year: number | null;
  last_interaction_year: number | null;
  contexts: string[];
  source_juans: number[];
  source_units?: number[];
  // Dossier fields
  identity_summary?: string;
  display_summary?: string;
  long_description?: string;
  story_function?: string;
  phase_arc?: string;
  interaction_patterns?: string[];
  summary_source?: string;
  profile_version?: string;
  created_at: string;
  updated_at: string;
}

export interface UnifiedPolity {
  id: string;
  canonical_name: string;
  all_names: string[];
  description: string;
  original_descriptions: string[];
  occurrences: EntityOccurrence[];
  total_mentions: number;
  juans_appeared: number[];
  created_at: string;
  updated_at: string;
}

export interface UnifiedOrganization {
  id: string;
  canonical_name: string;
  all_names: string[];
  description: string;
  original_descriptions: string[];
  occurrences: EntityOccurrence[];
  total_mentions: number;
  juans_appeared: number[];
  created_at: string;
  updated_at: string;
}

export interface UnifiedSchool {
  id: string;
  canonical_name: string;
  all_names: string[];
  description: string;
  original_descriptions: string[];
  occurrences: EntityOccurrence[];
  total_mentions: number;
  juans_appeared: number[];
  created_at: string;
  updated_at: string;
}

export interface UnifiedKnowledgeBase {
  book_id?: string;
  unit_label?: string;
  progress_label?: string;
  roles: Record<string, UnifiedRole>;
  locations: Record<string, UnifiedLocation>;
  events: Record<string, UnifiedEvent>;
  relations: Record<string, UnifiedRelation>;

  polities: Record<string, UnifiedPolity>;
  organizations: Record<string, UnifiedOrganization>;
  schools: Record<string, UnifiedSchool>;

  name_to_role_id: Record<string, string>;
  name_to_location_id: Record<string, string>;
  name_to_polity_id: Record<string, string>;
  name_to_organization_id: Record<string, string>;
  name_to_school_id: Record<string, string>;
  power_to_roles: Record<string, string[]>;
  juan_to_roles: Record<number, string[]>;
  juan_to_events: Record<number, string[]>;
  juan_to_polities: Record<number, string[]>;
  juan_to_organizations: Record<number, string[]>;
  juan_to_schools: Record<number, string[]>;
  unit_to_roles?: Record<number, string[]>;
  unit_to_events?: Record<number, string[]>;
  unit_to_polities?: Record<number, string[]>;
  unit_to_organizations?: Record<number, string[]>;
  unit_to_schools?: Record<number, string[]>;

  total_roles: number;
  total_locations: number;
  total_events: number;
  total_relations: number;
  total_polities: number;
  total_organizations: number;
  total_schools: number;
  juans_processed: number[];
  last_updated: string;
}

export interface RoleNodeUnified {
  id: string;
  name: string;
  power: string | null;
  description: string;
  displaySummary?: string;
  identitySummary?: string;
  longDescription?: string;
  profileVersion?: string;
  originalDescriptions?: string[];
  appearances: number;
  units: number[];
  aliases: string[];
  relatedEntities: string[];
  isIsolated?: boolean;
}

export interface RoleLinkUnified {
  source: string;
  target: string;
  action: string;
  weight: number;
  timeText: string | null;
  progressStart: number | null;
  progressEnd: number | null;
  progressLabel: string | null;
  actionTypes: string[];
  contexts: string[];
  sourceUnits: number[];
  // Relation dossier
  identitySummary?: string;
  displaySummary?: string;
  longDescription?: string;
  storyFunction?: string;
  phaseArc?: string;
  interactionPatterns?: string[];
}

export interface TimelineEventUnified {
  id: string;
  name: string;
  timeText: string | null;
  timeNumeric: number | null;
  progressStart: number | null;
  progressEnd: number | null;
  progressLabel: string | null;
  location: string | null;
  participants: string[];
  description: string;
  unitIndex: number;
  type: 'event';
  significance: string;
  background: string;
  // Event dossier (Top 500 only)
  identitySummary?: string;
  displaySummaryDossier?: string;
  longDescription?: string;
  storyFunction?: string;
  relationshipImpact?: string;
}

export interface PowerDistributionUnified {
  power: string;
  count: number;
  roles: string[];
}
