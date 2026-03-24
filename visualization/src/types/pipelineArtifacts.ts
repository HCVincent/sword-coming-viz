// Pipeline artifact types (JSON files under `data/`)

export interface SegmentYearIndexEntry {
  juan_index: number;
  segment_index: number;
  segment_start_time_raw: string | null;
  year: number | null;
  parse_method: string | null;
  confidence: number;
}

export interface SegmentYearIndex {
  version: string;
  cutoff_year: number;
  generated_at: string;
  segments: Record<string, SegmentYearIndexEntry>;
}

export interface SegmentYearOverrideEntry {
  year: number | null;
  reason?: string;
}

export interface SegmentYearOverrides {
  version: string;
  notes?: string;
  overrides: Record<string, SegmentYearOverrideEntry | number | null>;
}

export interface UnitProgressIndexUnit {
  unit_index: number;
  unit_title: string;
  season_index: number;
  season_name: string;
  progress_start: number;
  progress_end: number;
}

export interface UnitProgressIndexSegment {
  unit_index: number;
  segment_index: number;
  progress_index: number;
  progress_label: string;
}

export interface UnitProgressIndex {
  version: string;
  generated_at: string;
  book_id: string;
  unit_label: string;
  progress_label: string;
  total_units: number;
  total_progress_points: number;
  units: Record<string, UnitProgressIndexUnit>;
  segments: Record<string, UnitProgressIndexSegment>;
}

export interface BookQuickFilter {
  label: string;
  unit_range: [number, number];
  progress_range: [number, number];
}

export interface BookConfig {
  book_id: string;
  title: string;
  subtitle?: string;
  unit_label: string;
  progress_label: string;
  has_geo_coordinates: boolean;
  default_tab?:
    | 'timeline'
    | 'network'
    | 'power'
    | 'locations'
    | 'map'
    | 'writerArcs'
    | 'conflicts'
    | 'foreshadowing';
  quick_filters: BookQuickFilter[];
}

export interface LocationGeocodingEntry {
  location_id: string;
  canonical_name: string;
  modern_name: string;
  query: string;
  coordinates: [number, number] | null;
  candidate_coordinates?: [number, number] | null;
  candidate_count?: number | null;
  confidence: number;
  source: string;
  evidence: string;
  info?: string;
  infocode?: string;
  needs_review: boolean;
  attempts?: number;
  updated_at: string;
}

export interface LocationGeocodingOverridesEntry {
  coordinates: [number, number];
  notes?: string;
}

export interface LocationGeocodingCache {
  version: string;
  provider: string;
  generated_at: string;
  locations: Record<string, LocationGeocodingEntry>;
  overrides: Record<string, LocationGeocodingOverridesEntry>;
}
