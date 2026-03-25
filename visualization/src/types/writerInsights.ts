export interface WriterInsightEventRef {
  event_id: string;
  name: string;
  event_type: string;
  unit_index: number | null;
  unit_title?: string | null;
  season_name?: string | null;
  progress_start: number | null;
  progress_end: number | null;
  progress_label?: string | null;
  location: string | null;
  participants: string[];
  description: string;
  significance: string;
}

export interface WriterRelationshipPhase {
  relation_id: string;
  counterpart_id: string;
  counterpart_name: string;
  phase_label: string;
  trigger_event_id: string | null;
  trigger_event_name: string | null;
  unit_index: number | null;
  progress_start: number | null;
  location: string | null;
  summary: string;
}

export interface WriterCharacterArc {
  role_id: string;
  role_name: string;
  spotlight?: boolean;
  aliases: string[];
  primary_power: string | null;
  description: string;
  unit_span: [number | null, number | null];
  progress_span: [number | null, number | null];
  season_names: string[];
  key_locations: string[];
  key_events: WriterInsightEventRef[];
  relationship_phases: WriterRelationshipPhase[];
  summary: string;
}

export interface WriterConflictBeat {
  phase_label: string;
  event_id: string;
  event_name: string;
  unit_index: number | null;
  unit_title?: string | null;
  season_name?: string | null;
  progress_start: number | null;
  location: string | null;
  action_types: string[];
  summary: string;
}

export interface WriterConflictChain {
  id: string;
  title: string;
  spotlight?: boolean;
  source_role_id: string;
  target_role_id: string;
  source_role_name: string;
  target_role_name: string;
  conflict_type: string;
  action_types: string[];
  unit_span: [number | null, number | null];
  progress_span: [number | null, number | null];
  season_names: string[];
  locations: string[];
  tension_score: number;
  beats: WriterConflictBeat[];
  summary: string;
}

export interface WriterCuratedRelationship {
  id: string;
  title: string;
  kind: string;
  spotlight?: boolean;
  source_role_id: string;
  target_role_id: string;
  source_role_name: string;
  target_role_name: string;
  unit_span: [number | null, number | null];
  progress_span: [number | null, number | null];
  season_names: string[];
  key_locations: string[];
  phase_labels: string[];
  manual_beats: WriterCuratedRelationshipBeat[];
  key_events: WriterInsightEventRef[];
  summary: string;
  adaptation_value: string;
}

export interface WriterCuratedRelationshipBeat {
  season_name?: string | null;
  phase_label: string;
  summary: string;
  event_id?: string | null;
  event_name?: string | null;
  unit_index: number | null;
  progress_start: number | null;
  location: string | null;
}

export interface WriterForeshadowingThread {
  id: string;
  label: string;
  spotlight?: boolean;
  focus_roles: string[];
  motif_keywords: string[];
  unit_span: [number | null, number | null];
  progress_span: [number | null, number | null];
  season_names: string[];
  clue_events: WriterInsightEventRef[];
  payoff_events: WriterInsightEventRef[];
  summary: string;
}

export interface WriterInsightsSummary {
  character_arc_count: number;
  conflict_chain_count: number;
  foreshadowing_thread_count: number;
  season_overview_count: number;
  curated_relationship_count: number;
}

export interface WriterInsightsSeason {
  season_name: string;
  unit_range: [number, number];
  progress_range: [number, number];
}

export interface WriterSeasonOverviewRole {
  role_id: string;
  role_name: string;
  unit_appearance_count: number;
  event_count: number;
  relation_count: number;
  density_score: number;
}

export interface WriterSeasonOverviewLocation {
  location_name: string;
  event_count: number;
  role_count: number;
}

export interface WriterSeasonOverviewConflict {
  chain_id: string;
  title: string;
  source_role_name: string;
  target_role_name: string;
  tension_score: number;
}

export interface WriterSeasonOverviewRelationship {
  relationship_id: string;
  title: string;
  source_role_name: string;
  target_role_name: string;
  kind: string;
}

export interface WriterSeasonStoryBeat {
  beat_type: 'opening' | 'midpoint' | 'payoff';
  label: string;
  summary: string;
  event: WriterInsightEventRef | null;
}

export interface WriterSeasonMustKeepScene {
  scene_id: string;
  beat_type: 'opening' | 'midpoint' | 'payoff';
  label: string;
  event: WriterInsightEventRef | null;
  focus_roles: string[];
  related_relationship_titles: string[];
  adaptation_reason: string;
}

export interface WriterSeasonOverview {
  season_name: string;
  unit_range: [number, number];
  progress_range: [number, number];
  summary: string;
  spotlight_summary?: string | null;
  adaptation_hooks: string[];
  story_beats: WriterSeasonStoryBeat[];
  must_keep_scenes: WriterSeasonMustKeepScene[];
  top_roles: WriterSeasonOverviewRole[];
  top_locations: WriterSeasonOverviewLocation[];
  main_conflicts: WriterSeasonOverviewConflict[];
  priority_relationships: WriterSeasonOverviewRelationship[];
  anchor_events: WriterInsightEventRef[];
}

export interface WriterInsightsPayload {
  version: string;
  generated_at: string;
  book_id: string;
  unit_label: string;
  progress_label: string;
  spotlight_role_name?: string | null;
  summary: WriterInsightsSummary;
  seasons: WriterInsightsSeason[];
  season_overviews: WriterSeasonOverview[];
  character_arcs: WriterCharacterArc[];
  curated_relationships: WriterCuratedRelationship[];
  conflict_chains: WriterConflictChain[];
  foreshadowing_threads: WriterForeshadowingThread[];
}
